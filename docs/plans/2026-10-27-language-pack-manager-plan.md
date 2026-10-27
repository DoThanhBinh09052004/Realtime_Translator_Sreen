# OCR Language Pack Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select chỉ hiện ngôn ngữ OCR đã cài, thêm hành động quản lý để tải Chinese/Korean và gỡ gói tải thêm, giữ cách đổi nguồn trực tiếp hiện tại.

**Architecture:** Một registry ngôn ngữ cấp mapping cho config/OCR/Google; catalog artifact đã pin cấp dữ liệu cho kho component và transfer worker. Manager sống cùng app phát snapshot immutable; SettingsCoordinator giữ persist-before-apply, còn page/dialog chỉ render và phát intent. English/Japanese giữ trong bundle; gói tải thêm được cài theo transaction vào user data và dùng cùng resolver OCR.

**Tech Stack:** Windows x64, Python 3.10, PyQt5 5.15.11, PaddleOCR 2.10.0, PaddlePaddle 2.6.2, httpx 0.28.1, pytest/pytest-qt, PyInstaller one-folder.

**Spec:** `docs/plans/2026-10-27-language-pack-manager-design.md`. Đọc cả spec; các mặc định kỹ thuật trong đó cần review trước triển khai. Kế hoạch này thay phần “chưa quản lý tải thêm” của thiết kế bundle cũ, giữ các ràng buộc build/isolation còn liên quan.

## Global Constraints

- Windows x64; Python 3.10; PyQt5 5.15.11; PaddleOCR 2.10.0; PaddlePaddle 2.6.2; httpx 0.28.1. Không thêm dependency runtime.
- Giữ English/Japanese trong bundle, read-only và không thể xóa qua trình quản lý.
- Giữ config `source_lang`/`target_lang` dạng tên English/Japanese/Chinese/Korean/Vietnamese để tương thích; ID nội bộ độc lập với tên hiển thị.
- Chỉ gói xác thực đủ file, hash và tương thích mới xuất hiện trong select; file đang tải không phải gói đã cài.
- Không download, hash model lớn, giải nén, xóa thư mục hoặc khởi tạo Paddle trên GUI thread.
- Không có “Tải và bắt đầu”; tải xong không đổi source, không khởi động worker.
- Không ghi vào bundle, `.env`, config trong repo hoặc credential; mọi dữ liệu gói tải thêm ở user data.
- Unit/integration test dùng model giả, HTTP giả, config tạm và guard trong `tests/conftest.py`; native OCR/download thật là smoke riêng.
- Mọi spec/plan/progress của tính năng ở `docs/plans/` với tên có ngày; giữ nguyên thay đổi chưa commit của người dùng.
- Ô đích giữ Vietnamese/English; không tải model khi đổi target. Không thêm resume byte-range, nhập gói offline, tự cập nhật model hoặc nhiều engine OCR đồng thời trong đợt này.
- Tra CodeGraph trước khám phá/sửa; khi execution mới cân nhắc worktree theo skill, không tạo worktree chỉ để đọc kế hoạch. Chỉ stage từng file/hunk của task; không `git add .`.

## Review Focus

1. Config cũ lưu Chinese/Korean nhưng gói thiếu: không chọn giả English, không Start với model sai; có cách tải lại — Task 5/7.
2. Stop/đổi source/đóng dialog trong lúc tải rồi nhận progress/result cũ: không auto-start, không đổi ngược source, không mất tiến độ — Task 4/7.
3. Crash sau publish component nhưng trước installed marker, disk-full hoặc hủy sát commit: restart không nhận gói giả, không hỏng gói khác — Task 2/3.
4. Gỡ gói đang được OCR giữ lease hoặc có thành phần dùng chung, kể cả app instance khác: không xóa file đang dùng hay bundled — Task 2/4.
5. Bundle read-only, cwd ngoài repo, path Unicode/DPI cao và máy không có cache: resolver/UI đúng, model đã cài hoạt động offline — Task 2/6/8.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| Create `core/languages.py` | Registry immutable: ID/config name, Paddle/Google code, source/target/bundled, component mapping |
| Create `core/language_pack_contracts.py` | Value objects catalog/install plan/snapshot/error/progress/removal |
| Create `core/language_pack_catalog.py` | Parse/validate catalog và resource paths; không network/Paddle |
| Create `assets/ocr/language-packs.json` | Lock artifact HTTPS/versions/size/hash; không lặp mapping ngôn ngữ |
| Create `tools/pin_language_pack_catalog.py` | Authoring: pin URL/file/hash thật từ package 2.10.0 và upstream, thao tác riêng ngoài pytest |
| Create `core/language_pack_store.py` | Kho bền vững, readiness, component reuse, transaction/locks/lease/remove/recovery |
| Create `core/language_pack_transfer.py` | HTTP streaming, hủy, disk check, xác thực/giải nén/cài |
| Create `core/language_pack_manager.py` | QObject facade, QThread ownership, snapshot/progress và async shutdown |
| Modify `core/paths.py`, `core/ocr_models.py`, `engines/ocr.py` | User model root, resolver và lease engine trên OCR thread |
| Modify `core/config.py`, `engines/google_translate.py`, `core/worker.py` | Dùng registry, giữ config contract/revision và inject OCR reader |
| Modify `ui/controller_state.py`, `ui/settings_coordinator.py` | UI value objects, ready-source choices và persist-before-apply |
| Create `ui/widgets/package_status_row.py`, `ui/language_packs_dialog.py` | Row reusable và dialog chỉ render/signal |
| Modify `ui/pages/ocr_settings_page.py`, `ui/controller.py`, `ui/styles.py`, `main.py` | Action trong combo, mở manager, global style và composition/lifecycle |
| Modify `tools/prepare_ocr_models.py`, `tools/bundle_layout.py`, `.gitignore` | Stage/bundle catalog + dictionary đúng allowlist, không bundle trọng số tải thêm |
| Create tests nêu trong từng task; modify fixtures/UI boundary tests | HTTP/model/config giả, regression các interface cũ |
| Create `docs/testing/language-packs.md` | Hướng dẫn release/native smoke và bằng chứng thực |

