# Windows OCR bundle

The one-folder release bundles offline English (`en`) and Japanese (`japan`) OCR only. Translation through Google/API providers still requires a network connection. Source checkouts without `assets/ocr` retain PaddleOCR's normal model behavior; invalid staging and frozen missing/unsupported models fail with an actionable, nonretryable error.

## Prepare and build

Use Windows x64 and Python 3.10. Keep the development `.venv` unchanged:

```powershell
uv venv --python 3.10 .venv-build
uv pip sync --python .venv-build/Scripts/python.exe requirements-build.lock
uv pip check --python .venv-build/Scripts/python.exe
.venv-build/Scripts/python.exe tools/prepare_ocr_models.py --source-cache <prepared-cache-root> --output scratch/ocr-assets
./tools/build_windows.ps1 -PythonPath .venv-build/Scripts/python.exe -ModelDir scratch/ocr-assets
```

The preparation command requires an explicit cache root with the five pinned model directories listed in `core/ocr_models.py`, plus dictionaries and LICENSE from installed PaddleOCR 2.10.0. It never imports Paddle or downloads. In an online development environment, initialize PaddleOCR 2.10.0 separately for `lang='en'` and `lang='japan'` with `ocr_version='PP-OCRv4'` to populate that cache before preparation. Do not run that online preparation inside pytest or the release executable. An existing staging directory is never overwritten; choose a fresh output path to regenerate it.

Preparation writes SHA-256 hashes and package/model provenance. Review `assets/ocr/manifest.json`; weights are ignored by Git. The copied code LICENSE notice does not establish separate redistribution rights for model weights. The build validates every required model, dictionary, classifier, hash and logo before PyInstaller. Its application-data allowlist excludes config, credentials, `.env`, user caches, MORT and videos. Package dependencies still contribute their own runtime data through PyInstaller hooks.

The script resolves input paths before changing directory and restores its environment. It uses `SPECPATH`, so invocation from another cwd and Unicode/space-containing model paths is supported. Defaults produce `dist/main/main.exe`; use `-DistPath <fresh-output> -WorkPath <fresh-work>` to preserve an existing build. UPX is disabled. The frozen application reads `_internal/assets/ocr` and keeps configuration/DPAPI storage behavior unchanged.

## Verification and release gate

Default tests use fake assets and Paddle constructors under the offline/capture guards in `tests/conftest.py`. Run them with fresh TEMP/TMP and pytest basetemp under a granted writable directory; do not call real model preparation from pytest.

Before release, copy the complete one-folder output to a clean Windows VM under a path containing spaces and Japanese characters. Use a regular user, a read-only application directory, no `.paddleocr` cache and disabled networking. Verify logo, independent English/Japanese fixture OCR, language switch, Stop/Start, no cache/bundle writes, and responsive actionable failure for Chinese/Korean. Remove one classifier file from a disposable copy and verify the same nonretryable error without download. Record screenshots, startup timings, size and exit status. Translation failing offline does not invalidate OCR; diagnostic OCR output must prove recognition separately.

Native results and limitations for this run are recorded in `docs/plans/2026-10-26-ocr-bundle-report.md`. A successful unit suite alone does not clear the clean-VM release gate. Multiple installed OpenCV distributions remain a known dependency overlap; this change does not claim to resolve it.

The Windows lock additionally constrains albumentations to 1.3.1: fresh resolution of 1.4.15 imported albucore and failed on an undeclared Torch runtime requirement. The constraint matches the working development environment and keeps runtime `requirements.txt` unchanged. Measured staged OCR assets for this run: 18 manifest entries, 30,244,078 bytes including manifest. Build excludes transient `__pycache__`/bytecode files from collected package data.

Use a short build output prefix on Windows: deeply nested Paddle package headers can exceed MAX_PATH under long custom DistPath values. The default repository dist is shorter; this run preserved existing dist using a fresh scratch output.

Measured build for 2026-10-26: PyInstaller completed in 342.787s under `scratch/b4dist-20261026/main`; 9,480 files and 901,505,001 bytes total (main.exe 24,932,930 bytes). All 18 bundled manifest file hashes validate and bundled logo exists. Isolated locked environment performed English/Japanese native OCR with socket/DNS blocked. Clean-VM frozen offline/read-only/cache-empty verification remains required before release; the current artifact is a build-validation result.

Root final packaged startup QA: PASS on host with ordinary AppData permissions, foreign cwd, expected main window, WM_CLOSE and exit0; no OCR/capture/API was started in that GUI check. Initial restricted sandbox run was blocked by configuration-save modal; a Default IME diagnostic false match was corrected in the harness. This does not replace clean-VM offline/read-only/cache-empty verification. Raw result: docs/plans/2026-10-26-packaged-startup.json.

Fresh Git checkouts contain the tracked release manifest but not ignored model weights. Default source OCR therefore uses legacy PaddleOCR model/cache resolution until actual weight payloads are present. Prepare into a new path such as scratch/ocr-assets (not the metadata-only assets/ocr directory), and pass that same path to -ModelDir; the frozen destination remains _internal/assets/ocr. Explicit/frozen roots and partial/corrupt payload staging remain strict.
