# Kiểm chứng overlay theo khối — 2026-10-23

## Tự động

- Baseline trước thay đổi: 230 passed, exit 0.
- Sau tích hợp và sửa theo review: **286 passed in 7.70s, exit 0**; fake OCR/API, Qt offscreen.
- Bao phủ polygon lỗi, grouping, track trùng chữ, typewriter deadline, revision/source cũ, hàng chờ thay thế, retry hữu hạn, đóng client đúng thread, stop không chờ API, layout Việt/CJK, persistence rollback, DPI âm và scale 100/125/150/200%.
- Các test bổ sung xác nhận vị trí mới nhất trong lúc request bị giữ, không mask pixel ở blocks, đổi mode chờ request cũ xong, cache dùng chung cho hai ID cùng chữ, cooldown Gemini/Retry-After và khóa revision khi auth lỗi.

## Review cuối

Một reviewer độc lập đọc toàn bộ thay đổi và các ràng buộc. Đã sửa hai phát hiện bằng test RED → GREEN:

- Đóng cửa sổ bằng X/Alt+F4 gọi cùng đường thoát an toàn, chờ capture và request đang chạy dừng trước `shutdown_finished`.
- Thoát drag/mode invalidation trả lại xuyên chuột và con trỏ mặc định cho phụ đề.

Minor để lại: gốc canvas Qt làm tròn xuống pixel nguyên có thể lệch dưới một logical pixel ở DPI phân số. Công thức dữ liệu vẫn dùng số thực; chưa hiệu chỉnh phần dư khi paint. Cần đánh giá trên thiết bị DPI phân số thật trước khi tinh chỉnh.

Quyết định triển khai: dùng checkout feature hiện có theo hướng dẫn desktop, giữ các file người dùng; thêm signal `revision_changed` để GUI xóa nội dung cũ ngay khi start/stop/retry. Không cần cơ chế API hoặc dependency mới.

## Windows thật

Lệnh: `.venv/Scripts/python.exe docs/testing/block_overlay_smoke.py` (không dùng API key/OCR).

Kết quả: exit 0, màn hình `\\.\DISPLAY1`, scale 100%, overlay_visible=true, protected=true, click_through=true, errors=[], mean_difference=0.0, exact_original_pixels=true.

- PASS: cửa sổ canvas thật hiện cùng hai lớp native Qt; Set/GetWindowDisplayAffinity thành công.
- PASS: ảnh mss trước/sau khi canvas phủ nền hồng đặc và bản dịch giống nhau từng pixel; giữ checkerboard/chữ gốc, không có mảng đen.
- PASS: cờ WindowTransparentForInput và WA_TransparentForMouseEvents trong test; kiểm chứng click vào game thực tế: Chưa chạy.
- Focus trong game: Chưa chạy; có WindowDoesNotAcceptFocus/WA_ShowWithoutActivating.
- Tương tác di chuyển chữ trong lúc API giả bị giữ, stop/restart: kiểm thử tự động; chơi game thực tế: Chưa chạy.
- Scale vật lý 125/150/200%, màn hình gốc âm: Chưa chạy trên thiết bị thật; phép biến đổi số đã kiểm thử.
- OBS/bản ghi hình: Chưa chạy. Overlay có thể không xuất hiện theo lựa chọn đã duyệt.
- Phụ đề cũ: bộ hồi quy mask/stabilization/preset/drag PASS; kiểm tra game thủ công: Chưa chạy.

## Hiệu năng trên video người dùng

Working set/private bytes, CPU, độ trễ dịch, số request trên video Genshin: Chưa chạy. Không sử dụng API key thật hoặc thay đổi config.json của người dùng trong đợt kiểm thử. Chưa có kết luận cải thiện RAM so với bản cũ/MORT.

## Cách dùng

Mở trang Tùy biến Phụ đề, chọn **Theo vị trí chữ**, chọn vùng OCR nằm trọn trên một màn hình rồi bắt đầu quét. Có thể chuyển về **Phụ đề nổi**. Chế độ theo vị trí chữ yêu cầu Windows 10 build 19041 trở lên và capture exclusion thành công; lỗi được hiển thị, không tự đổi mode đã lưu.
