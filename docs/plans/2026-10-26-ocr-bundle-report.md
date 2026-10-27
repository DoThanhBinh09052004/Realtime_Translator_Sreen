# OCR bundle implementation report — 2026-10-26

Status: source implementation and focused tests complete; isolated native build in progress. Clean Windows VM release smoke remains unverified.

Implemented manifest/hash/path validation, atomic preparation of five pinned model sets plus two dictionaries/license, bundled-path runtime resolution, nonretryable missing/unsupported frozen OCR errors, build data allowlist/logo, cwd-independent spec and PowerShell preflight, isolated Windows/Python 3.10 hash lock and operator documentation. Existing source `.venv`, build/dist, AppData and DPAPI code were not changed.

TDD evidence:
- Asset RED: `tests/test_ocr_model_assets.py` collection failed with missing `core.ocr_models`; GREEN: 12 PASS.
- Runtime RED: 6 failures/1 pass (missing model kwargs, constructor called for invalid frozen assets, missing resolver integration); GREEN targeted assets/runtime/spans/worker status/app paths: 37 PASS.
- Layout RED: missing `tools.bundle_layout`; GREEN all three new files: 22 PASS.
- `git diff --check` on owned production changes: exit 0.

Real assets: preparation using existing cache and installed PaddleOCR 2.10.0 metadata exited 0. `assets/ocr/manifest.json` contains actual SHA-256 and model/package provenance, no absolute cache/user paths. Weights ignored, notice/dictionaries/classifier included. No downloads needed for models.

Build environment: `uv venv --python .venv/Scripts/python.exe .venv-build` succeeded, CPython 3.10.22. `uv pip compile --python .venv-build/Scripts/python.exe requirements-build.txt --generate-hashes --output-file requirements-build.lock` succeeded. Initial default uv cache access denied; retry used fresh granted TEMP/TMP/UV_CACHE_DIR. Package synchronization still running at interim report time; probing during installation is not native import evidence. Runtime requirements unchanged.

Build script has optional DistPath/WorkPath in addition to planned arguments, enabling actual build validation without replacing existing dist/main. Defaults remain dist/main/main.exe. Real build, measured size, version/import diagnostics and native OCR outcomes will be appended. No claim of clean VM or release completion is made.

Review limitation: `resolve_ocr_models` was initially added with Task 1 implementation before runtime-specific RED; runtime engine integration itself has observed RED/GREEN. Explicit-root read-only/cwd behavior test therefore passed its first observed run. This is a TDD sequencing deviation, disclosed rather than claimed as observed RED.

Review correction: default source nonbundled languages must retain legacy behavior even when EN/JP staging exists. Added actual-source-root regression: RED 1 failure (Chinese raised OcrModelError), then resolver fallback correction; `pytest tests/test_ocr_bundle_runtime.py tests/test_ocr_model_assets.py` GREEN 20 PASS. Frozen and explicit-root remain strict.

Isolated dependency diagnostics: original resolution installed albumentations 1.4.15/albucore 0.2.20; native PaddleOCR import failed because albucore required missing Torch. Existing working development environment uses albumentations 1.3.1 without importing albucore. Added only build constraint albumentations==1.3.1, regenerated hash lock, synced 72 packages; uv pip check PASS. Runtime requirements unchanged. Actual versions: PaddleOCR 2.10.0, PaddlePaddle 2.6.2, PyInstaller 6.22.3, numpy 2.2.6, opencv-python 4.13.0.92, contrib/headless 5.0.0.93. OpenCV overlap remains.

First PyInstaller attempt failed before Analysis: collect_all harvested a transient `paddle/distributed/communication/stream/__pycache__/send.cpython-310.pyc.<id>` that disappeared. Excluded bytecode/cache paths from collected datas; fresh build restarted after source fallback fix. Existing build/dist untouched.

Latest focused verification after review correction: 41 PASS in 5.08s for bundle layout, assets, runtime, app paths, OCR spans and worker status UI. Isolated native PaddleOCR import PASS with albumentations1.3.1/albucore0.2.20. Root owns final integrated suite and fixture OCR evidence.

Root integration verification: 670 PASS in 65.44s after source fallback correction, final reviewer reports source spec/quality PASS and addressed source-language finding. Root host native fixture OCR blocked socket/DNS before import: English `Hello worlg` and Japanese `日本語の翻訳テスト`, expected-fragment checks passed. Raw evidence is `docs/plans/2026-10-26-native-ocr-evidence.json`; this establishes native model operation on this host, not clean-VM/frozen executable validation. External-cwd real asset preflight returned 20 allowed data tuples.

Second attempt reached executable creation and COLLECT, then hit Windows MAX_PATH while copying Paddle's deep include header under long visualization-root dist prefix. Re-running build script with short fresh `scratch/b4dist-20261026` output and same isolated work directory; standard existing dist/main still preserved. This is an output-path limitation, not an OCR model failure. Keep build output prefixes short on Windows unless long-path policy is enabled.

Root additionally verified actual OCR through isolated locked .venv-build with socket/DNS denied before imports: both EN/JP succeeded, init+inference 2.625s / 2.156s. Evidence: docs/plans/2026-10-26-isolated-native-ocr.json. Short output longest Paddle include destination measured by root at 223 characters (<260).

## Final build result

PASS: `tools/build_windows.ps1 -PythonPath .venv-build/Scripts/python.exe -ModelDir assets/ocr -DistPath scratch/b4dist-20261026 -WorkPath <isolated visualization run>/build` completed, script exit 0; PyInstaller build log reports 342.787 seconds. Output executable is `scratch/b4dist-20261026/main/main.exe`. Existing `dist/main` and `.venv` preserved. Native artifact: 9,480 files, 901,505,001 bytes total; executable 24,932,930 bytes. Postbuild validation of `_internal/assets/ocr` succeeded for all 18 manifest entries; `_internal/ui/logo.png` exists. Final owned-file `git diff --check` exit 0.

Successful build log: visualization run `ocr-native-build-226da2afd7e3426291f367c6230cb00c/build-short.log`. Root is performing hidden executable startup QA. A second complete build from outside cwd was not performed; instead real-asset preflight from external cwd and automated cwd-independence tests passed. Full clean-VM offline/read-only/cache-empty GUI matrix remains unverified and is the release gate. No staging, commits, audit edits or model downloads performed by this worker.

Executable startup QA follow-up: root's first hidden host run from foreign cwd did not observe expected controller within 50 seconds; process remained alive and was stopped by its owned PID. stdout/stderr were empty (windowed bootloader). This is inconclusive/failed startup QA, not launch success. Root is enumerating all process windows to distinguish a modal error from import/startup latency. Independent diagnosis: isolated source `import main` passes in ~6 seconds; no OCR model initialization occurs before controller display; required physical PaddleOCR dynamic-import source files are bundled. No production edits justified yet, and no executable-launch claim is made.

Root final packaged startup QA: PASS on host with ordinary AppData permissions, foreign cwd, expected main window, WM_CLOSE and exit0; no OCR/capture/API was started in that GUI check. Initial restricted sandbox run was blocked by configuration-save modal; a Default IME diagnostic false match was corrected in the harness. This does not replace clean-VM offline/read-only/cache-empty verification. Raw result: docs/plans/2026-10-26-packaged-startup.json.
