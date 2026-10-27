# Game controls design

## Intent and agreed behavior

Control Translate HUD while playing games with a small floating toolbar, Windows global shortcuts, and a system tray. Existing PyQt5 application and translation pipeline remain authoritative.

- Stopped: horizontal icon-only toolbar, in order Play, Select region, Open full app, Exit.
- Running: collapse to the Play icon with a slowly rotating outer ring. The triangle stays still. Clicking the collapsed button stops translation and restores all four actions.
- Drag either presentation freely; release keeps the exact position, without snapping to screen edges. Dragging must not click Stop.
- No hide-subtitles action.
- Worker failure must expand the toolbar and stop its animation; a pending internal restart must not show a false stopped state.
- User asked for AGY CLI with Opus to implement, task checkboxes updated as work completes, controller review and a final local commit.

## Approaches and implementation choice

1. Extend the existing PyQt5 app with a separate toolbar, QSystemTrayIcon, and Windows RegisterHotKey: shares worker lifecycle and existing capture geometry; avoids a second app or dependency. Selected by the controller under the user's instruction to proceed with planning and implementation.
2. External helper process / game injection: duplicates lifecycle and settings or requires game-specific integration. Rejected for this scope.

## Controller defaults (not explicit user choices)

- Initial toolbar near the primary work area's upper-right corner. Remember the last released global logical position using existing atomic config storage; recover to a visible work area only if a saved position becomes inaccessible. No ordinary-release snapping or clamping of a reachable position.
- Four 44px icon targets, existing dark palette and Lucide icons, tooltips and accessible names. Ring rotates at a modest fixed rate and stops when hidden/stopped; no external animation dependency.
- Ctrl+Alt+F8 toggles translation; Ctrl+Alt+F9 selects region. Fixed defaults for v1, visible in tooltips and tray menu; report registration conflicts without crashing. No global exit shortcut.
- Main window X hides it while tray exists; explicit Exit and existing Quit command terminate safely. If tray unavailable, X retains safe-quit behavior. Opening full app intentionally activates it; the floating toolbar does not activate the app during ordinary show/start/stop/drag.
- Selecting a region preserves running/stopped intent, previous controller visibility and toolbar position. Escape cancels without changing the region. Do not open the full app after selection started from the toolbar or shortcut. Ignore duplicate selector requests; quitting during selection must never restart workers.
- Tray menu provides equivalent Play/Stop, Select region, Open app, Exit actions; left click restores the toolbar, double click opens full app.
- Use observed worker state and restart intent, not an independent optimistic UI flag. Start failure (e.g. missing API key) keeps the four actions available and makes the error discoverable.

## Constraints, non-goals and limitations

- Windows first, PyQt5, ctypes Win32 APIs; no new runtime packages, keyboard hooks, admin-elevation requirement, game injection, or anti-cheat workarounds.
- Do not promise a normal desktop overlay will appear above every exclusive-fullscreen game. Document game/window mode compatibility as manual validation; no game tested means no claim of compatibility.
- Exclude toolbar from capture through existing Windows capture-exclusion helper. If exclusion fails, report clearly and prevent animated self-capture (hide floating controls while capturing, retaining tray/shortcut access); do not feed the rotating control into OCR.
- Existing subtitles, OCR languages, models, credentials, build outputs and unrelated user changes are outside scope.
- Keep planning/progress/report files in docs/plans only. Work in current checkout, preserving the user's dirty changes. Only the controller creates the final commit after reviewing and testing.

## Validation

Automated Qt tests with fake workers and injected Win32/tray functions cover UI state, drag-versus-click, negative monitor coordinates, selector reentry/cancel/quit, hidden controller restoration, tray absence, registration conflict and cleanup. Existing worker-status/lifecycle tests must remain green. A fake-worker native GUI smoke can check rendering without OCR, API or desktop capture. Real game compatibility, exclusive fullscreen, physical monitor topology and native global key delivery require separate manual evidence.

## Reference

Windows hotkey contract: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey (WM_HOTKEY, MOD_NOREPEAT, conflict return value, unregister on cleanup).
