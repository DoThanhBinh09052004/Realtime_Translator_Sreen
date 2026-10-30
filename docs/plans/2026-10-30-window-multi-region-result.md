# Window capture / multi-region implementation result

Source implementation authorized and completed on 2026-10-30. Packaging work was paused at the user's request before this commit.

- Window Graphics Capture by HWND/PID/process identity, MSS desktop source, normalized ROI and exclusion regions.
- Independent OCR scan/retry state and translation tracking per region, bounded shared translation queue, source-to-overlay geometry mapping.
- Source picker, preview/editor, atomic settings persistence, explicit invalid-profile recovery, monitor topology handling and runtime/preview shutdown coordination.
- Final full suite: **1057 passed in 156.23 seconds**, no failures or skips. Evidence retained locally in `scratch/capture-task7-review-full.log`.
- Production native adapter: owned-window basic **12/12** and resize/minimize/restore lifecycle **14/14** checks passed on the interactive host. Sandbox graphics capture is restricted.
- Independent final review: four P2 findings fixed (DPI subtitle masks, Start during preview, Stop intent, stale resized preview); focused re-review **9 passed**, no outstanding P1/P2 findings.
- Offscreen synthetic editor/source-picker images were visually checked. Unit tests use fake frames/providers and do not imply game OCR accuracy or API latency.

Not claimed: a completed final frozen-app preview acceptance run, real-game testing, exclusive fullscreen/HDR/protected-content support, a physical mixed-DPI display matrix, clean-VM release acceptance, or native performance benchmarks. The source commit is ready for normal development use; packaging and those acceptance checks can be resumed separately.
