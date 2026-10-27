# Windows English/Japanese OCR Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo bản Windows one-folder kèm OCR tiếng Anh/tiếng Nhật, không phụ thuộc cache model hoặc username của máy build.

**Architecture:** Chuẩn bị một model staging nhỏ với manifest có hash từ cache đầu vào được chỉ định. Module runtime xác thực asset và cấp đường dẫn tường minh cho PaddleOCR; spec chỉ bundle file đã liệt kê và logo. Build chạy trong môi trường riêng có dependency lock; smoke native offline là cổng phát hành.

**Tech Stack:** Windows x64, Python 3.10, PaddleOCR 2.10.0, PaddlePaddle 2.6.2, PyInstaller 6.22.3, PowerShell, pytest.

**Spec:** `docs/plans/2026-10-25-remaining-fixes-design.md`, mục B4; finding B4 trong audit cùng ngày. Người dùng chọn đóng gói sẵn **English và Japanese**, không phải cả bốn ngôn ngữ.

## Global Constraints

- Đọc ràng buộc chung, model layout và harness Test-Plan trong spec; code mới không hard-code username hoặc ổ đĩa máy build.
- "OCR offline chỉ kèm `en` (English) và `japan` (Japanese). Google/API AI vẫn cần mạng để dịch."
- "Bản frozen chọn ngôn ngữ chưa kèm hoặc thiếu model trả `EngineError('ocr_model_missing', ..., False)`"; không tải/fallback âm thầm.
- Giữ one-folder `dist/main/main.exe`, `console=False`; không thêm installer, ký số hoặc auto-update.
- Phải kèm detector en/ml, recognizer en/japan, classifier chung và dictionary như spec. Classifier không được bỏ chỉ vì `use_angle_cls=False`.
- Source không có staging giữ cách PaddleOCR hiện tại; frozen luôn dùng bundle. Không ghi vào resource hoặc đổi AppData/DPAPI.
- Không bundle `.env`, `config.json`, credential, cache người dùng, `MORT/` hoặc video; không sửa runtime dependency để tiện build mà chưa có bằng chứng.
- Các test mặc định không tải model, không import Paddle thật hoặc gọi dịch. Asset thật và smoke không nằm trong suite mặc định.

## Review Focus

- Máy đích không có cache `.paddleocr` và không có mạng vẫn phải OCR được English/Japanese.
- Thiếu classifier/dictionary hoặc file rỗng/corrupt phải bị phát hiện trước khi Paddle tự tải.
- Đường dẫn có khoảng trắng/Unicode và cwd ngoài repository không làm lệch resource.
- Ngôn ngữ chưa kèm phải báo lỗi dễ hiểu, không nhận dạng sai bằng model khác.
- Thư mục cài read-only và manifest có đường dẫn thoát root không được gây ghi vào bundle hoặc copy file ngoài danh sách.

---

## File Structure

| File | Vai trò |
|---|---|
| Create `core/ocr_models.py` | Catalog model, manifest validation và resolver; không import PaddleOCR |
| Create `tools/prepare_ocr_models.py` | Copy bộ model từ source cache chỉ định và dictionary của package đã pin |
| Create `tools/bundle_layout.py` | Danh sách datas được phép vào bundle |
| Modify `engines/ocr.py:14–23,104–111` | Truyền đường dẫn model/dictionary và ánh xạ lỗi missing assets |
| Modify `main.spec:1–40` | Dùng root spec và datas đã kiểm tra, giữ one-folder |
| Create `requirements-build.txt`, `requirements-build.lock` | Công cụ build pin và lock trên Windows/Python 3.10 |
| Create `tools/build_windows.ps1` | Preflight và chạy PyInstaller bằng interpreter chỉ định |
| Modify `.gitignore` | Ignore `.venv-build/` và trọng số staging; giữ manifest có thể track |
| Create `tests/ocr_asset_helpers.py` | Factory asset giả đúng schema, dùng chung các test mới |
| Create `tests/test_ocr_model_assets.py`, `tests/test_ocr_bundle_runtime.py`, `tests/test_bundle_layout.py` | Kiểm chứng pipeline asset, runtime và allowlist bundle |
| Create `docs/testing/windows-ocr-bundle.md` | Hướng dẫn chuẩn bị/build/smoke, số đo thực và kết quả |

## Model source layout đã xác định