`ui/widgets/cards.py` và `ui/icons.py` là dependency tái sử dụng, chỉ sửa nếu thực sự thiếu capability chung. Không tạo bản sao ModernCard/palette/icon helper.

## Test Harness và baseline

Đọc `docs/testing/isolation.md`. Trước Task 1, lấy baseline fresh bằng `.venv/Scripts/python.exe` với thư mục test được cấp quyền; không dùng con số PASS của cuộc rà soát trước. Helper dưới đây chỉ tạo data tạm, không cài model vào profile người dùng:

```powershell
function Test-LanguagePacks {
    param([Parameter(Mandatory=$true)][string]$TestRoot,
          [string[]]$Targets = @('tests'))
    $taskRunDir = Join-Path $TestRoot ('language-packs-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $taskRunDir | Out-Null
    $env:TEMP = $taskRunDir
    $env:TMP = $taskRunDir
    $env:PYTHONUTF8 = '1'
    & .\.venv\Scripts\python.exe -m pytest @Targets -q -p no:cacheprovider --basetemp (Join-Path $taskRunDir 'pytest')
    if ($LASTEXITCODE -ne 0) { throw 'Pytest failed; inspect the actual failures.' }
}
```

Trong các lệnh bên dưới, `$LanguagePackTestRoot` là writable root tạm được cấp trong session execution, ưu tiên ngoài repository như thư mục visualization hiện tại; không hardcode username/session cũ. RED phải là lỗi thiếu đúng hành vi, không phải lỗi temp/dependency. Mỗi task kết thúc bằng commit chỉ khi execution đang ở branch phù hợp và kiểm tra staged diff không chứa thay đổi có trước.

### Task 1: Registry ngôn ngữ và catalog artifact có thể kiểm chứng

**Files:** Create `core/languages.py`, `core/language_pack_contracts.py`, `core/language_pack_catalog.py`, `assets/ocr/language-packs.json`, `tools/pin_language_pack_catalog.py`, `tests/test_language_registry.py`, `tests/test_language_pack_catalog.py`; Modify `.gitignore` để giữ ngoại lệ chính xác cho catalog, không track trọng số.

**Interfaces:**
- `LanguageDefinition(id: str, config_name: str, ocr_code: str | None, google_code: str, source_enabled: bool, target_enabled: bool, bundled: bool, component_ids: tuple[str, ...], dictionary_resource: str | None)`, frozen.
- `source_languages() -> tuple[LanguageDefinition, ...]`, `target_languages() -> tuple[LanguageDefinition, ...]`, `language_by_id(id: str) -> LanguageDefinition`, `language_by_config_name(name: str) -> LanguageDefinition`, `language_by_ocr_code(code: str) -> LanguageDefinition`; unknown raises ValueError, never defaults to en.
- Frozen values in contracts: `ArtifactFile(path: str, size_bytes: int, sha256: str)`; `ArtifactDefinition(id: str, revision: str, url: str, archive_size_bytes: int, archive_sha256: str, archive_root: str, files: tuple[ArtifactFile, ...])`; `ResourceDefinition(path: str, size_bytes: int, sha256: str)`; `PackCatalog(schema: int, paddleocr_version: str, ocr_version: str, components: dict[str, ArtifactDefinition], resources: dict[str, ResourceDefinition])`.
- `PackError(code: str, user_message: str, retryable: bool)` and `PackOperationError(Exception)` with `.error: PackError`; codes include `busy`, `network`, `disk_space`, `permission`, `integrity`, `incompatible`, `cancelled`, `in_use`, `protected`, `invalid_catalog`, `missing`.
- `load_pack_catalog(path: Path) -> PackCatalog`, `validate_pack_catalog(raw: object) -> PackCatalog`; no network/import Paddle/write. Resource root is supplied separately, not baked into JSON.
- Authoring CLI `python tools/pin_language_pack_catalog.py --output PATH`: require package metadata PaddleOCR 2.10.0, derive model URLs/dictionaries without import; download to tool temp, inspect allowed model files, calculate real hashes/sizes, produce validated catalog. Existing output requires explicit `--replace`; does not install into runtime model root.

