# Game Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add draggable compact game controls, system tray and Windows global shortcuts without regressing translation lifecycle.

**Architecture:** Passive GameToolbar emits actions; GameControls owns toolbar, tray and hotkeys and routes to the existing controller and region-selection lifecycle. TranslationWorker remains the single authority for running/restart state.

**Tech Stack:** Python, PyQt5, existing Lucide provider, ctypes Windows APIs, pytest/pytest-qt.

**Spec:** docs/plans/2026-10-26-game-controls-design.md

## Global Constraints

- Preserve all existing dirty files; do not commit, reset, stash or delete unrelated changes.
- No new runtime packages or game injection. Windows-first; platform-safe imports and injected native APIs in automated tests.
- Only icon buttons: Play/Stop, Select region, Open app, Exit. No subtitle-hide action.
- Running collapses to stationary Play triangle with rotating outer ring; click stops, drag never stops. No snapping.
- Preserve toolbar top-left through expand/collapse unless otherwise needed to recover a genuinely inaccessible position.
- Use docs/plans for all plan/progress/report artifacts, and update checkboxes only after actual verification.
- Implementation via AGY CLI: originally claude-opus-4-6-thinking; switched to gemini-3.8-flash-high with explicit user authorization after Opus quota exhaustion. Controller alone stages/commits once final checks pass.

## Review Focus

1. Worker dies during initialization or has a queued previous finished signal: controls follow current state/restart intent.
2. Drag initiated over the collapsed action: threshold must suppress activation even if Qt release arrives over the button.
3. Selection cancelled, requested twice, or active during quit: no unwanted app activation or worker restart.
4. Hotkey conflict, missing tray, WinId change and teardown: recoverable error, no leaked registrations or unreachable app.
5. Toolbar overlaps OCR region or moves to negative coordinates: no animated self-capture and no accidental primary-screen snapping.

## Task 1: Floating toolbar widget

**Files:** Create ui/game_toolbar.py, tests/test_game_toolbar.py; modify ui/icons.py only if a missing icon is required.

**Interfaces:** GameToolbar(QWidget) exposes toggle_requested, region_requested, open_requested, quit_requested and position_released(int, int) signals; set_running(running: bool), set_busy(busy: bool). It does not call the worker or save config itself.

- [x] Write failing Qt tests: stopped has four visible icon-only actions; running has one Play action and active ring; stopped stops ring and expands at unchanged top-left; accessible names/tooltips reflect actual action.
- [x] Add failing drag tests using Qt drag distance: clicking emits toggle once; dragging over collapsed button emits position but no toggle; negative global coordinates stay unchanged; busy blocks actions appropriately.
- [x] Implement the passive frameless translucent topmost non-activating widget with 44px targets, dark palette, existing Lucide icons, timer/custom paint ring and mouse handling that differentiates drag from click.
- [x] Run `.venv\Scripts\python.exe -m pytest tests/test_game_toolbar.py -q`; record exact result below.
- [x] Controller reviews task against spec and code quality before accepting it.

**Evidence:** Controller verified 31 passed in 0.33s (exit 0). Independent child-icon event probe verified exact 30px movement, one position notification, no toggle, no-focus flags, and hidden timer stop/resume. Review findings 1–4 resolved.

## Task 2: Global shortcuts and tray coordinator

**Files:** Create ui/global_hotkeys.py, ui/game_controls.py, tests/test_global_hotkeys.py, tests/test_game_controls.py.

**Interfaces:** GlobalHotkeys(QObject) emits toggle_requested, region_requested and error_occurred(str), exposes start() and close(); native API injected for tests. GameControls receives app/controller/worker and selection/quit callbacks; exposes toolbar and shutdown(); coordinator can block actions during selection/quitting. Keep interfaces small; document any justified signature adjustment in the report.

- [x] Write failing injected Win32 tests for F8/F9 registration with Ctrl+Alt+MOD_NOREPEAT, WM_HOTKEY routing, unknown IDs, conflicts, partial success cleanup, repeat close and unsupported-platform behavior. Never register real global keys in unit tests.
- [x] Implement pointer-safe Win32 signatures, QAbstractNativeEventFilter dispatch on GUI thread, unique IDs, explicit unregistration and filter cleanup. A conflict leaves the other action available and gives an actionable error.
- [x] Write failing coordinator tests for toolbar/tray routing through controller methods, failed start remaining expanded, internal restart and fatal finish, tray absence, capture-exclusion failure fallback, save-position failure and hidden animation cleanup.
- [x] Implement coordinator with QSystemTrayIcon menu, single-click restore/double-click full-app behavior, atomic persisted position via existing config, current-screen recovery, capture exclusion and actionable error reporting. Do not add an exit hotkey or subtitle-hide control.
- [x] Run `.venv\Scripts\python.exe -m pytest tests/test_global_hotkeys.py tests/test_game_controls.py tests/test_game_toolbar.py -q`; record result.
- [x] Controller reviews task against spec and code quality before accepting it.

**Evidence:** Controller independently verified 58 passed in 0.63s (exit 0). Reviewed all seven fixes. Task 3 owns canonical pre-start fallback ordering and selection visibility integration, including the exact queued-restart regression.

## Task 3: Application lifecycle and selection integration

**Files:** Modify main.py and ui/controller.py; create tests/test_game_controls_lifecycle.py. Additional focused lifecycle module is allowed if it makes main.py callbacks independently testable.

**Interfaces:** Existing ControllerWindow constructor stays compatible (optional new arguments allowed). Add an explicit public state notification or equivalent centralized state adapter so all entry points update toolbar/tray consistently. start_ocr/stop_ocr remain canonical user actions. Safe existing quit callback remains canonical teardown.

