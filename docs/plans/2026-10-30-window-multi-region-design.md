# Capture cửa sổ và nhiều vùng OCR — thiết kế đề xuất

Ngày: 30/10/2026. Trạng thái: bản đề xuất để duyệt, chưa triển khai. Người dùng yêu cầu lập kế hoạch cho capture cửa sổ, nhiều vùng quét và vùng loại trừ; các giới hạn/phương án dưới đây do người lập kế hoạch đề xuất, chưa phải quyết định người dùng đã xác nhận. Debug ảnh/OCR/render đầy đủ thuộc hạng mục sau.

## Mục tiêu và trải nghiệm

- Chọn nguồn **Màn hình** hoặc **Cửa sổ**; chế độ màn hình hiện có tiếp tục dùng được.
- Trên một nguồn, tạo 1–8 vùng OCR có tên, ID ổn định, thứ tự và bật/tắt; thêm tối đa 16 hình chữ nhật loại trừ. Mặc định một vùng OCR, không có vùng loại trừ.
- Ảnh nguồn được lấy một lần cho một lượt xử lý; các vùng OCR được cắt từ cùng ảnh, không gọi capture lại cho từng vùng.
- Chữ hiện dần, bản dịch đang chờ và kết quả trả muộn của vùng A không được làm thay đổi vùng B.
- Ở chế độ **Phụ đề nổi**, mỗi vùng có một lượt thoại riêng; ghép các bản dịch đang còn hiệu lực theo thứ tự vùng, cách nhau một dòng trống. Không ghép chữ nguồn của nhiều vùng thành một request. Khi chỉ có một vùng, hành vi và cách hiển thị giữ tương đương hiện tại.
- Ở chế độ **Theo vị trí chữ**, mỗi vùng chia khối độc lập; quy đổi khối về cùng canvas nguồn trước khi dùng layout/overlay hiện có. Không gom hai dòng thuộc hai vùng thành một khối.
- Giữ một ngôn ngữ nguồn/đích, provider và chế độ hiển thị chung. Chưa thêm provider, ngôn ngữ, lịch quét hoặc chế độ hiển thị riêng cho mỗi vùng.

## Căn cứ trong mã hiện tại

- `main.py:105–130`: tạo worker, đồng bộ một `CaptureGeometry`, nối `blocks_updated` và `subtitle_updated` tới overlay.
- `core/worker.py:430–453,517–577`: `mss.grab`, ảnh xám, một thumbnail/change detector, một bộ OCR retry và một `DialogueObservation` cho một vùng. Không dùng helper legacy `_process_frame` làm điểm tích hợp.
- `core/dialogue/coordinator.py`: một timer GUI, một session, nhận observation/result qua queued signals; đây là cơ chế cần giữ.
- `core/blocks/models.py` và `geometry.py`: một `CaptureGeometry` gắn một màn hình; `BlockJob.request_key` là `(revision, block_id, turn_id, text_version)`.
- `ui/settings_coordinator.py:267`: lưu vùng trước, sau đó áp dụng worker. `ui/region_selection.py`: giữ ý định chạy/dừng, khôi phục UI, chặn callback của lần chọn cũ và lúc quit.
- `ui/block_overlay.py`: một cửa sổ transparent với capture exclusion; `ui/overlay.py:328–351`: chặn revision/sequence cũ. Giữ các bảo đảm này.
- `core/config.py`: schema ngoài hiện là 1, ghi atomic, giữ trường khác; `main.spec`: PyInstaller onedir. Checkout có sẵn nhiều thay đổi người dùng; không gộp hoặc ghi đè chúng.

## Các phương án đã cân nhắc

| Phương án | Ưu điểm | Đánh đổi |
|---|---|---|
| Chỉ dùng MSS và theo dõi vị trí cửa sổ | Ít dependency mới | Vẫn chụp desktop theo tọa độ, không đem lại nguồn ảnh WGC; cửa sổ bị che vẫn là vấn đề khác. |
| **MSS cho màn hình + adapter WGC cho cửa sổ** | Giữ đường chạy cũ; dùng Python native wheel; phần OCR/dịch/overlay dùng chung | Thêm lifecycle callback/native thread, ánh xạ viền/client và kiểm tra đóng gói. Đây là phương án đề xuất. |
| Tự viết bridge WGC C++/Rust/.NET | Kiểm soát API thấp nhất | Thêm toolchain và artifact native cần bảo trì; chưa có lý do để bắt đầu ở đây. |