- [ ] **Step 1: Write failing contract tests.** Assert five IDs and every code/role/bundled flag equal spec §6, source names are exactly English/Japanese/Chinese/Korean and targets Vietnamese/English. `language_by_id('unknown')` raises. Catalog tests reject wrong version, missing component/dict, duplicate ID, HTTP URL, invalid digest, traversal/archive root, negative size and an unbounded archive. Monkeypatch socket/Paddle to fail if parser touches them. Tool test uses fake package metadata/HTTP and asserts actual fixture hash/bytes, not invented constants.
- [ ] **Step 2: RED.** `Test-LanguagePacks -TestRoot $LanguagePackTestRoot -Targets @('tests/test_language_registry.py','tests/test_language_pack_catalog.py')`; expected missing modules/interfaces.
- [ ] **Step 3: Implement interfaces and checked-in catalog.** Registry matches spec table; catalog uses the pinned package model sources including **Chinese det+rec** and **Korean rec**, plus en/ml/cls references. Pin release catalog with a deliberate real authoring run outside tests; inspect provenance and notice. Record archive sizes and hash values from real content; do not enable downloadable rows with empty/placeholder locks. This is release data generation, not a runtime fetch of untrusted metadata.
- [ ] **Step 4: GREEN.** Run same targets; validate generated catalog again with pure loader. Record native model compatibility as pending Task 8, not as proven by hashes.
- [ ] **Step 5: Commit.** `feat: define OCR language registry and pinned pack catalog`; stage only task files, explicitly force-add `assets/ocr/language-packs.json` if still ignored.

### Task 2: Kho component, resolver và gỡ gói có bảo vệ

**Files:** Create `core/language_pack_store.py`, `tests/language_pack_helpers.py`, `tests/test_language_pack_store.py`; Modify `core/paths.py`, `core/ocr_models.py`, `tests/test_app_paths.py`, `tests/test_ocr_bundle_runtime.py`.

**Interfaces:**
- Consumes Task 1 registry/catalog/errors and existing `OcrModelPaths(det: Path, rec: Path, cls: Path, dictionary: Path)`.
- Additional contracts: `PackState(language_id: str, state: str, origin: str, revision: str | None, removable: bool, in_use: bool, installed_bytes: int, reclaimable_bytes: int, downloaded_bytes: int = 0, total_bytes: int = 0, error: PackError | None = None)`; `PackSnapshot(rows: tuple[PackState, ...], operation_id: str | None = None, busy: bool = False)`; `InstallPlan(language_id: str, components: tuple[ArtifactDefinition, ...], resources: tuple[ResourceDefinition, ...], network_bytes: int, required_disk_bytes: int)`; `RemovalResult(reclaimed_bytes: int, pending_cleanup: bool)`. Place these in `core/language_pack_contracts.py`.
- `get_language_pack_root() -> Path` in paths; `PackStore(*, user_root: Path, bundled_root: Path, catalog: PackCatalog)`.
- `scan() -> tuple[PackState, ...]`, `plan_install(language_id: str) -> InstallPlan`, `publish_component(artifact: ArtifactDefinition, staging: Path) -> None`, `commit_pack(plan: InstallPlan) -> None`, `remove(language_id: str) -> RemovalResult`, `recover() -> None`, `resolve(language_id: str) -> OcrModelPaths`, `identity(language_id: str) -> tuple[str, str]` (language ID, validated pack revision), `lease(language_id: str) -> ContextManager[OcrModelPaths]`. Errors raise `PackOperationError`. Identity and paths are selected under the lease/mutation protocol so removal cannot race engine initialization.
- `resolve_ocr_models(lang: str, *, root: Path | None = None, store: PackStore | None = None) -> OcrModelPaths | None`: explicit `root` keeps legacy schema-1 contract; injected `store` uses registry/resolver; neither supplied retains existing source/frozen behavior. Use TYPE_CHECKING to avoid store/resolver import cycle.
- Test helper `make_pack_store(tmp_path: Path) -> PackStore` builds tiny bundled en/ja + catalog/user root; `make_component_archive(...)` supplies deterministic tar bytes for Task 3. Helpers never use profile/cache or import Paddle.

