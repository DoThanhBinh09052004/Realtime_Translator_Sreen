# Game controls results

## Delivered behavior

- Four draggable icon actions while stopped: start translation, select region, open app, exit.
- Running collapses to a stationary Play triangle with a rotating outer ring; click stops and expands. Dragging the actual child icon moves without firing Stop. No edge snapping.
- Windows Ctrl+Alt+F8 toggles translation; Ctrl+Alt+F9 selects region. Registration conflicts report an actionable error and successful registrations are released during cleanup.
- Tray actions share controller/worker state. X hides the full window only when a tray is available; explicit Exit follows safe worker shutdown.
- Selection preserves running/pending intent and hidden main-window state. Resume uses the controller so its status agrees with the worker. Cancellation, failed save, duplicate selection, stale callbacks and shutdown have dedicated coverage.
- Capture exclusion reuses the existing helper. If unavailable, floating controls hide before canonical capture start and stay hidden during the session; tray/shortcuts remain available.

## Execution and review

User requested AGY CLI implementation and a final controller review/commit. Initial Opus work exhausted quota. User explicitly selected Gemini 3.8 continuation; AGY Gemini High/Medium/Low sessions completed the scoped work. Controller verified actual files and tests rather than trusting agent completion messages.

Controller review caught and required fixes for child-icon dragging, focus/timer cleanup, unconnected capture fallback, queued restart state, selection/teardown guards and a real selection-resume status mismatch. The latter was independently reproduced using a real ControllerWindow and fake worker, then rechecked after correction.

All unit tests use fake native APIs/hotkeys/tray. Lifecycle tests include a guard against constructing a real Win32NativeApi. No live OCR, translation calls or desktop capture are needed for automated validation.

## Verified evidence

- Existing baseline before feature: **679 passed in 66.63s**, exit 0.
- Controller Task 1 check: **31 passed in 0.33s**, exit 0; explicit child-button events additionally verified exact 30px movement, one position notification and no toggle.
- Controller Task 2 check after fixes: **58 passed in 0.63s**, exit 0.
- Controller full working-tree suite: `.venv\Scripts\python.exe -m pytest tests -q --tb=short` — **753 passed in 66.08s**, exit 0. This includes four preexisting user background tests outside the feature commit.
- Controller offscreen GUI smoke with a real ControllerWindow, fake worker, fake hotkeys/tray and fake selector: start/stop passed; cancelling selection resumed with status `Đang hoạt động`; hidden main window stayed hidden. Component screenshots inspected for the expanded bar and compact ring. Explicit Segoe UI loading was needed for text in the offscreen QA renderer; product font settings were not changed.
- Staged-source verification: exported 170 indexed source/data files to an isolated QA directory (excluding old build artifacts, ignored model payloads and user changes), then ran the full suite from that directory: **749 passed in 63.88s**, exit 0. The four-test difference from the working tree is the user's existing uncommitted background tests.
- Fresh final review: AGY Gemini 3.8 Flash High reported no blocking high/medium code findings. Controller qualified unverified native compatibility statements; no administrator requirement or universal fullscreen compatibility is claimed.
- Local commit: `feat: add compact game controls and global shortcuts` created on develop. Completion records included in that same commit; no push. Git history contains its final hash.

## Limits

Real game compatibility, exclusive fullscreen, native global key delivery, display-affinity behavior during actual capture, physical multiple monitors/DPI and clean-machine packaging were not run. The manual checklist remains unchecked in docs/testing/game-controls.md. A topmost Qt widget is not a promise of universal exclusive-fullscreen support.

Saved-position recovery runs at startup. Live monitor hotplug does not automatically reposition the toolbar.

This change is source code and tests. The previous executable/build outputs, OCR weights, dependencies and unrelated user changes were not rebuilt or bundled into the commit.
