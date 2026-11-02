# Window capture feasibility probe

`tools/probe_window_capture.py` captures only two Qt windows that the probe owns.
They initially share a title and have different identity pixels plus four client
corner markers. The probe binds exact HWNDs and changes titles, moves, resizes,
minimizes, restores, holds content static, destroys the second HWND, and stops the
remaining capture. It never enumerates or selects a user's application.

Windows x64 build 19041 or newer and an interactive Windows desktop are required.
The native package and Qt are imported only when running the probe; `--help` and
argument parsing do not initialize capture. Duration is 6–300 seconds, default 10.
Exit 0 means every native check passed; exit 1 means a failed native gate, with
details in the JSON. Invalid command-line input exits 2.

## Isolated environment

Run from the repository root in PowerShell. These paths leave the normal app
environment unchanged. A workspace cache/temp directory avoids restricted sandbox
cache permissions.

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) 'scratch/capture-uv-cache'
$env:TEMP = Join-Path (Get-Location) 'scratch/capture-env-temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
uv venv --python .venv/Scripts/python.exe scratch/capture-probe-venv
uv pip sync --python scratch/capture-probe-venv/Scripts/python.exe requirements-build.lock
uv pip check --python scratch/capture-probe-venv/Scripts/python.exe
$env:QT_QPA_PLATFORM = 'windows'
scratch/capture-probe-venv/Scripts/python.exe tools/probe_window_capture.py --seconds 10 --output scratch/window-capture-probe.json
```

The lock now contains `windows-capture==2.0.1`; the original feasibility experiment
installed that candidate using `uv pip install --no-deps` after syncing the old
lock. No NumPy, Paddle, or OpenCV pin changed.

No images are saved by default. `--save-images` explicitly saves one successfully
mapped client PNG for each owned window beside the report. Do not run this flag
when only metadata is needed. JSON records physical DWM and client rectangles,
offsets, frame shapes and actual row strides, callback threads, frame timestamps,
marker checks, lifecycle stages, opening time, GUI heartbeat, and stop/drain time.

## Onedir smoke test

```powershell
scratch/capture-probe-venv/Scripts/python.exe -m PyInstaller --onedir --noconfirm --copy-metadata windows-capture --distpath scratch/capture-probe-dist --workpath scratch/capture-probe-build --specpath scratch tools/probe_window_capture.py
scratch/capture-probe-dist/probe_window_capture/probe_window_capture.exe --seconds 10 --output scratch/window-capture-probe-bundle.json
```

`--copy-metadata windows-capture` includes the distribution version used by the
probe's diagnostics. The extension `.pyd` is collected by PyInstaller. Keep the
spec, dist, build, temporary environments, and reports under `scratch/`.

For a stronger smoke test, launch the exe from its own directory with `PATH` set
to `C:\Windows\System32;C:\Windows` and `PYTHONHOME`/`PYTHONPATH` removed. Use an
absolute output path when changing the working directory. This excludes developer
tools from PATH; it is not equivalent to testing a fresh Windows installation.

## Interpreting results

The measured DWM capture size must equal the BGRA8 surface size. Client cropping
uses `GetClientRect` plus `ClientToScreen`; the probe never guesses a border width
or rescales a mismatched surface. NumPy slicing respects padded row stride.
Correct corner markers and window-specific center pixels must appear for both
HWNDs in initial, renamed, moved, resized, and restored phases. Restored native
timestamps must be newer than those before minimize. Static content may produce
zero callbacks; absence of a static callback is recorded and is not a failure.

Native start, stop, and wait run on the owner thread, separate from Qt's GUI event
loop. Native callbacks must also run off GUI. The report requires first frames
within 2 seconds, stop/drain within 3 seconds, a native close notification for the
destroyed HWND, and GUI heartbeat gaps below 0.5 seconds. The script does not call
thread termination or choose another window on failure.

On 2026-10-30 the Windows sandbox created valid Qt HWNDs but WGC failed with
`Failed to convert item to GraphicsCaptureItem`. An authorized run on the normal
interactive desktop passed, as did the onedir executable. A sandbox failure is
not evidence that the user's interactive capture path works or fails.

Contract tests use synthetic arrays only for tool validation/cropping. They are
not native capture evidence:

```powershell
$env:TEMP = Join-Path (Get-Location) ('scratch/probe-tests-' + [guid]::NewGuid().ToString('N'))
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.venv/Scripts/python.exe -m pytest -q tests/test_capture_probe_contract.py
```

The dated Task 0 report in `docs/plans/` records the exact measured scope. This
probe does not qualify games, protected content, HDR, exclusive fullscreen,
negative monitor origins, mixed DPI, or production adapter lifecycle behavior.

## Application release checks (2026-10-30)

The application uses the same locked `windows-capture==2.0.1` wheel. `main.spec`
collects its native extension and distribution metadata alongside the existing
OCR asset allowlist. The build environment contains 73 locked distributions;
the prior 72 package versions were preserved. The extension imports Windows
graphics/WinRT and VC runtime libraries and has no CLR dependency.

Run the release regressions and the full suite with TEMP/TMP outside this
checkout. A short pytest `--basetemp` under `scratch/` avoids Windows MAX_PATH
failures for deeply nested language-pack fixtures; collection-time config still
uses the external TEMP directory. Do not weaken `test_test_isolation.py`.

```powershell
$env:TEMP = 'C:\Users\Admin\.codex\visualizations\2026\10\29\01a187be-2073-74f1-8ea4-ee30c19c86c9\t7'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.venv/Scripts/python.exe -m pytest -q tests/test_capture_bundle.py tests/test_capture_regressions.py --basetemp=scratch/t7-targeted
.venv/Scripts/python.exe -m pytest -q --basetemp=scratch/t7-full
tools/build_windows.ps1 -PythonPath .venv-build/Scripts/python.exe -ModelDir assets/ocr -DistPath scratch/t7d -WorkPath scratch/t7b
```

Always choose fresh short build/output paths and preserve the existing `dist/`.
The regressions exercise absent native packages and dependent-DLL load errors
through the real lazy factory: desktop capture continues with an injected MSS
frame, and WGC returns a structured error. Spec execution checks that native hook
outputs reach PyInstaller's Analysis; this is supplemented by actual onedir
inspection, not treated as evidence of a working frozen native session.

The stress checks perform 100 native-adapter epochs, deliver every retired
frame/close callback after rebind, verify owner-thread stop/wait and buffer weak
references, and run 100 actual worker start/stop cycles with fake source/OCR.
Those checks establish lifecycle regressions, not a native memory/handle
benchmark. The dated Task 7 report records exact build, suite and smoke results.

For application smoke checks, verify the actual Qt data paths before launch,
remove provider keys and Python environment overrides, and never press Start.
Qt 5 on Windows uses known folders and does not isolate its data merely because
APPDATA/LOCALAPPDATA are changed. The vanilla executable is tested only in the
restricted process sandbox. A disposable QA-only frozen variant overrides
`core.paths.get_app_paths` before main imports for the interactive owned-window
preview check; it has identical application module bytecode and native payload,
with one extra isolation hook. The production spec/executable has no test flag
or hook. Keep these evidence scopes separate. Production adapter native evidence
is recorded separately in the dated Task 4 report.

Release acceptance still requires recorded manual results for 1/3/8 regions in
both overlay modes, window/borderless games, 100/125/150% DPI and negative desktop
origins, movement during held OCR, resize/cross-monitor/minimize/restore/close,
duplicate titles, process restart/reselection, monitor changes, capture exclusion
and user masks. Exclusive fullscreen, HDR and protected content are not promised.
No unperformed matrix cell should be marked PASS. Capture/copy/OCR latency,
scan age, request count, RAM and native handles after 30 cycles also require a
separate measured run on the same clip/crop; no performance SLA is inferred from
unit tests. To return to MSS, stop translation, choose the display source and
select its OCR regions; never substitute a desktop source silently after WGC loss.