- [ ] **Step 1: Write failing behavior tests.** Fresh scan only en/ja installed; commit fixture zh-Hans then resolve correct det-ch/rec-ch/cls/dict; ko reuses bundled det-ml/cls and plan only downloads rec-ko. Partial markers/bad hash/wrong version never installed; crash before marker stays uninstalled. Remove zh-Hans removes only unreferenced user components, preserves a synthetic shared component used by another installed fixture pack, and returns actual reclaimed bytes. Bundled removal raises protected. Two independent PackStore instances on same root respect live leases and mutation lock; stale locks recover. Atomic marker failure preserves other packs; pending Windows cleanup reports pending, not fake freed bytes. Unicode/cwd/read-only bundled root are covered. `get_language_pack_root()` stays under config_dir/models; old cache is untouched.
- [ ] **Step 2: RED.** Run `tests/test_language_pack_store.py`, `tests/test_app_paths.py`, `tests/test_ocr_bundle_runtime.py`; expected missing APIs/new behavior, existing explicit-root tests remain valid.
- [ ] **Step 3: Implement store and resolver.** Follow spec §7. Use short cross-process mutation locks and per-process live package leases with QLockFile; acquire/create leases under the same mutation lock as remove, never hold it across network. Strictly resolve operation targets inside injected user_root before recursive cleanup; do not follow junctions/symlinks. Read bundled files only, stream validation and cache by stat/revision; remove never edits legacy bundle manifest. `scan/recover` are blocking methods called only on background workers.
- [ ] **Step 4: GREEN/regression.** Run task targets plus `tests/test_ocr_model_assets.py`, `tests/test_bundle_layout.py`. Assert filesystem before/after bundled root is identical, including error paths.
- [ ] **Step 5: Commit.** `feat: add transactional OCR pack store and protected removal`.

### Task 3: Tải và cài gói trong background có thể hủy

**Files:** Create `core/language_pack_transfer.py`, `tests/test_language_pack_transfer.py`; Modify contracts/helpers only for shared values.

**Interfaces:**
- Consumes `PackStore.plan_install/publish_component/commit_pack`, Task 1 catalog and errors.
- `PackProgress(operation_id: str, language_id: str, state: str, downloaded_bytes: int, total_bytes: int)` in contracts.
- `install_pack(store: PackStore, language_id: str, *, operation_id: str, client_factory: Callable[[], httpx.Client], cancelled: Callable[[], bool], progress: Callable[[PackProgress], None]) -> None`; raises PackOperationError; client is created/closed inside this function's worker thread.
- `extract_component(archive: Path, artifact: ArtifactDefinition, destination: Path, *, cancelled: Callable[[], bool]) -> None` and `verify_component(root: Path, artifact: ArtifactDefinition) -> None` are private-to-transfer helpers, exported only if test isolation warrants it.

- [ ] **Step 1: Write failing transfer tests with httpx.MockTransport.** Success across multiple archives adds marker only after all hashes/resources validate; ko requests only missing component. Cover offline/timeout, 404, redirect, truncated/oversized body, wrong Content-Length, no Content-Length with valid streamed byte count, wrong SHA, tar traversal/link/duplicate/extra file/oversize, disk-full before/during write, permission failure, cancel between chunks and just before marker. Assert no installed marker on each failure, bundled unchanged, safe cleanup only inside injected staging, closed client, progress byte counts from actual network data. Retry reuses validated component and does not implement byte-range resume. Do not weaken global socket guard.
- [ ] **Step 2: RED.** Run `tests/test_language_pack_transfer.py`; expected missing transfer function.
- [ ] **Step 3: Implement streaming transaction.** Exactly one network attempt per explicit install action; HTTP transport retries=0, HTTPS catalog host, follow_redirects=False, connect 5s/read 15s, chunk 64 KiB. Free-space need includes archives + expanded files + 16 MiB. Check cancellation before filesystem publication and marker commit. Manual allowlisted extraction and streaming SHA are required; no extractall/raw archive path joins or model-size read_bytes. Publish reusable components then atomically publish pack marker; classify all expected errors to safe recovery copy.
- [ ] **Step 4: GREEN/regression.** Run transfer and store tests; record test proving callback/client creation on caller worker thread, not GUI. A canceled transfer is cancellation, not a successful installation.
- [ ] **Step 5: Commit.** `feat: download and verify OCR language packs with cancellation`.

