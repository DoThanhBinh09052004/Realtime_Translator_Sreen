# Window Capture and Multiple OCR Regions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This is a planning deliverable, not authorization to begin implementation.

**Goal:** Thêm nguồn cửa sổ WGC cùng 1–8 vùng OCR và tối đa 16 vùng loại trừ, giữ đường MSS và các bảo đảm về hội thoại/overlay hiện có.

**Architecture:** Hai capture adapter trả ảnh nguồn và metadata qua hợp đồng chung; scan state tách theo ROI, một OCR owner và một translation owner. Một region-session router namespace job ID, gom presentation về một canvas và giữ một GUI coordinator timer. Nguồn cửa sổ dùng HWND/identity thật; tọa độ ROI normalized, raster và Qt được chuyển đổi tường minh.

**Tech Stack:** Python x64 hiện tại, PyQt5 5.15.11, MSS 10.1.0, NumPy/OpenCV/PaddleOCR hiện có; ctypes Win32 và candidate windows-capture 2.0.1; pytest/pytest-qt, PyInstaller 6.22.3 onedir.

**Spec:** [2026-10-30-window-multi-region-design.md](C:/Users/Admin/Documents/Realtime_Translator_Sreen/docs/plans/2026-10-30-window-multi-region-design.md). Cả spec và plan là phương án đề xuất, chưa duyệt triển khai.

## Global Constraints

- Tính năng nguồn cửa sổ mới yêu cầu Windows 10 build 19041 trở lên, Python x64; chạy bằng quyền app hiện tại. Không tự nâng quyền.
- Một nguồn hoạt động tại một thời điểm; nguồn mới nằm trọn một màn hình. Giữ legacy MSS subtitle spanning-monitor khi đọc cấu hình cũ.
- Trên một nguồn, tạo 1–8 vùng OCR; thêm tối đa 16 hình chữ nhật loại trừ. Có ít nhất một vùng OCR bật.
- Vùng OCR cùng nguồn không được chồng diện tích; chạm cạnh được phép. Vùng loại trừ được chồng nhau.
- Một ngôn ngữ nguồn/đích, provider và chế độ hiển thị chung. Một owner OCR, một owner SDK dịch; tối đa 32 active tracks và 32 queued jobs.
- Không đổi pin Paddle/NumPy/OpenCV hiện tại để ép cài WGC. Kiểm tra native wheel và đóng gói trước khi chốt dependency.
- Không lưu ảnh/debug/video mặc định. Buffer một ảnh mới nhất cộng tối đa một ảnh đang xử lý; callback throttle tối đa 10 lần/giây.
- Không silently fallback từ window sang desktop, không chọn lại window theo title, không tái sử dụng identity cũ sau restart.
- GUI geometry poll mỗi 100 ms; opening timeout 2 giây; drain quá 3 giây báo đang dừng và chặn start mới, không terminate native thread.
- Không sửa MORT, không CodeGraph; tất cả spec/plan/progress nằm trong docs/plans/. Giữ nguyên thay đổi người dùng có sẵn.

## Review Focus

1. Cửa sổ trùng tên/đổi title/HWND reuse: vẫn đúng nguồn hoặc báo mất nguồn, không capture nhầm — Task 0, 4.
2. DPI 125%, origin âm, viền client và move trong lúc OCR đang chờ: chữ vẽ đúng vị trí, không API request thừa do move — Task 2, 4, 6.
3. ROI không đến lượt hoặc OCR lỗi bị hiểu thành nguồn trống; namespace lẫn vùng khi trả kết quả muộn — Task 3, 5.
4. Không có callback trên ảnh tĩnh, minimize/resize và native close chậm: không giữ stale frame hoặc làm đơ UI/đóng giả — Task 4, 6.
5. Config legacy nằm qua hai monitor, Apply lỗi, cancel/quit trong preview, native DLL thiếu trong bundle: giữ vùng cũ và thông báo được — Task 1, 6, 7.

## Trình tự và cổng nghiệm thu

`0: WGC probe → 1: contracts/config → 2: tọa độ → 3: MSS + scanner → 4: WGC adapter → 5: nhiều session → 6: UI + wiring → 7: regression + bundle`.

Task 0 không được xem là bằng chứng đã ship. Nếu không chứng minh được frame/client mapping, bounded shutdown hoặc runtime wheel tương thích, dừng nhánh WGC và sửa đề xuất kỹ thuật trước khi tích hợp; các task thuần MSS không cần dependency native để chạy test.

