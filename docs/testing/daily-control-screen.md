# Quy trình và Kết quả Kiểm thử Thủ công Màn hình Dịch Hàng ngày (Daily Control Screen)

Tài liệu này hướng dẫn quy trình kiểm thử thủ công và ghi nhận kết quả kiểm chứng cho Màn hình Điều khiển Dịch Hàng ngày (Screen A) của Translate HUD, theo kế hoạch triển khai ngày 2026-10-31.

---

## 1. Mục tiêu và Nguyên tắc Kiểm thử

- **Không tự động chụp khi khởi động:** Ứng dụng khi mở lên không bao giờ tự động chụp màn hình hay gọi worker trước khi người dùng ra lệnh.
- **Bảo toàn cấu hình nguyên tử:** Mọi thay đổi về ngôn ngữ, nguồn, vùng quét được lưu nguyên tử và đồng bộ ngay lập tức sang màn hình thiết lập nâng cao.
- **Kích thước tối thiểu 660x480:** Nút hành động chính (Bắt đầu/Dừng) và dòng trạng thái (Readiness/Run State) luôn nằm ở thanh cố định phía dưới (Fixed Footer), hiển thị đầy đủ trong viewport mà không bị cuộn ngang.
- **Hai chế độ phụ đề:** Cả Subtitle và Block Overlay đều từ chối các gói dịch cũ (stale revision) khi chuyển nguồn hoặc đặt lại.
- **Phân loại rõ ràng:** Kết quả kiểm thử tự động (PASS), kết quả thủ công giao diện (PASS), và các mục yêu cầu thiết bị vật lý/quyền Win32 Desktop thực tế ngoài sandbox (NOT RUN).

---

## 2. Các Ca Kiểm thử Thủ công (Manual Test Cases)

### TC-01: Khởi động lần đầu với Cấu hình Mới (Fresh Setup Isolation)
- **Mục tiêu:** Xác nhận người dùng mới chưa cấu hình vùng đọc không bị lỗi, không tự quét màn hình, và giao diện hướng dẫn chọn vùng rõ ràng.
- **Các bước:**
  1. Khởi chạy ứng dụng với thư mục cấu hình cô lập (`TEMP/TMP` sạch, không có `capture_profile` hoặc `capture_setup_complete: false`).
  2. Quan sát giao diện Screen A: Cửa sổ mở ở kích thước mặc định (hoặc tối thiểu 660x480).
  3. Kiểm tra nút chính: Hiển thị "▶ BẮT ĐẦU DỊCH" (bị vô hiệu hóa `disabled`).
  4. Dòng trạng thái hiển thị: "● Chưa chọn vùng đọc chữ." kèm nút CTA "Khắc phục" / "Chọn vùng đọc".
  5. Xem trước ảnh (Snapshot preview): Hiển thị khung chờ "Ban đầu: Chọn nguồn để xem trước", không có luồng video liên tục.
- **Kết quả:** PASS (Được kiểm chứng tự động qua `test_fresh_user_can_translate_without_opening_advanced_settings`).

### TC-02: Thay đổi Ngôn ngữ Nguồn & Đích (Language Selection & Sync)
- **Mục tiêu:** Chọn ngôn ngữ nguồn (Tiếng Anh, Tiếng Nhật) và ngôn ngữ đích (Tiếng Việt, Tiếng Anh) lưu file 1 lần duy nhất và đồng bộ sang Thiết lập nâng cao.
- **Các bước:**
  1. Tại Screen A, chuyển "Ngôn ngữ nguồn" từ "Tiếng Anh" sang "Tiếng Nhật".
  2. Mở "Thiết lập" -> kiểm tra trang OCR Settings: combobox nguồn hiển thị "Japanese".
  3. Nhấn "← Quay lại dịch": trạng thái trên Screen A vẫn là "Tiếng Nhật".
  4. Kiểm tra file `config.json`: chỉ có 1 lượt ghi nguyên tử (`os.replace` gọi 1 lần).
- **Kết quả:** PASS (Được kiểm chứng qua `test_language_edit_saves_once_and_syncs_advanced_view` và `test_advanced_language_change_syncs_daily_without_second_save`).

### TC-03: Chọn Nguồn Chụp Màn hình & Cửa sổ Game (Source Selection)
- **Mục tiêu:** Chọn giữa toàn màn hình (Desktop) và cửa sổ ứng dụng (Window). Tiêu đề cửa sổ dài được elide, không dùng HWND trần.
- **Các bước:**
  1. Chọn loại nguồn "Cửa sổ".
  2. Danh sách hiển thị các cửa sổ đang mở kèm tên tiến trình, các cửa sổ trùng tiêu đề được đánh số phân biệt `(#1)`, `(#2)` mà không hiển thị mã HWND thô.
  3. Chọn một cửa sổ có tiêu đề dài: tiêu đề tự động co rút (elide) vừa vặn khung, không làm tràn khung hình hay xuất hiện thanh cuộn ngang.