### Task 4: App-owned manager và snapshot bất đồng bộ

**Files:** Create `core/language_pack_manager.py`, `tests/test_language_pack_manager.py`; Modify contracts as defined, no widget imports.

**Interfaces:**
- `LanguagePackManager(store: PackStore, *, client_factory: Callable[[], httpx.Client] | None = None, parent: QObject | None = None)`; `snapshot_changed = pyqtSignal(object)`, `shutdown_finished = pyqtSignal()`.
- GUI-thread methods `snapshot() -> PackSnapshot`, `refresh() -> bool`, `request_install(language_id: str) -> bool`, `request_remove(language_id: str) -> bool`, `set_selected_language(language_id: str | None) -> None`, `cancel() -> None`, `shutdown() -> None`. Bool False means rejected/busy with a snapshot reason, not a silently queued action.
- All scan/recovery/install/remove work runs in owned QThreads. Manager merges operation progress onto cached scan rows; `snapshot()` never hashes/reads the model tree. A single operation ID and cancellation Event identify each run.

- [ ] **Step 1: Write failing Qt lifecycle tests.** A deliberately blocked transfer does not prevent a GUI QTimer from firing. Duplicate install/remove while busy returns False; selected/bundled removal rejected before dispatch. `removing` published synchronously prevents selecting that pack while queued delete runs. Late progress from previous operation cannot overwrite new snapshot. Deleting while another process has lease returns in_use. Cancel leaves other OCR/source intent untouched. Refresh/recovery is asynchronous; initial scan progress does not claim missing packages installed. Shutdown during HTTP, verify and remove requests cancel and emits shutdown_finished only after every QThread is finished; no terminate and no UI-thread long wait.
- [ ] **Step 2: RED.** Run `tests/test_language_pack_manager.py` with qtbot/fake barriers, not real sleeps/network.
- [ ] **Step 3: Implement manager.** QObject remains GUI-owned; only immutable values cross queued connections. Keep worker references until finished; close dialog cannot delete manager. Error/cancel triggers a fresh background scan before final snapshot. `set_selected_language` and source readiness checks are serialized on GUI thread; store lease rechecks protect real engine use independently.
- [ ] **Step 4: GREEN.** Run manager + store + transfer targets; Qt teardown must leave zero running worker threads and client closed.
- [ ] **Step 5: Commit.** `feat: manage OCR pack operations through app-owned workers`.

### Task 5: Registry vào config, OCR và đổi ngôn ngữ không thêm Start

**Files:** Modify `core/config.py:46–53,136–190`, `engines/google_translate.py:15,127–145`, `engines/ocr.py:15–121`, `core/worker.py:62,429–451,562–567`; Create `tests/test_language_pack_runtime.py`; Modify `tests/test_config_validation.py`, `tests/test_google_adapter.py`, `tests/test_worker_settings.py`, `tests/test_ocr_bundle_runtime.py` where contracts intentionally expand.

**Interfaces:**
- Derive `SUPPORTED_LANGUAGES` and `SUPPORTED_TARGETS` as compatibility aliases from Task 1 registry. normalize_config validates known language names only, not disk readiness; missing known packs do not rewrite stored source on load.
- `ocr_image(img, lang='en', *, store: PackStore | None = None) -> OcrResult`, `get_ocr_engine(lang='en', *, store: PackStore | None = None)`, `SimplePaddleOCR(lang='en', *, store: PackStore | None = None)` preserve old positional calls. With a store, hold lease while engine cached and release on ctor failure/switch/stop. Cache identity includes store identity + language + resolved pack revision.
- `TranslationWorker(state, region, interval_ms=500, *, ocr_reader: Callable | None = None)`; use injected reader when supplied, otherwise late lookup of module `ocr_image` to preserve existing monkeypatch tests. Both runtime and legacy frame helpers use the same reader. `release_ocr_engine()` in finally stays on OCR owner thread.
- Google mapping comes from `language_by_config_name`, preserving zh-CN versus Paddle ch and ja versus japan. No blanket unsupported-language fallback to en.