Mỗi task có red/green test phù hợp và review checkpoint. Chỉ commit nếu phiên thực thi được phép ghi Git; stage đúng thay đổi của task, không `git add .`, không lấy thay đổi người dùng vào commit. Không tạo branch/worktree/commit trong lượt chỉ lập kế hoạch này.

## File structure và interfaces cố định

Tất cả tên dưới đây là tên dự kiến; file chưa tồn tại được tạo ở task tương ứng. Các kiểu immutable đặt trong `core/capture/models.py`:

```python
NormalizedRect(x: float, y: float, width: float, height: float)
CaptureRegion(id: str, name: str, rect: NormalizedRect, enabled: bool)
CaptureProfile(version: int, source_kind: Literal['desktop','window'],
               monitor_name: str | None, window_hint: str | None,
               regions: tuple[CaptureRegion, ...], exclusions: tuple[NormalizedRect, ...])
WindowIdentity(hwnd: int, pid: int, process_started_100ns: int)
CaptureContext(binding_epoch: int, geometry_sequence: int,
               source_kind: Literal['desktop','window'], window: WindowIdentity | None,
               geometry: CaptureGeometry)  # geometry.region_px = client hoặc monitor toàn phần
CapturedFrame(binding_epoch: int, sequence: int, pixels: np.ndarray,
              image_origin_px: tuple[int,int], source_size_px: tuple[int,int],
              captured_at_s: float)  # pixels BGRA uint8, owned/read-only; origin trong source canvas
RegionOcrObservation(region_id: str, captured_at_s: float,
                     completed_at_s: float, ocr: OcrResult)
CaptureObservation(revision: int, scan_id: int, settings: RuntimeSettings,
                   context: CaptureContext, regions: tuple[RegionOcrObservation, ...])
SourceStatus(binding_epoch: int,
             phase: Literal['opening','ready','unavailable','error','stopping','stopped'],
             error: EngineError | None = None)
CaptureStatus(revision: int, binding_epoch: int,
              phase: Literal['opening','ready','unavailable','error','stopping','stopped'],
              error: EngineError | None = None)
```

`CaptureProfile.version=1` chỉ là version của nested profile, không đổi config schema ngoài. Region ID là UUID string không rỗng và không trùng; thứ tự trong tuple là thứ tự hiển thị. Exclusions dùng cùng coordinate space, không có ID riêng vì không namespace jobs.

`CaptureContext.geometry` bao phủ source client/monitor, dùng `ScreenMapping` hiện có; `CapturedFrame` của MSS có thể chỉ chứa bounding box ROI, còn WGC chứa client image. Geometry scale dựa `source_size_px`, không dựa kích thước crop MSS. Không sửa semantics `CaptureGeometry` cho caller cũ.

### Task 0: Chứng minh WGC trên runtime và bundle thử

**Files:** Create `tools/probe_window_capture.py`, `tests/test_capture_probe_contract.py`, `docs/testing/window-capture.md`. Modify requirements files chỉ sau khi cổng probe đạt.

**Interfaces:** `run_probe(*, seconds: float, output: Path) -> int`; dùng các cửa sổ Qt test do probe sở hữu, không tự chọn game/app riêng tư. JSON output chứa kích thước/offset/status/timing và boolean pass/fail, không ghi ảnh mặc định. Probe output nằm trong scratch/, không phải planning directory khác.