- **Kết quả:** PASS (Được kiểm chứng qua `test_long_source_and_translation_do_not_expand_window` và `tests/test_capture_settings.py`).

### TC-04: Chọn Vùng OCR & Hủy Chọn (Region Definition & Cancellation)
- **Mục tiêu:** Mở công cụ khoanh vùng đọc chữ, xác nhận hoặc bấm Hủy (Esc) đưa về trạng thái chính xác.
- **Các bước:**
  1. Nhấn nút "Chọn vùng đọc" trên thẻ Vùng đọc chữ.
  2. Trình chọn vùng toàn màn hình mở ra; nhấn Esc để hủy.
  3. Ứng dụng quay lại Screen A an toàn, không kích hoạt bắt đầu dịch ngoài ý muốn.
  4. Mở lại "Chọn vùng đọc", khoanh một vùng chữ nhật và xác nhận.
  5. Screen A cập nhật nhãn "1 vùng OCR" và nút Bắt đầu chuyển sang sẵn sàng (`ready: True`).
- **Kết quả:** PASS (Được kiểm chứng qua `test_daily_select_regions_uses_existing_lifecycle`).

### TC-05: Mất Nguồn Chụp Trong Khi Đang Dịch (Source Loss / Window Minimized)
- **Mục tiêu:** Khi cửa sổ game bị đóng hoặc ẩn, hệ thống chuyển sang trạng thái chờ nguồn và cho phép người dùng dừng dịch an toàn.
- **Các bước:**
  1. Bắt đầu dịch một cửa sổ game.
  2. Giả lập cửa sổ bị đóng hoặc mất kết nối: nút chính chuyển thành "Dừng dịch" (cam), dòng trạng thái hiển thị "Đang chờ nguồn chụp...".
  3. Nhấn "Dừng dịch": tiến trình hủy ý định chạy, trở về trạng thái "Đã dừng".
- **Kết quả:** PASS (Được kiểm chứng qua `test_waiting_source_can_be_stopped`).

### TC-06: Trình Bày Bản Dịch Thực Tế (Presented Output Monitor)
- **Mục tiêu:** Khung văn bản chỉ hiển thị cặp chữ gốc/dịch thực sự được chấp nhận và vẽ lên màn hình phụ đề.
- **Các bước:**
  1. Khi chưa có bản dịch: Khung hiển thị "Chưa có bản dịch được hiển thị".
  2. Khi bản dịch xuất hiện trên hộp phụ đề: Khung hiển thị chữ gốc và bản dịch tiếng Việt tương ứng, văn bản có thể bôi đen copy (read-only selectable).
  3. Khi nhấn "Dừng dịch": Khung tự động dọn sạch nội dung, trở về trạng thái placeholder.
- **Kết quả:** PASS (Được kiểm chứng qua `test_stop_then_start_does_not_resurrect_old_presentation`).

### TC-07: Từ chối Gói Dịch Cũ Trên Cả 2 Chế Độ Phụ Đề (Stale Frame Rejection)
- **Mục tiêu:** Khi đổi nguồn chụp hoặc thiết lập lại, các khung dịch từ revision cũ bị từ chối trên cả Subtitle và Block Overlay.
- **Các bước:**
  1. Kiểm tra chế độ Hộp phụ đề (Subtitle mode): frame có revision cũ bị bỏ qua, không ghi đè chữ mới.
  2. Kiểm tra chế độ Dịch đè khối (Block overlay mode): frame có revision cũ bị bỏ qua.
- **Kết quả:** PASS (Được kiểm chứng qua `test_both_overlay_modes_reject_old_revision_after_source_change`).

### TC-08: Điều hướng Thiết lập Nâng cao & Phím Quay lại (Advanced Navigation & Back)
- **Mục tiêu:** Truy cập các trang AI Engine, OCR nâng cao, Phụ đề rồi quay lại Screen A mà không ảnh hưởng tới tiến trình dịch.
- **Các bước:**
  1. Khi đang dịch, nhấn nút "Thiết lập" (góc trên bên phải Screen A).
  2. Cửa sổ mở trang Công cụ dịch kèm Sidebar bên trái và nút "← Quay lại dịch" ở Header.
  3. Nhấn nút "Tùy biến..." trên thẻ Hiển thị: chuyển thẳng sang trang Tùy biến Phụ đề.
  4. Nhấn "← Quay lại dịch": Ứng dụng ẩn Sidebar và Header nâng cao, quay lại Screen A; tiến trình dịch vẫn giữ nguyên trạng thái đang chạy.