Đầu vào `source_cache` là root `.paddleocr` được cung cấp bằng CLI, không tự tìm home. Copy các cặp file `inference.pdmodel`/`inference.pdiparams`, kèm `.pdiparams.info` nếu có:

| Nguồn tương đối dưới source_cache | Đích staging |
|---|---|
| `whl/det/en/en_PP-OCRv3_det_infer` | `det/en` |
| `whl/det/ml/Multilingual_PP-OCRv3_det_infer` | `det/ml` |
| `whl/rec/en/en_PP-OCRv4_rec_infer` | `rec/en` |
| `whl/rec/japan/japan_PP-OCRv4_rec_infer` | `rec/japan` |
| `whl/cls/ch_ppocr_mobile_v2.0_cls_infer` | `cls` |

Dictionary lấy từ package PaddleOCR 2.10.0 qua `importlib.metadata.distribution('paddleocr').locate_file(...)`, không import package chỉ để tìm đường dẫn: `paddleocr/ppocr/utils/en_dict.txt` và `paddleocr/ppocr/utils/dict/japan_dict.txt`. `dictionary_root` là thư mục `ppocr/utils`; test fake root giữ cùng cấu trúc con. Copy thêm `paddleocr/LICENSE` thành staging `NOTICE.paddleocr.txt` qua đường dẫn metadata riêng. Tool ghi provenance phiên bản/tên model và SHA-256 file thật; từ chối nguồn thiếu, không suy đoán thư mục tương đương. Các URL model đối chiếu trong package đã được ghi ở spec; executor không đổi model version để làm hết lỗi.

### Task 1: Chuẩn bị và xác thực bộ asset tối thiểu

**Files:** Create `core/ocr_models.py`, `tools/prepare_ocr_models.py`, `tests/ocr_asset_helpers.py`, `tests/test_ocr_model_assets.py`.

**Interfaces:**
- Produces frozen dataclass `OcrModelPaths(det: Path, rec: Path, cls: Path, dictionary: Path)`.
- Produces `OcrModelError(Exception)` với thông báo sạch, hướng dẫn chọn English/Japanese hoặc cài lại gói đầy đủ; không đưa home/cache path vào thông báo người dùng.
- Produces `validate_ocr_assets(root: Path) -> dict`: đọc manifest schema trong spec, kiểm tra versions/languages đúng, đủ các path bắt buộc, file nonempty, hash đúng, path tương đối POSIX không chứa `..`/absolute và file resolve nằm trong root; trả manifest khi hợp lệ, raise OcrModelError khi sai. Không tạo/sửa file.
- Produces `prepare_models(source_cache: Path, output: Path, dictionary_root: Path, *, license_path: Path) -> dict`: output chưa tồn tại; copy đúng bảng nguồn/đích cùng notice, tạo manifest, validate; raise khi thiếu/đích đã tồn tại, không ghi đè cache/đích cũ.
- CLI: `python tools/prepare_ocr_models.py --source-cache PATH --output PATH`; root dictionary được resolve bằng metadata nói trên. Thành công exit 0 và in manifest path; thất bại exit 2 với lý do, không khởi tạo Paddle.
- Test helper `make_assets(root: Path) -> Path`: tạo đủ file giả nonempty, notice, manifest hash thật từ bytes giả; `make_source_cache(root: Path) -> tuple[Path, Path, Path]` trả cache root, dictionary root, license path giả theo bảng để test tool. Test mới import từ `ocr_asset_helpers` trong test directory theo pytest prepend mode hiện có. Không thêm helper test vào production.