- [ ] Viết test parse args: mặc định không lưu ảnh, native import lazy; invalid duration/output lỗi rõ; đây là test hợp đồng tool, chưa mô phỏng thành công native.
- [ ] Chạy `.venv/Scripts/python.exe -m pytest -q tests/test_capture_probe_contract.py`; xác nhận FAIL đúng vì tool chưa có.
- [ ] Tạo probe có hai cửa sổ trùng title, marker tại bốn góc client, move/resize/minimize/restore và stop. Lấy WGC bằng HWND, kiểm tra frame stride và mapping DWM/client; native source không nằm trong event loop GUI.
- [ ] Tạo env thử bằng `uv venv --python .venv/Scripts/python.exe scratch/capture-probe-venv`; `uv pip sync --python scratch/capture-probe-venv/Scripts/python.exe requirements-build.lock`; `uv pip install --python scratch/capture-probe-venv/Scripts/python.exe --no-deps windows-capture==2.0.1`. Chạy `uv pip check --python scratch/capture-probe-venv/Scripts/python.exe`, rồi `scratch/capture-probe-venv/Scripts/python.exe tools/probe_window_capture.py --seconds 10 --output scratch/window-capture-probe.json`; build probe bằng chính env đó với `-m PyInstaller --onedir --noconfirm --distpath scratch/capture-probe-dist --workpath scratch/capture-probe-build tools/probe_window_capture.py`. Giữ probe spec dưới scratch bằng `--specpath scratch`, không tạo artifact phát hành ở root. Wheel không được nâng NumPy/Paddle/OpenCV ngoài pin.
- [ ] Xác nhận: đúng cả hai HWND, title đổi không rebind; marker khớp pixel client sau crop; ảnh chỉ BGRA8 đường được hỗ trợ; restore nhận frame mới; stop/drain chạy ngoài GUI; bundle chạy không cần Rust/.NET/dev environment. Ghi cả thất bại/giới hạn, không dùng benchmark README làm số đo.
- [ ] Chạy lại test tool PASS; checkpoint review native evidence. Nếu cổng fail, chưa thêm WGC vào app và chưa chốt dependency. Khi đạt, thêm pin candidate vào requirements.txt; tái sinh lock bằng `uv pip compile --python .venv-build/Scripts/python.exe requirements-build.txt --generate-hashes --output-file requirements-build.lock`, review diff giữ các pin hiện tại; sync/check env build theo lock trước build tiếp.

### Task 1: Profile immutable, validation và migration không mất cấu hình

**Files:** Create `core/capture/__init__.py`, `models.py`, `profile.py`; Modify `core/config.py`; Test `tests/test_capture_profile.py`, `tests/test_config_validation.py`, `tests/test_config_persistence.py`.

**Interfaces:** `parse_capture_profile(raw: object) -> CaptureProfile` raise `ConfigError`; `load_capture_profile(screens: tuple[ScreenMapping,...]) -> CaptureProfile | None` (None = legacy spanning/unresolvable, giữ đường cũ); `save_capture_profile(profile: CaptureProfile) -> None`; `migrate_legacy_region(region: dict, screens: tuple[ScreenMapping,...]) -> CaptureProfile | None`.

- [ ] Viết tests: `test_legacy_region_roundtrips_exact_pixels`, `test_legacy_spanning_region_is_retained`, `test_profile_rejects_nonfinite_bool_duplicate_ids_limits_and_no_enabled_roi`, `test_profile_save_is_atomic_and_preserves_legacy_region_and_credentials`, `test_read_does_not_write`, `test_window_profile_persists_hint_without_runtime_identity`. Assert ROI 9/exclusion17 fail; HWND/PID/process time không xuất hiện trong JSON; invalid existing profile báo lỗi, không coi như không có profile.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q tests/test_capture_profile.py tests/test_config_validation.py tests/test_config_persistence.py`; xác nhận test mới FAIL trước code.
- [ ] Implement typed values và validation: float finite, trong 0..1, diện tích dương, tên trim không rỗng, ROI ID UUID không trùng, overlap reject; source kind/monitor/hint hợp lệ. Tích hợp nested profile vào normalize/save atomic; runtime identity chỉ trong RAM. Legacy wrappers vẫn hoạt động, không ghi profile khi chỉ load.
- [ ] Run cùng command, PASS cả test mới và hợp đồng cũ. Checkpoint chỉ files task; không stage config.json người dùng.

### Task 2: Tọa độ nguồn, crop và vùng loại trừ

**Files:** Create `core/capture/geometry.py`; Test `tests/test_capture_geometry.py`, `tests/test_capture_exclusions.py`; tham chiếu `core/blocks/geometry.py`, không đổi hợp đồng caller cũ.

**Interfaces:** `region_rect_px(rect: NormalizedRect, source_size_px: tuple[int,int]) -> Rect`; `resolve_region_crops(profile: CaptureProfile, source_size_px: tuple[int,int]) -> dict[str, Rect]`; `frame_crop(frame: CapturedFrame, rect: Rect) -> np.ndarray`; `filter_excluded_spans(ocr: OcrResult, *, roi_rect_px: Rect, exclusions_px: tuple[Rect,...]) -> OcrResult`; `to_source_rect(rect: Rect, roi_rect_px: Rect) -> Rect`.

- [ ] Viết test cases/assertions: ROI `(0.25,0.5,0.5,0.25)` trên `(1920,1080)` → `Rect(480,540,960,270)`; negative monitor origin chỉ ảnh hưởng global mapping, không crop index; 125/150% Qt mapping không nhân DPR hai lần; MSS bounding-origin được trừ đúng; fractional touching edge không có pixel OCR chung.
- [ ] Viết tests exclusion: crop buffer gốc không bị sửa; span giao một phần exclusion bị bỏ; subtitle text chỉ gồm span còn lại theo thứ tự OCR; exclude toàn ROI → text/spans rỗng; error OcrResult không biến thành empty success; các exclusion chồng nhau không làm xuất hiện lại chữ.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q tests/test_capture_geometry.py tests/test_capture_exclusions.py tests/test_block_geometry.py tests/test_selector_geometry.py`; xác nhận test mới FAIL.
- [ ] Implement floor/ceil/clip và xử lý common raster edge theo thứ tự ROI; crop copy BGRA rồi mask đen trước OCR, filter span sau OCR bằng cùng rect source-local. `frame_crop` reject frame không phủ ROI hoặc source_size không khớp context, không silently clip mất nội dung.
- [ ] Run cùng command PASS; review pixel fixtures ở viền phải/dưới và chiều rộng không chia hết row alignment. Checkpoint geometry task.