- [x] Write failing tests for selecting while running/stopped, Escape, failed save, duplicate request, hidden main-window restoration, and quit during selection. A hidden controller stays hidden after selection; only prior running intent resumes.
- [x] Write failing tests that X hides to available tray, X without tray safely quits, explicit Quit always drains workers, missing-key start does not collapse toolbar, and stale finished during pending restart does not expand it.
- [x] Integrate controls after controller setup; connect shared action/state routes. Initialize toolbar without auto-starting OCR. Shutdown hides/cleans toolbar, tray and hotkeys, closes any selector and drains worker exactly once.
- [x] Refactor region-selection callbacks only as needed to preserve UI visibility/running intent and guard reentry/quit; ensure saving a new region still uses existing settings coordinator and geometry synchronization.
- [x] Run `.venv\Scripts\python.exe -m pytest tests/test_game_controls_lifecycle.py tests/test_worker_status_ui.py tests/test_worker_block_lifecycle.py tests/test_google_worker_lifecycle.py tests/test_controller_behavior.py -q`; record result.
- [x] Controller reviews task against spec and code quality before accepting it.

**Evidence:** Controller reviewed all six fixes; full workspace suite passed 753 tests in 66.08s, exit 0. Independent real-controller/fake-worker GUI smoke confirmed start/stop, correct status after cancel/resume, and hidden-main preservation. Tests guard against real Win32 registration.

## Task 4: Final review, validation and commit

**Files:** Create docs/testing/game-controls.md; update this plan with evidence and docs/plans/2026-10-26-game-controls-results.md with implementation decisions and limitations.

- [x] Document shortcuts, toolbar transitions, dragging, tray close/exit behavior, error paths and manual game/fullscreen/multimonitor checklist. Do not check manual tests that were not run.
- [x] Run all feature tests plus full `.venv\Scripts\python.exe -m pytest tests -q`; record counts, exit code and any environmental limitation.
- [x] Perform a fake-worker GUI rendering smoke without live OCR/API/capture; inspect screenshot if available, record scope precisely.
- [x] Fresh reviewer reads feature diff, design and tests; controller resolves significant findings and reruns affected checks.
- [x] Controller reviews staged diff, excludes preexisting changes (especially ui/overlay.py and scratch deletions), runs git diff --cached --check and creates one scoped local commit; no push.

**Evidence:** Full workspace 753 passed in 66.08s; exact staged-source snapshot 749 passed in 63.88s (both exit 0). Real-controller/fake-worker start/stop/cancel smoke passed. Fresh review has no blocking findings. Scoped local commit created; completion record amended into that same commit. No push.

## Execution progress

- 2026-10-26: Design/plan prepared from agreed interaction. User explicitly requested plan then AGY Opus execution and commit; no further requirements interview. AGY CLI discovered at C:\Users\Admin\.gemini\bin\agy.exe; available model claude-opus-4-6-thinking confirmed using `agy models` with normal user credential access. This was the initial preflight state; current completion is recorded in the checked tasks above.
- Ruling: Preserve existing region-selection resume intent because the user requested execution before answering that optional detail; avoids changing existing behavior.
- Ruling: Use current checkout to preserve user work and provide the requested reviewable local commit; agents may edit only scoped feature files and may never commit independently.
- Baseline: 679 tests passed in 66.63s, exit 0. Sandbox default Temp was not writable; set TEMP/TMP to C:\Users\Admin\.codex\visualizations\2026\10\25\01a1734a-77f0-7383-b4aa-34f65c30681f\game-controls-tmp (outside repo, as test-isolation checks require).
- Preflight Opus review: no blockers. Controller rejected S1 after verifying existing ui/capture_exclusion.py helper; use it. Accepted selection reentry/visibility/quit concerns; already owned by Task 3.
- Task 1 interrupted: Opus hit RESOURCE_EXHAUSTED/429 before completing its report or checklist. Controller independently ran feature suite: 26 passed in 0.38s, exit 0; manual event probe still reproduced broken child-button dragging. At that point the task was not accepted. Subsequent Gemini fixes and controller verification resolved these findings; Task 1 is now accepted.
- User authorized Gemini 3.8 continuation; use the available Gemini 3.8 Flash family for subsequent implementation (High initial repair, Medium Task 2, Low scoped repairs/integration). No blind retry of exhausted Opus quota.

### Preflight interface scan

| Scope | Check | Ruling |
| --- | --- | --- |
| Task 1 | Passive widget tests and signals match widget deliverable | Consistent; no worker/config imports |
| Task 2 | Native API injected, no real hotkeys in unit tests | Consistent; conflicts are recoverable |
| Task 3 | Canonical controller actions and preserved selection intent | Consistent; optional constructor additions only |
| Task 4 | Documentation, full suite, scoped commit | Consistent; manual game tests remain unchecked |
| Tasks 1/2 | Signals and set_running/set_busy are coordinator inputs | Exact public interface shared |
| Tasks 2/3 | Coordinator callbacks and centralized controller state | Resolve signature in report, preserve current callers |
| Tasks 1/3 | State presentation is driven by controller/worker | No independent optimistic toolbar flag |
| Tasks 1/2/4 | Icon UI and test names | Same ui/game_toolbar.py and feature test paths |

- Final validation: all four tasks complete. Controller review, 753 workspace tests, 749 exact staged-source tests, GUI smoke, scoped diff checks and local commit completed. Native/game manual checklist remains separate and unchecked.
