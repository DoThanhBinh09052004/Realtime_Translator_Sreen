# Dialogue context QA

Dialogue context is **opt-in**. In AI settings enable **Giữ ngữ cảnh hội thoại**. Select subtitle mode and an AI provider, then include both the character label and dialogue in each OCR region when available. Google Translate and blocks keep their normal translation paths. Each subtitle region has separate memory; labels in another region are not joined automatically.

Try a three-person exchange: A addresses the teacher; the teacher answers A; B addresses the teacher; A then addresses B. Check the translated text itself for the correct direction of address. Unknown or missing labels may remain ambiguous. A name mentioned as a third person does not prove who is being addressed. The app does not guarantee correct pronouns from insufficient OCR evidence.

One source turn creates a candidate relationship. Two distinct source utterances can support it; repeating a request, retrying, restarting on the same utterance, and appending text do not independently confirm it. Conflicting forms suspend the previous default. Previous translated pronouns are style samples, never source evidence. No character presets, images, extra analysis request, or persisted relationship database are used.

**Bắt đầu hội thoại mới** clears all regions of the current source, invalidates pending results, and scans the current text again. Use it when changing games inside one emulator or monitor capture: the app cannot reliably detect that transition. Stop/start on the same source retains bounded knowledge in RAM, while old runtime results are rejected. Changing provider/model/endpoint, language, source identity, overlay mode or the context toggle resets semantic memory. A changed window crop clears scene history; desktop crop changes reset conservatively. After 120 seconds without nonempty dialogue, scene history expires. Closing the app discards memory.

A provider returning plain text, invalid metadata or malformed JSON switches to translation text with recent context for the rest of that service session. The settings status explains this without an API-key warning. Valid translation text is retained when metadata is invalid; malformed/truncated JSON is withheld. There is no second API call to repair JSON. Normal transport retries retain the exact dispatched snapshot.

## Automated/offline checks

Run tests with an external writable TEMP as described in the implementation progress ledger; pytest protects real config, credentials, capture and network. The integration harness uses the real coordinator, dialogue session, bounded translation worker, service, parser and overlay, with fake OCR observations and SDK transport.

Run an offline diagnostic report from the repository root:

```powershell
.\.venv\Scripts\python.exe -m tools.evaluate_dialogue_context offline --output scratch/context-evaluation
```

The corpus contains 30 original English/Japanese cases, 150 turns. Output includes `events.jsonl`, `summary.json`, blinded per-turn `review-pairs.json` and a separate `review-key.json`. Offline transport returns conspicuously marked fake text: its output proves pipeline operation, **not semantic translation quality**. Request wall time and real stable-signal-to-overlay-presentation time are measured through production signals. OCR sampling uses logical times; capture-to-overlay is N/A. Token usage is N/A when the transport supplies none. Do not compare fake transport timing against live acceptance targets.

`--cadence-ms 500` feeds turns on a fixed real cadence without waiting per result, using the same production queue. Use it separately from sequential quality replay to examine dropped/late work. It still is a transcript input, not recorded capture latency. Actual capture-to-overlay requires recorded/live capture timestamps plus `Overlay.translation_presented`; selection receipts alone do not prove visible pixels.

## Live evaluation gate

No live benchmark has been run for this implementation. Agree provider, model and budget before using:

```powershell
.\.venv\Scripts\python.exe -m tools.evaluate_dialogue_context live --provider "OpenAI" --model "<chosen-model>" --allow-network --max-requests 900 --runs 3 --output scratch/context-live
```

The flags are mandatory before credentials are loaded. Keys come from the existing configured provider, never CLI arguments. The request ceiling is checked before every transport call; it is not an absolute monetary ceiling when thinking/output usage or pricing is unknown. A full 150-turn corpus × baseline/context × three repetitions requires at least 900 successful calls, before retries. Outputs are explicit diagnostic artifacts under scratch; the app does not automatically dump memory.

Review the blinded translations for both variants against the source and corpus notes. In `review-pairs.json`, fill `correct_A`/`correct_B` with booleans (leave unreviewed turns null); optionally fill `initial_error_A/B` and `propagated_error_A/B`. Keep the separate variant key hidden until review is finished. Then run:

```powershell
.\.venv\Scripts\python.exe -m tools.evaluate_dialogue_context score --output scratch/context-live
```

This produces `scored-summary.json`, unblinding scores by variant and splitting ambiguous/unambiguous and independent/context-dependent cohorts. Correctness and propagation remain null without human annotations; regex matches are not scores. Candidate/supported/conflicted relation counts come from final selected memory snapshots, not gold metadata. Report counts and statistical limitations as well as percentages. Scoring does not itself assert that the live release gate passed.

Release targets: context-dependent accuracy +15 percentage points, or at least half the remaining errors if baseline exceeds 85%; no degradation when baseline is perfect; independent accuracy loss at most 3 points; real stable-to-overlay P95 increase at most 20%; no extra successful-path calls. Keep `context_enabled=False` until live semantic and runtime gates have evidence for the chosen provider/model. No conclusion extends automatically to every Custom API.

For UI QA, render at 480 px width with Windows fonts; checkbox and secondary reset button must remain readable, unsupported reasons must wrap, unsaved API-key/model edits must survive context status updates. Verify stop/start, unavailable/rebind, resize and reset during requests without deadlock or changing the selected capture source.
