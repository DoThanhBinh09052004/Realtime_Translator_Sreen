# Monitor geometry implementation report — 2026-10-26

## Scope and interfaces

Implemented the approved 2026-10-25 subtitle monitor geometry plan. Task 1 produces `preset_position(QRect, QSize, str)` and `clamp_position(QRect, QSize, QPoint, margin=10)`; Task 2 consumes those exact Qt logical-coordinate interfaces. Pre-flight found no conflict between them.

Created `ui/subtitle_geometry.py`, `tests/test_subtitle_geometry.py`, `tests/test_subtitle_monitor_ui.py`, and `docs/testing/subtitle-monitor-geometry.md`; changed geometry-only behavior in `ui/overlay.py` after root explicitly released ownership. Preserved PlainText and the preexisting alpha-background painting changes.

## Behavior

Preset coordinates include the full availableGeometry origin. Clamp uses exclusive global edges, an independent 10px margin per axis when it fits, and origin anchoring for oversize axes. Minimum preset dimensions remain 200x40. The overlay selects the screen containing its pre-layout frame center, then a still-present widget screen, then primary. Width limits use 75% of that work area without DPI multiplication. Translation layout preserves the previous center/bottom anchor before clamping; drag enable restores an offscreen position without emitting persistence signals.

## Test evidence

All runs used `.venv/Scripts/python.exe -m pytest`, `-q -p no:cacheprovider`, with a fresh `geometry-<guid>` TEMP/TMP and basetemp under the permitted visualization root outside the repository.

1. Pure-helper RED: collection failed with the expected missing `ui.subtitle_geometry` module.
2. Pure-helper GREEN: 15 passed.
3. Integration RED: 9 failed for the old wrong-origin placement, stale width, and missing `_available_geometry`.
4. Geometry GREEN: 24 passed.
5. Focused regression GREEN: 57 passed in 6.72s, covering geometry, monitor UI, overlay masks, Google subtitle overlay, subtitle background, worker status UI, and subtitle PlainText.
6. `git diff --check -- ui/overlay.py ui/subtitle_geometry.py tests/test_subtitle_geometry.py tests/test_subtitle_monitor_ui.py`: clean.

## Rulings and limits

- Root coordinates the final whole-suite run once sibling workers finish; this worker did not run a competing full suite.
- Root requested no staging, commits, shared audit edits, or child agents, so the plan's commit and fresh-review steps are delegated to root rather than executed here.
- Added explicit valid/removed widget-screen fallback tests and independent per-axis margin cases beyond the plan's minimum list.
- One additional margin test oracle was corrected before implementation: a 1065px window in a 1080px area leaves 15px for the exclusive bottom bound when the 10px margins do not fit.
- Native multi-monitor, taskbar, Windows layered-window and 100%/150% DPI smoke were not run. Offscreen fake-monitor tests do not establish those properties; the pending checklist records them explicitly.

No commits or staging performed. No capture geometry, block renderer, configuration schema, or render revision/sequence behavior changed.