- [ ] **Step 1: Write failing runtime tests.** Parameterize en/ja/ch/ko and assert exact model/dict kwargs with fake Paddle and injected store; missing/corrupt packs never construct Paddle or auto-download. Assert one active engine/lease, revision/path change invalidates cache, and stop/failure frees lease on owner thread. Config known Chinese survives absent pack; unknown language still uses existing normalized default. Source switch on a running worker increments revision without start_worker; stopped worker stays stopped; old OCR/translation result rejected. Test Google reads all five registry codes and target change does not touch store/transfer. Keep explicit-root legacy behavior covered.
- [ ] **Step 2: RED.** Run new runtime target plus config/Google/worker tests; confirm missing behavior, not changes to test network guards.
- [ ] **Step 3: Implement adapters and worker injection.** Do not load Paddle during imports/preflight/UI. Missing managed assets return structured nonretryable ocr_model_missing with manager recovery advice; no native fallback to another language. Preserve existing frame/Google recovery/session contracts. Engine load errors invalidate readiness via manager refresh when surfaced; never auto-select another source.
- [ ] **Step 4: GREEN/regression.** Run runtime target, `tests/test_worker_settings.py`, `tests/test_worker_stabilization.py`, `tests/test_dialogue_worker_integration.py`, `tests/test_google_adapter.py`, `tests/test_google_worker_lifecycle.py`, `tests/test_ocr_spans.py`, `tests/test_config_validation.py`.
- [ ] **Step 5: Commit.** `feat: resolve managed OCR packs during existing source switches`.

### Task 6: UI trình quản lý dùng component global và ui-ux-pro-max

**Files:** Create `ui/widgets/package_status_row.py`, `ui/language_packs_dialog.py`, `tests/test_language_packs_dialog.py`; Modify `ui/controller_state.py`, `ui/styles.py`, `tests/test_ui_module_boundaries.py`.

**Interfaces:**
- UI-only frozen `LanguageChoice(id: str, config_name: str, label: str)`; append `OcrPageState.source_choices: tuple[LanguageChoice, ...] | None = None` and `.source_notice: str = ''`. None preserves constructor-supplied choices for legacy isolated view tests; empty tuple means truly no installed source.
- `PackageRowState(language_id: str, title: str, phase: str, status_text: str, detail_text: str, downloaded_bytes: int, total_bytes: int, reclaimable_bytes: int, action: str | None, action_enabled: bool, action_reason: str = '')`; actions are install/cancel/retry/remove. Progress behavior uses phase, not parsing translated labels; delete confirmation formats reclaimable_bytes directly. `LanguagePacksState(rows: tuple[PackageRowState, ...], busy: bool, message: str = '')`.
- `PackageStatusRow(state: PackageRowState, parent=None)` with `action_requested = pyqtSignal(str, str)` (language_id, action), `render(state) -> None`.
- `LanguagePacksDialog(state: LanguagePacksState, parent=None)` with `install_requested(str)`, `cancel_requested()`, `remove_requested(str)`, and `render(state) -> None`. Dialog confirms removal with QMessageBox default Cancel then emits intent; it never deletes or downloads itself. Qt finished only closes view.

- [ ] **Step 1: Write failing UI tests.** Render all states, ensure bundled has no remove; active row explains disabled removal; retry/error text actionable; determinate download and separate verifying/installing labels; no truncated distinguishing names. Cancel confirmation emits no remove; Yes emits once. Tab/Shift-Tab navigation, Escape close, focus restoration hook and closing during progress preserve app-owned fake service. Extend boundary test scan to `ui/language_packs_dialog.py` so it cannot import config/worker/engines/network/store; imports remain inert. Progress render emits no action.
- [ ] **Step 2: RED.** Run `tests/test_language_packs_dialog.py`, `tests/test_ui_module_boundaries.py`.
- [ ] **Step 3: Implement view using existing system.** Read and apply ui-ux-pro-max; repeat the two focused UX queries in spec §10 if guidance needs refreshing. There is no PyQt dataset stack: use verified All-platform focus/progress/error/text principles, not web framework snippets. Reuse ModernCard, CYBER_PALETTE, SECONDARY_BUTTON_STYLE, existing stylesheet and Lucide helper. Add missing dialog/progress/focus/destructive-state styles centrally with scoped object names; do not duplicate palette or create a generic UI framework. Use a scrollable 560×520 dialog, minimum 440×360 clamped to screen, wrap status/error text and keep footer reachable.
- [ ] **Step 4: GREEN and visual review.** Run UI/boundary targets, then inspect native screenshots at 100/150/200% DPI for installed/download/error/active/remove-confirm states. Confirm keyboard focus and no layout shift as percentage changes. Save visual QA evidence under approved scratch/artifact root, not product assets; no UI success claim from offscreen tests alone.
- [ ] **Step 5: Commit.** `feat: add reusable language pack manager dialog`.

### Task 7: Ghép select, coordinator và app lifecycle

**Files:** Modify `ui/pages/ocr_settings_page.py:9–15,34–37,121–127`, `ui/settings_coordinator.py:20–45,128–132`, `ui/controller.py:31–38,134–142,198–207,290–317`, `main.py:54–72,107–127`; Create `tests/test_language_pack_app_integration.py`; Modify `tests/test_ocr_settings_page.py`, `tests/test_settings_coordinator.py`, `tests/conftest.py`, `tests/test_game_controls_lifecycle.py` only as needed for injected service.