Candidate: `windows-capture==2.0.1`, lazy import trong adapter WGC, không đổi các pin Paddle/NumPy/OpenCV hiện có. Đã đọc metadata PyPI và Python source trong wheel `cp39-abi3-win_amd64`: có `window_hwnd`, `start_free_threaded`, `CaptureControl.stop/wait`. Chưa cài/chạy native capture hoặc xác nhận PyInstaller; Task 0 là cổng kiểm chứng bắt buộc trước tích hợp. Không tự chuyển sang thư viện khác khi cổng này thất bại.

Nguồn chính: [Python wrapper](https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/windows_capture/__init__.py), [PyPI release 2.0.1](https://pypi.org/project/windows-capture/2.0.1/). Việc wrapper có API phù hợp là bằng chứng khả năng tích hợp, không phải bằng chứng hiệu năng hoặc tương thích game.

## Giới hạn bản đầu

- Tính năng nguồn cửa sổ mới yêu cầu Windows 10 build 19041 trở lên, Python x64; chạy bằng quyền app hiện tại. Không tự nâng quyền.
- Một nguồn hoạt động tại một thời điểm. Nguồn mới phải nằm trọn trên một màn hình; một cửa sổ vắt qua hai màn hình hoặc phần client ngoài màn hình sẽ tạm ngưng xử lý và báo cách khắc phục. Không tự đoán tỷ lệ trên màn hình mixed-DPI.
- Chưa cam kết fullscreen độc quyền, HDR/tone mapping hoặc cửa sổ có nội dung bị hệ điều hành bảo vệ. Task 0 xác nhận đường SDR BGRA8; format khác phải báo không hỗ trợ thay vì dịch ảnh sai màu/đen.
- Vùng OCR cùng nguồn không được chồng diện tích; chạm cạnh được phép. Vùng loại trừ được chồng nhau và có hiệu lực trên mọi vùng OCR giao với nó.
- Bản đầu không tăng số worker Paddle: vẫn một owner OCR, một owner SDK dịch. Tổng số track dịch đang hoạt động tối đa 32, hàng đợi dịch tối đa 32 như thiết kế hiện tại.
- Capture callback chỉ giữ một ảnh mới nhất, cộng tối đa một ảnh đang được OCR sử dụng; không tạo lịch sử ảnh, không lưu video, không gửi ảnh qua API dịch.

## Nguồn, tọa độ và định danh

**Nguồn màn hình:** chọn monitor theo device name từ `ScreenGeometryProvider`. Backend MSS chụp bounding rectangle của các vùng OCR đang bật bằng một `grab`; metadata giữ offset bounding rectangle trong monitor để quy đổi về canvas monitor. Khoảng trống giữa các ROI không được OCR.

**Nguồn cửa sổ:** liệt kê cửa sổ top-level có thể chọn bằng Win32; loại cửa sổ của chính app, hidden/cloaked/tool windows không phù hợp. Lựa chọn giữ `HWND + PID + process creation time` trong RAM; thiếu quyền xác minh identity thì báo lỗi. Không chọn theo substring title, không gắn lại một HWND đã tái sử dụng, không tự bám cửa sổ khác khi game đóng.

Capture WGC trả ảnh bao gồm phạm vi cửa sổ mà native API cung cấp. Adapter phải xác định chính xác `capture_bounds_px`, `client_bounds_px`, padding/row stride, rồi cắt client image. Không giả định ảnh WGC bằng `GetWindowRect` hoặc chỉ trừ một số pixel viền cố định. Task 0 kiểm tra `DwmGetWindowAttribute` và phép `ClientToScreen` trên cửa sổ test có marker; nếu kích thước/offset không giải thích được thì trả `capture_geometry`, không scale đoán.

**Vùng:** lưu `NormalizedRect(x,y,width,height)` trong hệ 0..1 của client image (window) hoặc monitor (desktop). Khi resize, vùng co giãn tương đối; không bảo đảm nó tự nhận biết vị trí HUD nếu game đổi layout/aspect ratio. Cho cập nhật preview/chỉnh lại vùng. Mapping raster dùng floor cạnh trái/trên, ceil phải/dưới, clip trong ảnh, reject vùng rỗng; các ROI không giao nhau trong tọa độ liên tục nhưng rounding có thể chung một pixel cạnh, khi đó gán pixel chung cho ROI đứng trước để không OCR/dịch trùng.

**Vùng loại trừ:** áp dụng trên bản sao crop dành cho OCR, không sửa buffer capture dùng chung. Đồng thời loại mọi `OcrSpan` có bounding rectangle giao diện tích với vùng loại trừ, rồi dựng lại `OcrResult.text` từ các span còn lại theo thứ tự OCR trả về. Không dùng `OcrResult.text` chưa lọc cho subtitle. Nếu ROI bị loại trừ toàn bộ, gửi kết quả OCR rỗng hợp lệ để session kết thúc lượt cũ theo policy, không giữ phụ đề vô hạn. Riêng nguồn desktop, tiếp tục nhận mask phụ đề động hiện có từ `overlay.capture_geometry_changed`, đổi global physical rect sang source-local và kết hợp user exclusions trước change detection/OCR. Không áp mask tọa độ desktop lên ảnh window WGC.

**Cửa sổ di chuyển:** GUI geometry provider poll mỗi 100 ms; thay origin trong cùng monitor, không đổi kích thước client, chỉ cập nhật `geometry_sequence`/canvas mapping. Các khối hiện tại được vẽ lại theo geometry mới dù OCR tiếp theo đang chờ; không reset lượt thoại hoặc gọi API chỉ vì origin đổi.

**Resize/DPI/monitor/source changes:** thay kích thước raster, nguồn, màn hình hoặc cấu hình vùng làm tăng `revision` và `binding_epoch`; xóa presentation/pending cũ trước khi nhận observation mới. Với thay đổi cần mở lại WGC, debounce 200 ms sau thay đổi cuối, đóng/drain nguồn cũ rồi mở nguồn epoch mới; không chờ debounce mới xóa overlay. Chờ frame có kích thước phù hợp context mới; callback từ epoch cũ không được đưa trở lại buffer. Không trộn frame cũ và metadata resize mới.

## Pipeline và hợp đồng chính

Thêm package `core/capture/` thay vì đưa Win32/native callback vào coordinator hoặc UI settings.

| Thành phần | Trách nhiệm |
|---|---|
| `models.py` | Immutable profile, region, source identity, frame, context và observation batch. Không phụ thuộc QWidget. |
| `profile.py` | Validation, migration JSON, lưu trữ qua atomic config hiện có. |
| `geometry.py` | Normalized ROI → raster crop → source canvas → `CaptureGeometry`; vùng loại trừ. |
| `source.py`, `desktop.py`, `wgc.py` | Protocol nguồn ảnh, MSS adapter và WGC adapter. |
| `windows.py` | Win32 enumerate/identity/bounds/minimized; ctypes có argtypes/restype x64. |
| `scan.py` | State nhận diện thay đổi/retry/last-scan riêng từng region; lịch quét và lọc exclusion. |
| `sessions.py` | Nhiều dialogue session, namespace ID, gom job/result/frame; dùng một coordinator timer. |
| `ui/window_geometry.py` | GUI QObject poll native metadata, ghép Qt/physical monitor mapping, phát context thay đổi. |
| `ui/capture_preview.py` | QThread lấy một ảnh preview, đóng nguồn xong mới phát finished; không chạy OCR. |
| `ui/capture_settings.py`, `ui/capture_regions_dialog.py` | Chọn nguồn, bảng vùng và chỉnh trên ảnh nguồn; giữ phong cách Qt hiện có. |

Interfaces do implementation plan xác định chi tiết. Giữ `BlockJob`/`BlockTranslationResult` và request key 4 phần: router cấp global `block_id` số nguyên duy nhất cho `(region_id, local_track_id)` trong một revision, có bảng route ngược. Không dùng `region_index*32` vì local track ID hiện tăng không giới hạn theo thời gian. Khi track hết hiệu lực, bỏ route nhưng không tái sử dụng global ID trong cùng revision.

`DialogueCoordinator` vẫn là nơi duy nhất sở hữu timer/GUI state, nhận observation batch của các ROI được quét. ROI chưa đến lượt hoặc OCR lỗi không được hiểu thành OCR rỗng. Mỗi ROI có session và hạn freshness riêng; mất chữ ở một ROI không xóa các ROI khác. Router đổi cả jobs, results và active-turn tuples sang cùng global ID namespace; không chỉ đổi ID trong job rồi giữ active keys cục bộ.

Chế độ blocks chia quota 32 track cho N ROI bật: `divmod(32,N)`, phần dư cấp theo thứ tự cấu hình. `BlockSession(max_tracks=32)` có tham số giới hạn để router cấp quota; default giữ hợp đồng cũ. UI hiển thị giới hạn chia khối khi nhiều ROI. Subtitle mỗi ROI một track, tổng tối đa 8. Route jobs/results qua một `BlockTranslationWorker` hiện có, giữ rate-limit/retry dùng chung provider và cơ chế latest-per-track.

Mỗi vòng worker lấy một snapshot nguồn, chọn ROI đến hạn theo lần scan cũ nhất, tie-break ưu tiên nhu cầu xác nhận thoại rồi thứ tự cấu hình. Sau mỗi OCR kiểm tra revision/stop và budget `interval_ms`; nếu đã hết budget, dừng sweep, vòng kế tiếp lấy frame mới và bắt đầu vùng còn lâu chưa quét. Một OCR riêng lẻ không bị cắt ngang. Static ROI được lên lịch kiểm tra lại sau 1 giây; tốc độ thực tế còn phụ thuộc số vùng và thời gian OCR. Không hứa 8 vùng chạy nhanh như 1 vùng; hiển thị độ trễ scan khi freshness không giữ được.

## Lifecycle và trạng thái lỗi

- `idle → opening → ready`; source selected nhưng chưa có frame đầu tiên quá 2 giây: báo `capture_timeout`, nút thử lại. Không retry vô hạn và không đổi sang desktop ngầm.
- WGC có thể không phát frame mới khi nội dung tĩnh. Sau frame đầu, không dùng việc thiếu callback làm bằng chứng game đã đóng; reuse frame mới nhất chỉ khi identity, client size và trạng thái cửa sổ vẫn hợp lệ.
- Minimize/ẩn/đóng/identity sai/capture failed: ngừng phát OCR observations, invalidate kết quả đang chờ và clear overlay ngay khi phát hiện. Giữ cấu hình vùng. Window closed yêu cầu chọn lại; minimize được chờ restore, revalidate và bắt đầu epoch mới khi frame hợp lệ đến.
- Capture callback chỉ copy ảnh nhận đủ điều kiện (throttle tối đa 10 lần/giây), thay latest buffer dưới lock và ghi nhận timestamp; không OCR, không SDK, không gọi QWidget, không phát một Qt event cho mỗi video frame. Riêng terminal failure/closed gửi tối đa một terminal event mỗi epoch qua queued signal về lifecycle GUI, có guard epoch; lifecycle invalidate revision, clear overlay/pending mà không đợi OCR đọc status. Trạng thái nguồn vẫn được lưu thread-safe để owner thực hiện cleanup. Test phải giữ OCR đang bận khi native phát lỗi.
- `close()` nguồn chạy trên owner worker, ngoài native callback; stop và join native thread xong mới báo owner finished. GUI không join/block. Nếu drain quá 3 giây, hiển thị đang dừng và chặn start mới; không terminate thread, không phát `shutdown_finished` giả.
- Chọn/chỉnh vùng: giữ running intent, dừng/drain runtime worker → mở preview worker lấy một frame toàn nguồn (không chỉ bounding ROI hiện có) → drain preview source → mở editor. Cancel/Escape giữ nguyên profile. Apply validate toàn bộ và lưu atomic một lần rồi mới áp dụng worker. Nếu resize khi editor mở, yêu cầu cập nhật ảnh trước khi lưu; origin-only change không làm mất lựa chọn.
- Ý định Start của người dùng tách khỏi việc worker hiện đang chạy: `ControllerWindow.capture_run_requested` vẫn true khi minimize/tạm mất nguồn để restore có thể tự tiếp tục. Người dùng bấm Stop hoặc Quit thì false và restore không được tự Start; Start khi chưa chọn đúng nguồn không đổi intent thành true.
- `RegionSelectionLifecycle` mở rộng làm owner tổng hợp runtime worker và preview worker: `request_shutdown()` vô hiệu callback/resume, dừng cả hai, chỉ phát `shutdown_finished` một lần khi `worker.is_drained` và preview source đã đóng. `main.py` thay kết nối barrier từ worker trực tiếp bằng signal tổng hợp này; participant language_packs giữ nguyên. Quit khi runtime đã drain nhưng preview native còn đóng dở vẫn phải chờ preview.

## Cấu hình và tương thích

Thêm trường `capture_profile` có `version=1` trong config schema ngoài hiện tại, không đổi các khóa credential/provider. Profile gồm `source_kind`, `monitor_name` hoặc `window_hint`, danh sách ROI/exclusions; chỉ persist tên/process hint dễ hiểu, không persist HWND/PID/process creation time. Khi mở lại app với window profile, giữ vùng nhưng yêu cầu chọn lại nguồn trước khi Start.

Không có profile: chuyển một legacy `region` nằm trọn một monitor thành một ROI tương đương pixel, chưa tự ghi config khi chỉ đọc. Legacy subtitle region vắt qua hai monitor giữ nguyên đường MSS cũ; muốn dùng editor nhiều ROI phải chọn lại nguồn một màn hình. Không âm thầm cắt/di chuyển vùng cũ. Profile mới sai dữ liệu phải báo lỗi và cho quay lại desktop legacy; không tự xóa profile để tiếp tục chạy một nguồn khác.

`load_region`/`save_region`/`set_region` và selector cũ giữ compatibility wrapper cho legacy caller/test. App chính chuyển sang `load_capture_profile`/`apply_capture_profile`/`configure_capture`. Chỉnh profile mới không ghi đè legacy `region`; quay lại mode cũ có vùng cũ của người dùng.

## UI tối thiểu

Trong trang OCR hiện có: nguồn Màn hình/Cửa sổ, nút chọn nguồn/cập nhật danh sách, nguồn đang chọn và trạng thái; nút **Quản lý vùng quét**. Editor dùng ảnh nguồn có khung OCR và khung loại trừ phân biệt bằng cả nhãn lẫn màu; bảng tên, bật/tắt, loại vùng, thứ tự, chỉnh/xóa. Kéo vẽ hoặc nhập X/Y/W/H theo phần trăm; nút lên/xuống và bàn phím đủ dùng, Escape hủy. Tất cả là draft cho đến Apply; lỗi hiển thị cạnh trường và tập trung về trường đầu tiên.

Toolbar **Chọn vùng** mở editor của nguồn hiện tại; không vô tình chuyển WGC sang MSS. Mặc định vùng mới tên `Vùng 1`, `Vùng 2`...; không suy luận vai trò hội thoại/menu. Giữ nút **Áp dụng** vô hiệu khi ROI chồng nhau, quá giới hạn, ID trùng hoặc không còn ROI bật.

## Điều kiện hoàn thành

1. Chứng minh WGC đúng HWND với hai cửa sổ trùng tên, title thay đổi, move/resize/minimize/restore/close; marker xác minh client mapping và row stride.
2. 1, 3 và 8 ROI đọc độc lập; exclusion đúng cả subtitle và blocks; không có request do pixel chỉ nằm ngoài ROI thay đổi.
3. Bản dịch trả muộn sau đổi nguồn/resize/xóa ROI/quit không xuất hiện; chuyển giữa hai mode không trộn jobs.
4. Move cùng monitor cập nhật vị trí block khi OCR đang bị giữ, không thêm request dịch do move; DPI 100/125/150%, monitor origin âm, monitor disconnect đều có test định nghĩa kết quả.
5. Callback/thread/buffer giữ giới hạn, start-stop lặp không tạo native session chồng nhau; GUI tiếp tục nhận sự kiện khi đóng native chậm.
6. Legacy config/selector/game controls và các hợp đồng dialogue/cache/retry vẫn qua test; không đụng thay đổi người dùng có sẵn.
7. PyInstaller onedir thật chạy được WGC/MSS trên máy đích không cần Rust/.NET hoặc môi trường phát triển; trường hợp DLL thiếu có lỗi thao tác được.

Thực hiện theo [implementation plan](C:/Users/Admin/Documents/Realtime_Translator_Sreen/docs/plans/2026-10-30-window-multi-region-plan.md). Chưa có kết quả benchmark hay xác nhận tương thích native trong tài liệu này.
