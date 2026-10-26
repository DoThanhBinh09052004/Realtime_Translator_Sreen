# Game Controls Final Review

## Status: No blocking findings

Read-only code review of the new Game Controls feature across `ui/game_toolbar.py`, `ui/global_hotkeys.py`, `ui/game_controls.py`, `ui/region_selection.py`, `main.py`, and `ui/controller.py`, alongside their test suites (`tests/test_game_toolbar.py`, `tests/test_global_hotkeys.py`, `tests/test_game_controls.py`, `tests/test_game_controls_lifecycle.py`).

No actionable high or medium defects remain. All six previous review findings (canonical start/stop resume, fake hotkey isolation guard, terminal selection closed flag with session generation guard, selector factory error recovery, overlay visibility preservation, and failed-save error discoverability) are correctly resolved and verified.

---

## Core Verification Summary

1. **Canonical Start/Stop and Selection Resume**:
   - Toggle routes strictly through `controller.start_ocr` and `controller.stop_ocr`.
   - Missing API keys keep toolbar expanded, ring stopped, and reveal the controller error view (`ai_page.highlight_missing_key()`).
   - Region selection resumes via `controller.start_ocr(preserve_translation_session=True)`, ensuring controller status (`"Đang hoạt động"`), starting hook, and worker agree.
   - Previous controller visibility is preserved; if controller was hidden prior to selection, it remains hidden after finish or cancel.

2. **Shutdown and Callback Lifecycle Isolation**:
   - `RegionSelectionLifecycle.close()` sets a terminal `_is_closed = True`, clears active state, and disconnects selector signals.
   - `_session_generation` increments on every selection, rejecting late signals from prior cancelled or completed selectors.
   - `GameControls.shutdown()` cleanly disconnects event filters, unregisters Win32 hotkeys, hides tray icon, and closes toolbar idempotently.
   - Subsequent or queued actions after shutdown are rejected by explicit guards.

3. **State Queue Ordering**:
   - `GameControls._queue_state_sync()` queues state evaluation via `QTimer.singleShot(0, self.sync_state)` to the next GUI event-loop turn.
   - Synchronous `revision_changed` or `finished` signals during internal restarts do not cause false stopped presentation or reset the rotating ring animation.
   - While selection is active (`_is_selecting = True`), queued stopped state synchronizations keep the toolbar hidden.

4. **Windows Native Messages**:
   - Win32 API functions (`RegisterHotKey`, `UnregisterHotKey`) in `Win32NativeApi` use pointer-safe ctypes definitions with `wintypes.HWND`, `ctypes.c_int`, and `wintypes.UINT`.
   - `HotkeyNativeEventFilter` handles both `b"windows_generic_MSG"` and `b"windows_dispatcher_MSG"`, safely translating message addresses via `wintypes.MSG.from_address(addr)`.
   - Handled `WM_HOTKEY` returns `(True, 0)` to consume the message, while unhandled or non-hotkey messages return `(False, 0)`.
   - Partial registration success unregisters only registered IDs on cleanup; repeat `close()` is idempotent.

5. **Self-Capture Fallback & Pre-Start Ordering**:
   - `ControllerWindow.starting_translation` signal fires after start validation and strictly before `worker.start_worker()`.
   - If `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` fails (`is_capture_excluded is False`), `_on_pre_start` hides the floating toolbar before capture frames are acquired.
   - Single-click tray activation while running under exclusion failure refuses to reveal the toolbar, preventing self-capture OCR loops.
   - `QEvent.WinIdChange` re-evaluates display affinity if Qt recreates the native window handle.

6. **Focus, Drag, and Test Isolation**:
   - `GameToolbar` specifies `Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.WA_ShowWithoutActivating` and `Qt.NoFocus` on buttons, preventing keyboard/window focus theft from games.
   - Event filtering on child buttons intercepts drag gestures beyond `startDragDistance`, suppressing click events and preserving raw global coordinates (including negative multi-monitor spaces). Dragging over the collapsed button moves the toolbar without stopping translation.
   - Lifecycle test suite enforces hotkey isolation via `guard_no_real_native_api` autouse fixture, preventing real native API registration during automated tests.

---

## Untested Game & Native Limitations

Controller qualification: this review established code-level findings only. Native compatibility below remains unverified; do not infer a requirement to elevate the application from the use of RegisterHotKey.

1. **Exclusive Fullscreen Mode (DirectX / Vulkan)**:
   - No live game was tested. Topmost Qt window flags alone do not establish exclusive-fullscreen compatibility. Validate each game/window mode separately; no universal compatibility claim is made.
2. **Elevated (Administrator) Game Processes**:
   - Native key delivery with an elevated game in focus was not tested. The earlier blanket UIPI/elevation claim was not established by this review and is withdrawn; this feature does not introduce an administrator requirement.
3. **Capture Exclusion Prerequisites**:
   - Existing capture-exclusion helper validates Windows build 19041+ and checks API success. Actual driver/capture behavior and the fallback were not exercised against live capture in this review.
4. **Dynamic Monitor Topology Changes**:
   - Saved positions are validated against connected screens on launch. Live monitor hotplug does not automatically reposition controls; startup recovery is the implemented behavior.