- [ ] **Step 1: Viết test có oracle nội dung/side effect.** `test_prepare_copies_only_en_japan_models`: cache giả thêm `unrelated/secret.txt`; prepare; assert languages `['en','japan']`, đủ 5 cặp model + 2 dict, không có secret, bytes nguồn không đổi. `test_prepare_fails_without_classifier` xóa classifier input; assert OcrModelError và không có manifest hợp lệ ở output. `test_prepared_assets_support_unicode_paths` dùng `tmp_path/'Bản dựng Nhật 空白'`; prepare/validate thành công. `test_validation_rejects_incomplete_or_corrupt_assets` tham số hóa thiếu `.pdmodel`, thiếu dict Nhật, file rỗng, file sai bytes, schema/version sai. `test_validation_rejects_paths_outside_root` dùng entry `../outside.txt` hoặc absolute; assert lỗi trước khi đọc file đó. `test_prepare_never_overwrites_existing_output` assert file sentinel giữ nguyên. Thêm `test_validation_is_read_only`: snapshot bytes/mtime trước/sau validate giống nhau.
- [ ] **Step 2: Chạy RED.** `Test-Plan -Targets @('tests/test_ocr_model_assets.py')`; xác nhận thiếu module/API dự kiến.
- [ ] **Step 3: Implement các interface.** Dùng hashlib/json/pathlib/shutil; copy vào staging tạm cạnh output, validate rồi publish output chỉ khi toàn bộ hợp lệ. Không recursive delete/move target chưa xác minh nằm trong staging được tạo bởi tool. Không tải mạng và không extract tar trong tool này. Copy notices đi kèm nguồn, ghi provenance manifest; không tự suy diễn điều kiện phân phối model.
- [ ] **Step 4: Chạy GREEN.** Cùng lệnh; tất cả test PASS, không cần model thật.
- [ ] **Step 5: Commit.** `git add core/ocr_models.py tools/prepare_ocr_models.py tests/ocr_asset_helpers.py tests/test_ocr_model_assets.py`; `git commit -m "build: stage validated English and Japanese OCR assets"`.

### Task 2: Runtime frozen dùng asset tường minh và không tải ngầm

**Files:** Modify `core/ocr_models.py`, `engines/ocr.py`; Create/Test `tests/test_ocr_bundle_runtime.py`.

**Interfaces:**
- Consumes: Task 1 dataclass/error/validator và staging layout.
- Produces `resolve_ocr_models(lang: str, *, root: Path | None = None) -> OcrModelPaths | None`: explicit root bắt buộc hợp lệ; default frozen lấy `Path(sys._MEIPASS)/'assets'/'ocr'`; source lấy repo-relative `assets/ocr`, trả None nếu staging chưa có. Frozen thiếu staging hoặc lang ngoài en/japan raise OcrModelError. Source không staging giữ tất cả ngôn ngữ hiện có.
- `SimplePaddleOCR.__init__(lang='en')` giữ signature; khi resolver có kết quả, truyền `det_model_dir`, `rec_model_dir`, `cls_model_dir`, `rec_char_dict_path`, `ocr_version='PP-OCRv4'` và các cờ CPU/angle/log cũ vào PaddleOCR.
- `ocr_image(img, lang='en') -> OcrResult` bắt OcrModelError trước catch Exception, trả lỗi code `ocr_model_missing`, retryable False; không nuốt thành lỗi OCR retryable chung.

- [ ] **Step 1: Viết regression qua fake Paddle ctor và ocr_image thật.** `test_frozen_en_and_japan_use_bundled_paths` tham số hóa `en/japan`, fake `sys.frozen=True`, `_MEIPASS=tmp_path`, helper tạo assets đúng vị trí; patch `engines.ocr.PaddleOCR` bằng ctor ghi kwargs; assert det en/ml, rec en/japan, cls chung và dict đúng dưới bundle, giữ `use_angle_cls=False`, `cpu_threads=2`, `enable_mkldnn=False`. Patch socket guard như suite; không gọi Paddle thật. `test_frozen_missing_asset_never_constructs_paddle` xóa classifier; `ocr_image(np.zeros((20,20),dtype='uint8'),'en')` trả code/lỗi nonretryable, ctor sentinel không được gọi. `test_frozen_unsupported_language_is_actionable` cho `ch/korean`: không ctor, không fallback, user_message có English/Japanese. `test_source_without_staging_keeps_legacy_ocr` sys.frozen False và mock resolver root mặc định chưa tồn tại: ctor nhận lang japan, không cần model_dir, OCR fake vẫn có kết quả. `test_read_only_bundle_needs_no_cache_write` spy filesystem write/mkdir trên model root và requests/socket bằng guard: resolver/ctor nhận asset hợp lệ, không có write. `test_explicit_root_does_not_depend_on_cwd` chdir tmp khác, resolve với root có Unicode; path đúng.
- [ ] **Step 2: Chạy RED.** `Test-Plan -Targets @('tests/test_ocr_bundle_runtime.py')`; lỗi thiếu resolver hoặc kwargs/báo lỗi chưa đúng. Conftest hiện fake Paddle nên test phải patch ctor ở `engines.ocr`, không import package thật.
- [ ] **Step 3: Implement resolver và ghép engine.** Resource frozen chỉ đọc bundle; source fallback chỉ khi không có staging, không bỏ qua staging hỏng. Validate trước ctor, tránh `maybe_download` thấy classifier thiếu. Không thay `get_ocr_engine` cache contract hoặc bỏ single-engine release.
- [ ] **Step 4: Chạy GREEN/regression.** `Test-Plan -Targets @('tests/test_ocr_model_assets.py','tests/test_ocr_bundle_runtime.py','tests/test_ocr_spans.py','tests/test_worker_status_ui.py','tests/test_app_paths.py')`; mong đợi PASS.
- [ ] **Step 5: Commit.** Chỉ stage ba file task này. Commit `fix: use bundled OCR models without runtime downloads`.