**Interfaces:**
- `OcrSettingsPage.manage_packs_requested = pyqtSignal()`; `update_source_choices(choices: tuple[LanguageChoice, ...], selected_config_name: str) -> None`; source_changed keeps emitting config name for actual languages. Token `__manage_language_packs__` belongs only in itemData, never snapshot/config.
- `SettingsCoordinator(..., *, pack_manager: LanguagePackManager | None = None)` adds `source_ready() -> bool`, `pack_dialog_state() -> LanguagePacksState`, and `pack_state_changed = pyqtSignal(object)`. Existing positional args stay compatible. Snapshot uses cached manager snapshot, no filesystem scan. set_source rejects not-installed/removing IDs before persist; on success updates manager selected ID and worker exactly once.
- `ControllerWindow(..., *, pack_manager: LanguagePackManager | None = None)` owns a lazy single `LanguagePacksDialog`, handles intent wiring and focus return. `start_ocr` calls source_ready preflight before starting_translation/start_worker; invalid source gives notice/open-manager recovery without falsifying running status.
- main composes one store/manager, injects OCR reader `lambda image, lang: ocr_image(image, lang=lang, store=store)` into worker, injects manager into controller, then refreshes in background. Shutdown app.quit requires both translation and pack shutdown completion; no running threads destroyed.

- [ ] **Step 1: Write failing integration tests.** Select lists only installed en/ja then separator/action. Selecting manager restores former selection, emits manage intent once, saves/configures nothing and opens one dialog. Install ch adds choice but does not change source/start/configure; selecting ch afterwards configures once with running/stopped state preserved. Target choices remain independent. Delete inactive ch removes it, bundled unchanged; active/removing removal blocked. Legacy config ch with no pack yields index -1/notice, unchanged file and blocked Start; install restores saved choice without auto-start. Failed save restores old UI/runtime. Download while switching ja→en, Stop, closing/reopening dialog and late completion never selects/restarts. Existing hotkeys/tray Start passes source guard. Shutdown during download waits for both finish signals once.
- [ ] **Step 2: RED.** Run new integration target plus `tests/test_ocr_settings_page.py`, `tests/test_settings_coordinator.py`, `tests/test_game_controls_lifecycle.py`; update fixtures with a fake manager/store, not profile model files. Keep old signal assertions for programmatic source changes.
- [ ] **Step 3: Implement composition and intents.** Handle currentIndexChanged through itemData; block signals while restoring action index/rebuilding choices. Define a clear placeholder when saved source is unavailable. On manager snapshot changes coordinator emits `settings_changed(snapshot, 'language_packs')` for source choices and `pack_state_changed(dialog_state)` for the manager view; controller excludes language_packs from clear_translation_status and never changes source revision/settings on this event. Manager rendering never writes config. Connect dialog/service once, use open(), keep manager alive on close. Track two shutdown completion flags with one maybe_quit function, including immediate completion and repeated Quit.
- [ ] **Step 4: GREEN/regression.** Run integration targets plus `tests/test_controller_behavior.py`, `tests/test_controller_compatibility.py`, `tests/test_controller_integration.py`, `tests/test_worker_status_ui.py`, `tests/test_ui_module_boundaries.py`, `tests/test_game_controls.py`. Confirm no forced Start or download on selection of installed languages.
- [ ] **Step 5: Commit.** `feat: connect installed language select to pack management`.

### Task 8: Bundle resources, chạy native và nghiệm thu toàn luồng

**Files:** Modify `tools/prepare_ocr_models.py`, `tools/bundle_layout.py`, `tests/test_ocr_model_assets.py`, `tests/test_bundle_layout.py`; Create `tests/test_language_pack_bundle.py`, `docs/testing/language-packs.md`. Modify `main.spec` only if explicit allowlist helper cannot supply new data; do not change dependency pins without separate evidence/scope review.

**Interfaces:**
- Existing `prepare_models(...) -> dict` retains schema-1 en/ja manifest contract. Add sibling resource prep function `prepare_pack_resources(output: Path, dictionary_root: Path, catalog_path: Path) -> None`: copy catalog, Chinese `ppocr_keys_v1.txt` and Korean `dict/korean_dict.txt` to `pack_resources/`, matching Task 1 pinned resource hashes; no runtime download. en/ja dictionaries and NOTICE already exist.
- `bundle_data(project_root: Path, model_root: Path) -> list[tuple[str, str]]` additionally validates/allowlists catalog and the exact extra dictionaries. Catalog root is runtime `_MEIPASS/assets/ocr` or source assets; generated extra files are not added to legacy manifest.files that has a fixed allowlist.
- Runtime notices retain model provenance. No user-root downloads, .env, credentials, config, .staging/.trash, MORT, video or weight archives enter the application bundle.