### Task 3: Nguồn MSS và scanner có state riêng từng ROI

**Files:** Create `core/capture/source.py`, `desktop.py`, `scan.py`; Test `tests/test_capture_desktop.py`, `tests/test_capture_scan.py`.

**Interfaces:** protocol `CaptureSource.open(context: CaptureContext, *, roi_rects_px: tuple[Rect,...] | None = None) -> None`, `read_latest(*, now_s: float) -> CapturedFrame | None`, `status() -> SourceStatus`, `close() -> None` (owner thread, sau return native đã drain); factory `create_capture_source(context: CaptureContext, *, on_terminal: Callable[[SourceStatus], None] | None = None) -> CaptureSource`. `roi_rects_px=None` yêu cầu toàn source để preview; tuple runtime chứa rect pixel source-local của các ROI bật, MSS lấy union, WGC được trả toàn client. Tuple rỗng không hợp lệ. Worker bọc SourceStatus với revision hiện tại thành CaptureStatus trước khi phát signal. `RegionScanner(profile: CaptureProfile, *, ocr_reader, clock)`; `observe(frame: CapturedFrame, *, settings: RuntimeSettings, context: CaptureContext, revision: int, force_regions: frozenset[str], dynamic_masks_px: tuple[Rect,...], is_current: Callable[[], bool]) -> CaptureObservation | None`; `reset(profile: CaptureProfile) -> None`. `dynamic_masks_px` là mask subtitle source-local ở desktop, rỗng ở WGC. `None` frame không phải ảnh nguồn rỗng; scanner trả None nếu revision/stop không còn hợp lệ.