### Task 3: Build có đường dẫn di động và xác minh native

**Files:** Create `tools/bundle_layout.py`, `tools/build_windows.ps1`, `requirements-build.txt`, `requirements-build.lock`, `tests/test_bundle_layout.py`, `docs/testing/windows-ocr-bundle.md`; Modify `main.spec`, `.gitignore`.

**Interfaces:**
- Consumes Task 1 validator/manifest; Task 2 frozen resource layout.
- Produces `bundle_data(project_root: Path, model_root: Path) -> list[tuple[str, str]]` trong `tools/bundle_layout.py`: validate assets và logo; source là absolute path, destination là directory tương đối bundle; chỉ manifest, file model/dictionary/NOTICE.paddleocr.txt có trong manifest và `ui/logo.png`. Giữ destination `assets/ocr/<parent>` cho model, `ui` cho logo. Manifest cũng được copy.
- Script `tools/build_windows.ps1 -PythonPath PATH -ModelDir PATH`: derive project root từ `$PSScriptRoot`, resolve cả input relative trước đổi cwd; set env `TRANSLATEHUD_OCR_MODELS_DIR` trong process; gọi interpreter đó chạy preflight, rồi `-m PyInstaller --clean --noconfirm --distpath <root>/dist --workpath <root>/build <root>/main.spec`; nonzero được propagate; không tự pip install và không xóa dist tùy ý.
- Spec resolve `project_root=Path(SPECPATH).resolve()` do PyInstaller cung cấp, import helper từ root, `ModelDir` lấy từ env hoặc `<root>/assets/ocr`; không dùng cwd/home; `upx=False` để không thêm dependency UPX. Giữ collect_all hiện cần thiết, bỏ/điều chỉnh hiddenimports chỉ nếu native build chứng minh module không còn tồn tại; không thêm module đoán mò.
- `requirements-build.txt`: `-r requirements.txt` và `pyinstaller==6.22.3`; lock sinh trong môi trường Windows/Python 3.10. `.gitignore` thêm `.venv-build/`, `assets/ocr/**`, ngoại lệ `!assets/ocr/manifest.json`; model weights là release artifact, không commit bằng `git add .`.

