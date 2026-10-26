# Game controls verification

## Expected interaction

The floating control bar has four icon-only actions: start/stop translation, select capture region, open full app, and exit. Tooltips identify each action. When translation runs it collapses to the stationary Play icon with an animated outer ring. Click the compact button to stop and restore the full bar. Dragging must never trigger a click, stop translation or snap to an edge.

Default Windows shortcuts:

| Shortcut | Action |
| --- | --- |
| Ctrl+Alt+F8 | Start/stop translation |
| Ctrl+Alt+F9 | Select capture region |

Shortcut conflicts must be reported and must not prevent use through the toolbar or tray. There is no global exit or subtitle-hide shortcut.

If Windows cannot exclude floating controls from capture, the bar stays hidden during an active translation session. Use the tray menu or Ctrl+Alt+F8 to stop; it becomes available again afterward.

Closing the full window hides it when the tray is available. Exit from the toolbar/tray/sidebar ends the application after safely stopping workers. Without a tray, closing the full window retains safe exit behavior.

Selection preserves the prior running/stopped intent and main-window visibility. Escape keeps the previous capture region. Duplicate selection requests must not create multiple selectors; quitting while selecting must not restart translation.

## Automated validation

Run feature tests with `.venv\Scripts\python.exe -m pytest tests/test_game_toolbar.py tests/test_global_hotkeys.py tests/test_game_controls.py tests/test_game_controls_lifecycle.py -q` and the full suite with `.venv\Scripts\python.exe -m pytest tests -q`.

Tests inject native registration and tray behavior, disable live capture/network through the existing fixtures and do not reserve real global shortcuts. Use a writable TEMP/TMP directory outside the repository so test configuration remains isolated. Exact command results belong in docs/plans/2026-10-26-game-controls-results.md.

## Manual checklist — record evidence before marking complete

- [ ] Native desktop: icons, tooltips, ring, expanded and compact layout render correctly at 100%, 150% and 200% DPI.
- [ ] While a different app owns keyboard focus, each registered shortcut fires once per press; held keys do not repeatedly toggle.
- [ ] A reserved shortcut reports conflict; the other shortcut, toolbar and tray remain usable.
- [ ] Toolbar shows without unexpectedly activating the full app; Open app intentionally activates it.
- [ ] Drag from the running button moves it, preserves the running session, and keeps the exact released position.
- [ ] Restart app: last reachable global position is restored. After disconnecting a monitor and restarting, an inaccessible saved position recovers to a visible work area. Live hotplug does not automatically reposition the bar.
- [ ] Test monitor left of primary, above primary and mixed DPI; compact/expanded transitions preserve the toolbar anchor.
- [ ] Start/stop repeatedly while translation requests are in flight; no false running animation after fatal failure or unintended restart.
- [ ] Select from hidden controller, cancel with Escape, repeat hotkey while selecting, and quit while selecting; verify visibility/session intent.
- [ ] Toolbar inside capture region: confirm it is excluded. Simulate unsupported/failed display affinity: controls hide during capture and remain reachable by tray/shortcut.
- [ ] Tray click restores controls, double-click opens the app, explicit Exit removes tray/hotkeys and drains workers.
- [ ] Game windowed mode: verify capture, subtitle, toolbar and shortcuts.
- [ ] Game borderless-fullscreen mode: verify capture, subtitle, toolbar, shortcuts and focus.
- [ ] Game exclusive-fullscreen mode: record game, graphics API, Windows version, capture/overlay/shortcut behavior independently.

These are separate compatibility checks. A topmost desktop toolbar does not constitute evidence that all exclusive-fullscreen games are supported. No game injection or anti-cheat workaround is included.