- [ ] Tests dùng fake MSS/clock/OCR: `test_one_grab_for_three_regions`, `test_preview_reads_full_source_instead_of_runtime_union`, `test_same_frame_crops_have_same_capture_time`, `test_changes_outside_regions_do_not_schedule_ocr`, `test_each_region_has_own_retry_thumbnail_and_confirmation`, `test_scan_budget_rotates_oldest_regions_without_starvation`, `test_static_region_due_after_one_second`, `test_stop_or_revision_change_between_regions_discards_batch`, `test_desktop_subtitle_dynamic_mask_covers_two_rois_without_self_capture`, `test_window_source_does_not_inherit_desktop_mask`. Assert một grab/sweep, không gọi OCR trên gap, một region lỗi không dừng region còn lại; skipped region không xuất hiện dưới dạng OcrResult rỗng; mask áp dụng trước thumbnail và OCR.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q tests/test_capture_desktop.py tests/test_capture_scan.py`; xác nhận FAIL test mới.
- [ ] Implement MSS ownership trong worker thread, union bounding crop hoặc full-source preview theo open request và metadata offset; scanner kết hợp user exclusions với dynamic masks, chuyển BGRA → gray sau mask, gọi OCR tuần tự, dùng image-change gate/retry từng ROI. Budget sweep bằng interval_ms, kiểm tra sau từng OCR; lấy frame mới vòng tiếp theo, chọn oldest-scan trước. Kết quả batch chỉ chứa ROI thật sự đã xử lý; sequence tăng đơn điệu.
- [ ] Run cùng command PASS; assert buffers không bị giữ qua lịch sử và clock không dùng wall time. Checkpoint deliverable backend độc lập UI.

### Task 4: WGC, window identity và native lifecycle

**Files:** Create `core/capture/windows.py`, `wgc.py`, `ui/window_geometry.py`; Modify factory `core/capture/source.py`; Test `tests/test_capture_windows.py`, `tests/test_capture_wgc.py`, `tests/test_window_geometry.py`.

**Interfaces:** `enumerate_capture_windows() -> tuple[WindowChoice,...]` với `WindowChoice(identity: WindowIdentity, title: str, process_name: str, available: bool)`; `read_window_geometry(identity: WindowIdentity) -> NativeWindowGeometry` với fields `capture_bounds_px: Rect, client_bounds_px: Rect, minimized: bool, visible: bool`; `validate_window_identity(identity) -> bool`; `WgcCaptureSource(native_factory=..., clock=..., on_terminal: Callable[[SourceStatus], None] | None = None)` theo CaptureSource protocol. `WindowGeometryProvider.set_binding(profile: CaptureProfile, identity: WindowIdentity | None, binding_epoch: int) -> None`, signals `context_changed(CaptureContext)`, `source_unavailable(EngineError)`, timer100ms GUI-owned. `on_terminal` gọi tối đa một lần/epoch cho closed/error; worker dùng callback này emit `capture_terminal_status(object)` về lifecycle GUI qua Qt.QueuedConnection, không phải chờ run() đọc status.

- [ ] Fake Win32/native tests: `test_duplicate_titles_and_title_change_keep_hwnd_identity`, `test_reused_hwnd_rejected`, `test_capture_bounds_client_crop_and_padded_rows`, `test_static_content_without_callback_remains_valid`, `test_timeout_before_first_frame_only`, `test_minimize_close_and_frame_errors_clear_ready_state`, `test_terminal_failure_relays_once_per_epoch_while_ocr_is_held`, `test_old_callback_cannot_overwrite_new_epoch`, `test_callback_buffer_has_capacity_one`, `test_native_stop_and_join_run_outside_gui_and_callback`, `test_move_emits_geometry_without_new_binding_epoch`, `test_resize_or_dpi_requires_new_binding`, `test_cross_monitor_window_is_unavailable`.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q tests/test_capture_windows.py tests/test_capture_wgc.py tests/test_window_geometry.py`; xác nhận FAIL test mới.
- [ ] Implement ctypes signatures x64, identity bằng process creation time, enumerator loại cửa sổ app/hidden/cloaked; source lazy import WGC, dùng `window_hwnd`, không title matching. Copy owned BGRA8 client crop vào capacity-one latest buffer; bỏ callback quá tốc độ hoặc sai epoch/size. Không có Qt widgets trong native callbacks; callback exceptions chuyển status có thể thao tác được.
- [ ] Implement provider: GUI lấy screen mapping; origin-only update tăng geometry_sequence, không revision; size/DPI/monitor đổi báo hard rebind, debounce200ms sau thay đổi cuối trước reopen native. Invalidate overlay/job ngay khi phát hiện thay đổi, không chờ debounce. Minimize giữ profile, restore revalidate identity và epoch mới; close buộc chọn lại nguồn.
- [ ] Run fake tests PASS rồi chạy lại manual probe Task0 với adapter thực. `.stop()`/`.wait()` chỉ gọi ngoài GUI và ngoài callback; chậm quá3s vẫn đang stopping và không mở source thứ hai. Checkpoint native lifecycle; không hứa `.stop()` luôn hoàn thành trong3s.

### Task 5: Router nhiều session và hiển thị không trộn vùng

**Files:** Create `core/capture/sessions.py`; Modify `core/dialogue/coordinator.py`, `core/blocks/session.py`, `core/dialogue/subtitle_session.py`; Test `tests/test_capture_sessions.py`, `tests/test_capture_translation_routing.py`; giữ nguyên `core/blocks/models.py` request-key public shape.

**Interfaces:** `RegionDialogueSession(profile: CaptureProfile, *, policy=DEFAULT_DIALOGUE_POLICY)` cung cấp session facade `observe(batch: CaptureObservation)`, `set_geometry(context: CaptureContext)`, `translation_jobs(*, now_s)`, `mark_dispatched(job, *, now_s)`, `apply_result(result, *, now_s) -> bool`, `tick(*, now_s)`, `current_frame()`, `active_turns`, `needs_scan_regions: frozenset[str]`, `drain_errors()`; initialization `reset(revision: int, settings: RuntimeSettings)`. Coordinator thêm GUI slots `configure_capture(profile: CaptureProfile, context: CaptureContext) -> None`, `observe_capture(batch: CaptureObservation) -> None`, `update_capture_geometry(context: CaptureContext) -> None`; giữ slot observe cũ cho legacy. Thêm signal `capture_scan_policy_changed(int, object)` mang revision + frozenset region ID, không đổi signature `scan_policy_changed(int,bool)` cũ. `BlockSession(*, policy=..., max_tracks: int=32)` thay hardcode quota bằng tham số; subtitle session thêm track_id mặc định0 cho compatibility.