- [ ] **Step 1: Viết test layout.** `test_bundle_data_includes_models_manifest_and_logo` tạo project giả có logo/model assets; assert từng file manifest có tuple source/dest đúng, có manifest và logo. `test_bundle_data_ignores_user_files` thêm `.env`, config, secret, video ngoài assets; assert không tuple nào chứa chúng. `test_bundle_data_missing_logo_or_model_fails_preflight` tham số hóa lỗi, assert OcrModelError/ValueError trước khi build. `test_bundle_data_independent_of_cwd` chdir một tmp khác và dùng absolute project/model root; kết quả giống trước chdir. Dùng helper Task 1, không assert spec chứa một chuỗi source nhất định.
- [ ] **Step 2: Chạy RED.** `Test-Plan -Targets @('tests/test_bundle_layout.py')`; mong đợi thiếu helper layout.
- [ ] **Step 3: Implement helper/spec/script/dependency/docs.** Script lưu/khôi phục env/cwd bằng try/finally, `ErrorActionPreference='Stop'` và kiểm tra `$LASTEXITCODE`. Tài liệu mô tả đúng chỉ English/Japanese, nguồn cache/dictionary cần chuẩn bị, đường dẫn Unicode và chưa tải model ngầm. Ghi cách tạo model cache trước build trong môi trường dev có mạng, giữ riêng việc này với chạy executable và pytest.
- [ ] **Step 4: Chạy GREEN và toàn suite.** `Test-Plan -Targets @('tests/test_bundle_layout.py','tests/test_ocr_model_assets.py','tests/test_ocr_bundle_runtime.py','tests/test_app_paths.py')`, sau đó `Test-Plan`. `git diff --check -- main.spec engines/ocr.py core/ocr_models.py tools/bundle_layout.py tools/build_windows.ps1`. Mong đợi exit 0.
- [ ] **Step 5: Tạo build env riêng và lock, không sửa .venv đang dùng.** Từ repo root chạy `uv venv --python 3.10 .venv-build`; `uv pip compile --python .venv-build/Scripts/python.exe requirements-build.txt --generate-hashes --output-file requirements-build.lock`; `uv pip sync --python .venv-build/Scripts/python.exe requirements-build.lock`; `uv pip check --python .venv-build/Scripts/python.exe`. Lưu versions OpenCV/Paddle thực vào tài liệu. Nếu resolve/import/native OCR lỗi, chẩn đoán dependency trước khi thay pin; không đánh dấu build đạt bằng test giả. Có thể tiếp tục ở lỗi user-code liên quan; thay runtime dependency ngoài B4 cần làm rõ phạm vi.
- [ ] **Step 6: Chuẩn bị asset thật và build.** Chạy `.venv-build/Scripts/python.exe tools/prepare_ocr_models.py --source-cache <cache-root-đã-chuẩn-bị> --output assets/ocr`; đầu vào là đường dẫn máy executor thực, không ghi username đó vào source. Review manifest SHA/provenance. Chạy `tools/build_windows.ps1 -PythonPath .venv-build/Scripts/python.exe -ModelDir assets/ocr`; mong đợi exit 0 và `dist/main/main.exe`. Chạy lại script từ một cwd khác với input absolute để chứng minh không lệch root. Ghi build size thực; không ước đoán thay số đo.
- [ ] **Step 7: Smoke Windows sạch trước kết luận phát hành.** Copy toàn bộ thư mục dist/main sang VM/máy sạch có path chứa khoảng trắng và tiếng Nhật, cài app folder read-only cho user thường; cache `.paddleocr` của user test chưa có, ngắt mạng. Mở executable, kiểm tra logo, chọn English OCR ảnh mẫu có chữ đã biết, chuyển Japanese OCR ảnh mẫu độc lập, dừng/Start lại. Nhật ký có thể báo dịch mất mạng nhưng OCR không được tải/model error. Để phân biệt OCR/dịch, dùng capture/OCR diagnostic riêng ở dev khi cần; không coi dịch offline thất bại là OCR thất bại. Kiểm tra không tạo cache model mới hoặc ghi bundle. Chọn Chinese/Korean phải báo lỗi chọn English/Japanese, UI còn phản hồi. Xóa một classifier của bản copy test: lỗi rõ, không download. Ghi ảnh/test matrix/size/thời gian khởi tạo/exit; nếu thiếu môi trường sạch thì ghi chưa kiểm chứng và không tuyên bố release hoàn tất.
- [ ] **Step 8: Commit phần build.** Stage đúng các file mới và spec; dùng `git add -f -- docs/testing/windows-ocr-bundle.md assets/ocr/manifest.json` chỉ sau khi đã review manifest. Không add weight/dist/cache. `git diff --cached` không có key/cấu hình người dùng; commit `build: package offline English and Japanese OCR for Windows`. Cập nhật finding B4 audit với giới hạn kiểm chứng thật.

## Self-Review

- Năm Review Focus lần lượt thuộc Task 2 + native smoke Task 3; classifier/dict/corruption/path traversal thuộc Task 1; Unicode/cwd thuộc Task 1 và Task 3; ngôn ngữ thiếu thuộc Task 2. Không chỉ test mock construction để kết luận offline: native smoke là bắt buộc.
- ModelPaths/error/validator do Task 1 định nghĩa, Task 2 và Task 3 dùng lại đúng tên; bundle destination khớp resolver `_MEIPASS/assets/ocr`.
- Tải lần đầu UX, thêm ngôn ngữ, giải quyết triệt để cv2 overlap, installer và CI đa nền tảng không thuộc kế hoạch này.
