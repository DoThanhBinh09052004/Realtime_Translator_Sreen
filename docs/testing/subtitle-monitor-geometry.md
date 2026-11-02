# Subtitle monitor geometry verification — 2026-10-26

Automated verification uses Qt's offscreen platform with fake logical monitor work areas. It does not establish native Windows multi-monitor or DPI behavior.

## Automated checks performed

- Fixed preset oracles: right/left/above monitors, negative x/y, taskbar-offset work area, legacy minimum preset dimensions.
- Exclusive-edge clamping, independent margins, oversized-window anchoring.
- Real Overlay layout/movement with patched available work areas: long Japanese/Vietnamese subtitles, changing monitor width, offscreen custom position recovery on update and drag enable.
- Monitor selection before resize; screenAt, valid widget-screen fallback, removed-screen fallback to primary; logical geometry unchanged at fake ratios 1.5 and 2.0.
- Existing overlay mask, Google subtitle, background, worker status, and PlainText regressions: 57 passed together.

## Native Windows smoke checklist — not run

- [ ] Right secondary monitor, apply every preset and update to a long subtitle.
- [ ] Left secondary monitor with negative x, apply presets and drag.
- [ ] Monitor above primary with negative y, update Japanese/Vietnamese text.
- [ ] Taskbar on top and left: confirm offsets are applied once.
- [ ] 100% / 150% scaling across monitors: confirm width and margins stay logical.
- [ ] Drag overlay across monitors, then update short and long subtitles.
- [ ] Disconnect the monitor holding a custom position; update and enable drag on remaining screen.
- [ ] Check click-through, fade, background alpha and text appearance on native layered windows.

Native results remain pending. No desktop capture or physical monitor test was performed in this run.