- [ ] Tests: cùng local track_id/text ở hai ROI nhận global block_id khác nhau; map result về đúng owner; bỏ route đã retire, không recycle ID cùng revision; xóa/tắt/reorder ROI làm revision cũ không thể hồi sinh; malformed/late/error batch không reset region khác. Assert `len(job.request_key)==4` vẫn đúng và với mọi job routed: `(job.revision,job.block_id,job.turn_id) in routed_active_turns`; inverse mapping job_started/result cũng đúng local track.
- [ ] Tests output: subtitle A/B trả ngược thứ tự vẫn hiển thị theo thứ tự cấu hình, cách một dòng trống; B trống không xóa A; blocks local rect được offset về source, không merge qua ROI; quota `sum==32` với N1/3/8 và active/pending không quá32; OCR starvation làm freshness của region đó hết hạn đúng policy; global rate-limit không tách budget theo ROI.
- [ ] Test `test_geometry_move_repaints_held_blocks_without_new_ocr_or_translation`: chỉ geometry origin đổi làm frame geometry mới, cùng text/jobs; context geometry_sequence cũ không rewind; size/epoch đổi phải hard reset trước result tiếp theo.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q tests/test_capture_sessions.py tests/test_capture_translation_routing.py tests/test_dialogue_sessions.py tests/test_dialogue_translation_queue.py tests/test_dialogue_coordinator.py`; xác nhận test mới FAIL.
- [ ] Implement router namespace, local/global jobs/results/job_started và active_turns conversion bằng dataclass replace và reverse map; dọn route retired không reuse ID; child sessions nhận observations độc lập. `DialogueCoordinator` dùng router cho profile mới và session cũ cho legacy, vẫn một timer; thêm các GUI slots đã khai báo. Ghép subtitle chỉ ở presentation, không ở request; source canvas image_size lấy từ context.
- [ ] Run cùng command PASS; checkpoint cùng test fairness/retry existing. Không đổi translator provider implementation để xử lý nhiều ROI.

### Task 6: Worker, settings/editor và main wiring

**Files:** Modify `core/worker.py`, `main.py`, `ui/controller.py`, `ui/controller_state.py`, `ui/settings_coordinator.py`, `ui/pages/ocr_settings_page.py`, `ui/region_selection.py`, `ui/game_controls.py`; Create `ui/capture_settings.py`, `ui/capture_regions_dialog.py`, `ui/capture_preview.py`; Modify `ui/overlay.py` chỉ khi integration test chứng minh cần; Test `tests/test_capture_app_integration.py`, `tests/test_capture_settings_ui.py`, `tests/test_capture_selection_lifecycle.py`, `tests/test_capture_preview.py`.

**Interfaces:** `TranslationWorker.configure_capture(profile: CaptureProfile, context: CaptureContext) -> int` áp dụng atomic snapshot và cấp revision; `update_capture_geometry(context: CaptureContext) -> None` cho origin-only; property `is_drained: bool` chỉ true khi OCR/source native và translation worker đều đã dừng; signals `capture_observation_ready(object)`, `capture_status_updated(object)`, `capture_terminal_status(object)`, `capture_rebind_requested(object)`; giữ `set_region`, `set_capture_geometry`, legacy constructor. `SettingsCoordinator.apply_capture_profile(profile) -> bool`; `CapturePreviewWorker(profile, context).preview_ready(image, context)`, `.request_stop()`, `.shutdown_finished()`; `CaptureRegionsDialog(profile, image, context).profile_selected(profile)`, `.cancelled()`. Mở rộng `RegionSelectionLifecycle.request_shutdown() -> None`, signal `shutdown_finished()`, slot `on_capture_terminal(status: SourceStatus) -> None` là GUI owner aggregate runtime+preview. `ControllerWindow.capture_run_requested: bool` giữ ý định Start/Stop độc lập trạng thái tạm ngưng nguồn.

- [ ] Viết UI/lifecycle tests: draft edit không ghi config; overlap/limit/no-enabled có thông báo và không Apply; nhập số không cần drag; Escape/cancel/save fail giữ profile cũ; resize khi editor mở yêu cầu refresh; toolbar chọn vùng giữ source window; cửa sổ thiếu identity sau app restart không Start được; source biến mất clear ngay và bỏ kết quả cũ.
- [ ] Viết integration tests fake capture+OCR+service: Start → source owner → batch → coordinator → jobs → result → subtitle/block overlay đúng nguồn; cả MSS/WGC giả, subtitle/blocks, provider matrix hiện có. Giữ OCR đang chờ rồi move window, assert block cập nhật geometry qua GUI slot; native terminal failure trong lúc OCR held phải clear/invalidate qua queued relay trước khi OCR release, late translation không hồi sinh. Đổi nguồn/resize/quit với callback cũ assert không hiện lại và không nguồn native song song; minimize→restore tự tiếp tục chỉ khi capture_run_requested còn true, Stop lúc đang chờ restore ngăn auto-start.
- [ ] Viết tests drain: selection chờ runtime drained mới preview; preview drained mới runtime resume; GUI heartbeat còn chạy khi native close bị giữ; quit ở từng bước không resume; shutdown_finished chỉ sau close thật. Riêng `test_quit_waits_for_preview_native_drain_when_runtime_already_finished` assert ShutdownBarrier chưa app.quit khi preview close còn held, sau release chỉ quit một lần. GameControls start/stop, trạng thái chờ nguồn và pending restart luôn cùng ý định controller.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q tests/test_capture_app_integration.py tests/test_capture_settings_ui.py tests/test_capture_selection_lifecycle.py tests/test_capture_preview.py tests/test_game_controls_lifecycle.py tests/test_game_controls.py`; xác nhận test mới FAIL.
- [ ] Integrate owner-thread source/scanner vào nhánh run hiện hành, không helper legacy; profile/context thay bằng snapshot dưới mutex. Nối `capture_observation_ready → coordinator.observe_capture`, coordinator `capture_scan_policy_changed` cung cấp per-region force set cho worker; geometry provider nối đồng thời worker context và coordinator geometry slot, không nhét native query vào paintEvent. Scanner dùng `is_current=lambda: worker._is_current(revision)` trong owner thread để bỏ kết quả invalidated giữa sweep. `overlay.capture_geometry_changed → worker.set_overlay_rect` tiếp tục nhận mask global physical qua context mới; scanner nhận tuple mask source-local chỉ cho desktop, không lấy mask legacy load_region cho window. `revision_changed` vẫn clear overlay/status như hiện tại.
- [ ] Nối `capture_terminal_status → lifecycle.on_capture_terminal` bằng Qt.QueuedConnection, guard binding_epoch; slot invalidate revision/clear presentation và pending ngay, request source drain không block. `capture_run_requested` chỉ đổi bởi Start hợp lệ/Stop/Quit, tạm mất nguồn không làm mất intent; restore/rebind đi qua controller để toolbar/status đồng bộ. Nối `RegionSelectionLifecycle.shutdown_finished → ShutdownBarrier.finish('translation')` thay kết nối worker trực tiếp hiện tại. `on_quit` gọi lifecycle.request_shutdown cùng pack_manager.shutdown; aggregate phát khi runtime is_drained và preview đã finished, giữ guard quit một lần.
- [ ] Implement UI trên trang OCR hiện có: source/refresh/status và editor ảnh nguồn; numeric X/Y/W/H%, labels bên cạnh màu, tên/order/enable/delete, Apply một lần qua atomic save; mất quyền capture có nút chọn nguồn/thử lại. Preview source.open dùng roi_rects_px=None để thấy toàn nguồn; runtime dùng các rect ROI bật. Dùng lifecycle generation guard hiện có cho legacy selector, thêm preview state machine cùng bảo đảm intent; không gọi native wait trên GUI.
- [ ] Run cùng command PASS cộng `.venv/Scripts/python.exe -m pytest -q tests/test_dialogue_worker_integration.py tests/test_worker_blocks.py tests/test_block_app_integration.py tests/test_controller_integration.py tests/test_capture_exclusion.py`. Checkpoint end-to-end fake path; không kết luận WGC thực từ fake tests.