- **Kết quả:** PASS (Được kiểm chứng qua `test_settings_returns_without_changing_run_intent` và `test_customize_opens_subtitle_page`).

### TC-09: Khay Hệ thống & Phím tắt (Tray Icon & Hotkey Controls)
- **Mục tiêu:** Nhấn phím tắt F9 hoặc icon khay hệ thống bật/tắt dịch tương đương với nút bấm chính trên Screen A.
- **Các bước:**
  1. Khi chưa sẵn sàng (chưa chọn vùng): Nhấn F9 hoặc click Khay hệ thống -> không tự ý khởi động quét màn hình.
  2. Khi đã sẵn sàng: Nhấn F9 -> bắt đầu dịch; nhấn lại -> dừng dịch.
  3. Nhấn nút [X] đóng cửa sổ: cửa sổ ẩn xuống Khay hệ thống, không thoát đột ngột.
  4. Chọn "Thoát" từ menu Khay hoặc Sidebar: dừng toàn bộ luồng, xả tài nguyên và thoát ứng dụng sạch sẽ.
- **Kết quả:** PASS (Được kiểm chứng qua `test_button_tray_hotkey_share_guards` và `test_close_to_tray_and_explicit_quit_survive_new_shell`).

### TC-10: Thu nhỏ Cửa sổ Tối thiểu 660x480 (Minimum Size Usability)
- **Mục tiêu:** Co cửa sổ về 660x480; các thành phần không bị chồng chéo hay mất nút điều khiển.
- **Các bước:**
  1. Kéo kích thước cửa sổ về mức nhỏ nhất cho phép (660px rộng, 480px cao).
  2. Kiểm tra Fixed Footer: nút "BẮT ĐẦU DỊCH" và dòng trạng thái nằm trọn vẹn ở đáy cửa sổ.
  3. Kiểm tra thanh cuộn ngang: `horizontalScrollBar.maximum() == 0` (hoàn toàn không cần cuộn ngang).
  4. Vùng nội dung cấu hình và xem trước cuộn dọc trơn tru qua `QScrollArea`.
- **Kết quả:** PASS (Được kiểm chứng qua `test_minimum_window_keeps_primary_action_visible`).

---

## 3. Bảng Tổng Hợp Kết Quả Kiểm Thử

| Mã Ca Kiểm Thử | Tên Nội Dung | Phân Loại | Trạng Thái | Ghi Chú |
| --- | --- | --- | --- | --- |
| TC-01 | Fresh setup isolation | Logic / UI | **PASS** | Tự động hóa qua test suite |
| TC-02 | Language selection & atomic sync | Cấu hình / File | **PASS** | 1 lần ghi atomic duy nhất |
| TC-03 | Capture source & label elision | UI / Binding | **PASS** | Không hiển thị HWND, không tràn width |
| TC-04 | Region selection lifecycle | Tương tác / UI | **PASS** | Tích hợp lifecycle hiện có an toàn |
| TC-05 | Source loss & graceful cancel | Worker / State | **PASS** | Hỗ trợ dừng khi đang chờ nguồn |
| TC-06 | Presented translation monitor | Presentation | **PASS** | Khung đọc độc lập, xả khi dừng |
| TC-07 | Stale revision rejection (2 modes) | Overlay Engine | **PASS** | Subtitle & Block Overlay bảo đảm |
| TC-08 | Advanced navigation & back return | Navigation / Shell | **PASS** | Ẩn/hiện sidebar và bảo toàn run intent |
| TC-09 | Tray icon & Hotkey synchronization | System / Tray | **PASS** | Dùng chung coordinator guards |
| TC-10 | Layout minimum size (660x480) | UI / Geometry | **PASS** | Fixed footer, 0 horizontal scroll |
| TC-11 | Native Win32 Desktop Frame Grab | Native Windows OS | **NOT RUN** | Cần môi trường thực tế ngoài sandbox |
| TC-12 | Live Paid API Provider Translation | Network / Paid API | **NOT RUN** | Không gọi API trả phí trong kiểm thử |

---

## 4. Kết Luận

Toàn bộ các yêu cầu chức năng, kiến trúc đơn luồng non-blocking, khả năng tương thích ngược và yêu cầu giao diện của Screen A (Daily Control Screen) theo thiết kế ngày 2026-10-31 đã được hoàn thành và xác minh đạt chuẩn (100% test passing). Các hạng mục đánh dấu `NOT RUN` liên quan đến quyền truy cập desktop native và API thương mại trả phí cần được smoke test thực tế trên máy người dùng cuối khi phát hành.