- [ ] **Step 1: Write failing bundle tests.** Missing/tampered catalog/dictionary fails preflight; extra dictionaries/catalog land at exact runtime relative paths; parser reads same source/frozen catalog from foreign cwd and Unicode root. Tar archives/user installs are excluded; source resources and fake bundled assets remain read-only. Ensure old prepare_models callers/tests do not silently get a malformed legacy manifest.
- [ ] **Step 2: RED.** Run `tests/test_language_pack_bundle.py`, `tests/test_bundle_layout.py`, `tests/test_ocr_model_assets.py`.
- [ ] **Step 3: Implement packaging/docs.** Wire explicit resource prep into build instructions; do not discover/copy arbitrary package/cache files. Verify raw official archives and notice compatibility during data authoring; record exact catalog revisions/hashes in release evidence. Add manual user instructions for install/retry/cancel/remove, bundled protection, offline OCR versus online translation, and repair missing/corrupt packs.
- [ ] **Step 4: GREEN, full regression and diff review.** Run task targets, then `Test-LanguagePacks -TestRoot $LanguagePackTestRoot` for all tests. Run `git diff --check -- core engines ui main.py tools tests .gitignore` and inspect only task-owned diffs. Full suite PASS is required; it does not prove real download/native OCR. Run repo build script with the prepared model root and existing build environment, record actual output/size rather than assuming build succeeds.
- [ ] **Step 5: Native acceptance on a clean Windows profile.** Start bundled app in read-only install directory with Unicode/space path and no .paddleocr cache; network off proves en/ja first. Network on: install zh-Hans then ko using pinned upstream, record actual required/download bytes and progress, choose each against known text fixtures and prove correct OCR (not merely Paddle ctor success). Download while en/ja runs must leave UI responsive. Restart with network off and prove installed ch/ko OCR still works; translation network failure is a separate expected condition. Remove inactive downloaded pack, reopen app, verify it stays absent and can reinstall; simulate interrupted download/missing file/missing selected pack, verify recovery. Check Tab/Escape and Windows DPI 125/150/200%. No runtime auto-download to home and no bundle writes. If clean/native environment unavailable, explicitly mark this release gate unverified rather than pass.
- [ ] **Step 6: Commit.** `build: ship OCR language pack resources and validation guide`; stage exact files and reviewed catalog/provenance, never weights/dist/user data. Create dated execution-results document under docs/plans with measured outcomes only.

## Self-Review và Coverage

| Spec | Tasks/test ownership |
|---|---|
| §1–2 select đã cài, manager, không download-and-start, phạm vi 4 source/2 target | 1 registry, 6 dialog, 7 application flow |
| §3–6 legacy mapping, versions, catalog/URL/hash thật | 1 registry/catalog + 5 adapters + 8 packaging/native |
| §7 storage, shared components, marker, leases, safe removal | 2 store + 3 transfer + 4 manager |
| §8 cancel/progress/busy/close/crash/shutdown | 3 transfer + 4 manager + 7 main shutdown |
| §9 config thiếu, persist-before-apply, revision/stale result, no auto-start | 5 runtime + 7 integration |
| §10 component reuse, keyboard, focus, DPI, visual QA | 6 views + 7 select + 8 native QA |
| §11 acceptance and mock/native boundary | 8 release evidence plus all targeted tests |

- Interface names/types above are the canonical cross-task contracts. Task 6 UI dataclasses have no engine/config imports; Task 7 performs translation between service and UI values. All signatures consumed later are defined by Tasks 1–6.
- Each of five Review Focus rows has explicit tests in the owning tasks, not just a manual checklist. Existing source-only/explicit-root resolver behavior remains regression-covered.
- Plan steps specify outcomes/signatures/assertions instead of writing implementation bodies. Production scope excludes provider refactor, grouping optimization and changing hard limits 32/2000 from the earlier audit.
- Planning verification: re-read both documents, verify referenced existing files, required headers/task cycles, exact user decisions and no residual download-and-start behavior. Mark execution boxes only during implementation with fresh evidence.

## Handoff

Chỉ spec và kế hoạch được viết trong bước này; chưa triển khai sản phẩm hoặc tải trọng số. Đề xuất thực thi **Native** theo thứ tự 1→8 vì registry/store/manager/UI chia sẻ nhiều interface, cần giữ một luồng ngữ cảnh nhất quán; vẫn review toàn bộ thay đổi trước khi kết luận. Nếu người dùng muốn kiểm tra độc lập từng task, chọn subagent-driven và dùng skill tương ứng. Review spec/plan và chọn cách execution trước khi bắt đầu code theo writing-plans.