### Task 7: Regression, đóng gói và nghiệm thu thực tế

**Files:** Modify `main.spec`, `requirements-build.lock`, `docs/testing/window-capture.md`, `docs/testing/game-controls.md`, `docs/testing/game-dialogue-overlay.md`; Test `tests/test_capture_bundle.py`, `tests/test_capture_regressions.py`, existing capture/dialogue/controller suites.

**Interfaces:** Không thêm API sản phẩm. PyInstaller bundle gồm native extension/DLL dependencies được Task0 xác minh; lazy import lỗi trả EngineError thay vì crash trước khi người dùng chọn MSS.

- [ ] Thêm test wheel absent/native load failure → MSS vẫn import/chạy, WGC báo lỗi rõ; legacy config/selector giữ output; integration stress fake100start-stop không leak session/queue/buffer; all late callback paths đã retire không đổi frame. Không tạo test chỉ khẳng định source chứa một chuỗi collect_all.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q tests/test_capture_bundle.py tests/test_capture_regressions.py`; xác nhận FAIL trước khi thêm hooks/handling cần thiết.
- [ ] Đóng gói bằng `.venv-build/Scripts/python.exe -m PyInstaller --noconfirm main.spec`; thêm collect dynamic libs/extension cụ thể sau khi kiểm tra wheel, giữ manifest OCR/language packs và tránh đưa secrets/dev paths vào bundle. Build không được nâng các pin runtime khác.
- [ ] Run `.venv/Scripts/python.exe -m pytest -q` với network/desktop blocked theo conftest; kết quả mong đợi không failure mới, các skip có lý do. Không dùng số91 của audit cũ làm kết quả lần này.
- [ ] Manual bundle matrix: 1/3/8ROI, MSS/WGC, hai overlay modes; window/borderless; DPI100/125/150%, origin âm; move cùng monitor, resize, cross-monitor, minimize/restore/close, apprestart chọn lại window, hotswap monitor và nhiều window trùng tên. Verify overlay/toolbar không lọt OCR và user exclusion có tác dụng thật. Fullscreen độc quyền/HDR nếu thử phải báo kết quả hỗ trợ/không hỗ trợ, không coi là acceptance guarantee.
- [ ] Đo riêng capture/copy time, OCR time/ROI, scan age, số request và RAM/native handle sau30start-stop; so một ROI cũ trước/sau trên cùng clip/crop. Ghi median/p95 và điều kiện máy; tối đa buffer/session/queue là tiêu chí cứng, không gán SLA tốc độ chưa đo. Nhiều ROI không được gọi thêm API chỉ vì nguồn di chuyển.
- [ ] Cập nhật manual results PASS/FAIL cụ thể, các giới hạn còn lại và hướng quay lại MSS. Review cuối toàn bộ source→OCR→route→paint cùng lifecycle; chỉ báo hoàn thành khi cả fake tests và native/bundle gate đạt. Nếu thiếu môi trường native, ghi rõ phần chưa xác minh thay vì đánh dấu xong.

## Chạy test trong sandbox Windows

Nếu TEMP mặc định bị hạn chế như audit trước, tạo thư mục tạm **mới** dưới workspace trong process chạy test; không sửa config thật hoặc đổi ACL hệ thống. Ví dụ prefix cho từng phiên PowerShell:

```powershell
$captureTestRoot = Join-Path (Get-Location).Path ('scratch/capture-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $captureTestRoot | Out-Null
$env:TEMP = $captureTestRoot
$env:TMP = $captureTestRoot
# Chạy command pytest của task; dùng --basetemp (Join-Path $captureTestRoot 'pytest') nếu cần.
```

Không chạy live WGC/desktop trong unit tests. Native probe/manual matrix phải là thao tác chủ động trong phiên triển khai. Trước cleanup recursive, xác minh absolute path thuộc workspace và chỉ xóa thư mục do phiên test đó tạo.

## Tự rà soát kế hoạch

- Spec coverage: profile/migration Task1; normalized/pixel/exclusion Task2; bounded scan/desktop Task3; identity/native lifecycle Task0+4; independent session/request/render Task5; UI/app lifecycle Task6; frozen bundle/native acceptance Task7.
- Type consistency: profile/context dùng xuyên suốt; giữ public request key bốn phần, legacy constructors có default; MSS crop origin tách khỏi full source size; ROI-local result qua router trước khi đổi sang source canvas.
- Review Focus: mỗi nhóm lỗi phía trên có test hoặc native acceptance ghi đúng task; native behavior không suy ra từ mocks.
- Điểm chưa được xác nhận thực nghiệm: WGC client mapping, SDR handling trên game đích, stop latency và PyInstaller dependencies. Task0/7 đặt cổng kiểm chứng, không coi đây là chi tiết đã giải quyết.
- Execution handoff: đọc cả spec và plan, duyệt cách hiển thị nhiều ROI ở subtitle cùng giới hạn một màn hình. Chỉ bắt đầu task sau khi người dùng yêu cầu triển khai; khuyến nghị thực thi tuần tự vì các task phụ thuộc chặt vào contracts/geometry/router.
