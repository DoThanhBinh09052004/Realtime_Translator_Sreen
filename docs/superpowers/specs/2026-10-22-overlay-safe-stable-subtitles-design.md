# Overlay-Safe Stable Subtitles Design

## Context

The live translation loop currently masks a cached overlay rectangle, runs OCR as soon as the captured frame changes, and immediately translates every new OCR string. Two user-visible failures follow:

1. The overlay can resize or move without publishing its new rectangle, allowing translated text to re-enter OCR.
2. Progressive or partially disappearing dialogue is translated in fragments, and a short trailing fragment can replace a useful full translation.

OCR speaker-name detection and dialogue line formatting are explicitly outside this change.

## Goals

- Keep the visible translation overlay out of this application's OCR input while leaving it visible to normal recording and screenshot software.
- Translate text after two consecutive identical OCR observations.
- Translate the latest candidate after at most 2.0 seconds so continuously changing text cannot wait forever.
- Translate a candidate seen only once when it disappears before a second observation.
- Prevent a trailing substring of the most recently translated source text from replacing the full translation.
- Preserve the current translation retry, settings revision, caching, and overlay refresh behavior.

## Non-Goals

- Detecting or formatting speaker names.
- Preserving or merging OCR line breaks.
- Changing translation providers, prompts, models, or API settings.
- Hiding the overlay from OBS, screen recording, or other capture applications.
- Adding new user-facing settings for stabilization thresholds.

## Architecture

The work is split into two independently testable components and implemented in this order:

1. **Live overlay-mask synchronization.** The UI publishes every capture-relevant geometry or visibility change. The worker applies a clipped, padded mask before both frame-change detection and OCR.
2. **Subtitle stabilization.** A focused state machine receives OCR observations and decides whether to wait, translate, or treat the observation as unchanged. The worker bypasses its static-frame OCR optimization only while the state machine has a pending candidate.

The overlay protection remains a pixel-mask operation inside the application. It does not use Windows capture-exclusion flags because the translation should remain visible in recordings.

## Component 1: Live Overlay Mask

`ui/overlay.py` will expose a `capture_geometry_changed` signal whose value is either the current global `(x, y, width, height)` rectangle or `None` when the overlay is not visible. The overlay publishes this value after show, hide, move, and resize events. A text update already changes widget size through `adjustSize()`; the resize event therefore publishes the new rectangle immediately instead of waiting for a fade animation to finish.

`main.py` will connect this signal directly to `TranslationWorker.set_overlay_rect()` and will still perform one explicit initial synchronization after constructing the worker. The existing fade-completion and drag-only synchronization hooks become unnecessary.

`core/worker.py` will apply a 6-pixel padding around the overlay rectangle before translating it into capture-relative coordinates. The mask is clipped to the captured image on all four sides, including captures on monitors with negative desktop coordinates. A missing or non-overlapping rectangle leaves the image unchanged. Masking continues to occur before `_is_frame_changed()`, so overlay animation and text changes cannot trigger OCR work.

## Component 2: Subtitle Stabilizer

A new `core/subtitle_stabilizer.py` module will own temporal text state. It will expose:

- `StabilizationDecision(action, text)`, where `action` is `wait`, `translate`, or `unchanged`.
- `SubtitleStabilizer.observe(text: str, now_s: float) -> StabilizationDecision`.
- `SubtitleStabilizer.commit(text: str) -> None`, called only after a translation succeeds.
- `SubtitleStabilizer.reset() -> None`.
- `SubtitleStabilizer.has_pending: bool`.

The state machine collapses every whitespace run to one space and trims the result before comparisons. It follows these rules:

1. A new non-empty candidate is held as pending and returns `wait`.
2. The same pending candidate observed a second consecutive time returns `translate`.
3. Prefix-related candidates belong to the same progressive sequence: when either the new candidate starts with the pending text or the pending text starts with the new candidate, the latest observation replaces the pending value without resetting the sequence start time. The latest value returns `translate` when the sequence reaches 2.0 seconds.
4. A candidate with no prefix relationship to the pending value is materially different. It replaces the pending candidate and starts a new 2.0-second window.
5. An empty observation translates the pending candidate if one exists; otherwise it returns `wait`.
6. A candidate equal to the last successfully committed source returns `unchanged`.
7. A non-empty candidate whose whitespace-delimited tokens are a strict suffix of the last committed source tokens is treated as `unchanged` until an empty observation or text unrelated by equality/suffix starts a new dialogue segment. It never replaces the existing overlay during that trailing-fragment segment.
8. `commit()` records the successfully translated source and clears pending state. Failed translations are not committed, so the existing retry path can try the same source again.

`core/worker.py` will consult the stabilizer after OCR and before the translation service. While `has_pending` is true, the worker performs OCR at the configured capture interval even when the image thumbnail is static; this supplies the required second identical observation. Once a source is committed, the existing static-frame optimization resumes. Settings changes, region changes, explicit retries that invalidate the worker snapshot, and worker restarts reset stabilization state together with the existing frame and text caches.

## Data Flow

1. The UI publishes the overlay's current rectangle or `None`.
2. The worker captures the selected region and masks the padded overlay intersection.
3. If the masked frame changed, or stabilization has a pending candidate, the worker runs OCR.
4. The stabilizer classifies the OCR text as `wait`, `translate`, or `unchanged`.
5. `wait` produces no UI update. `unchanged` refreshes the current overlay. `translate` calls the existing translation service.
6. A successful translation commits the source text and updates the overlay. A failed translation remains uncommitted and follows the existing retry schedule.

## Error Handling and Lifecycle

- Geometry publication is best-effort UI state; invalid or non-overlapping rectangles are ignored safely.
- Mask coordinates are clipped before NumPy slicing, avoiding negative-index wraparound or out-of-bounds writes.
- OCR and translation errors continue to use the existing `EngineError` and retry behavior.
- Revision checks remain authoritative: results from an old settings revision are discarded and cannot commit stabilizer state.
- Stopping or reconfiguring the worker clears pending candidates so text captured under old settings cannot be translated later.

## Testing Strategy

### Overlay-mask tests

- Geometry changes are published after overlay show, hide, move, and resize.
- A resized text overlay updates the worker rectangle without waiting for fade completion.
- Padding is applied and clipped at every capture boundary, including negative desktop coordinates.
- A hidden or non-overlapping overlay does not alter captured pixels.
- Overlay pixels are masked before frame-change detection and OCR.

### Stabilizer tests

- The first observation waits and the second identical observation translates.
- Progressive prefix growth retains the original timer and translates the latest value at 2.0 seconds.
- A materially different candidate starts a new timer.
- A candidate that disappears after one observation is translated.
- An exact repeat of committed source returns unchanged.
- A strict trailing suffix of committed source cannot replace the overlay.
- Translation failure does not commit the source and remains retryable.
- Pending state forces OCR on a static frame; committed state restores the static-frame optimization.
- Reconfiguration and worker restart clear pending state.

The complete test suite will run after each task, with focused tests added alongside the existing worker and overlay tests.

## Acceptance Criteria

- Moving, resizing, showing, hiding, or changing overlay text cannot expose overlay pixels to OCR on the next capture.
- A stable subtitle is translated only after its second identical OCR observation.
- A progressively revealed subtitle is translated no later than 2.0 seconds after the first related observation.
- A short-lived subtitle is still translated from its last observed non-empty text.
- A trailing fragment of the last translated source never replaces the full translation.
- Existing retry, revision-safety, configuration, translation-cache, and UI tests continue to pass.
