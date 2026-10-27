# Rà soát TranslateHUD — 25/10/2026

## Phạm vi và kết quả kiểm chứng

- Đọc luồng ứng dụng Python trong `main.py`, `core/`, `engines/`, `ui/`; đối chiếu test, tài liệu kiểm chứng, dependency và cấu hình đóng gói. Dùng CodeGraph trước khi tra mã nguồn. Không audit độc lập toàn bộ mã C# trong thư mục `MORT/`.
- Đánh giá checkout đang có thay đổi chưa commit, gồm `ui/overlay.py` và test nền phụ đề mới. Không sửa mã sản phẩm, cấu hình người dùng hoặc các thay đổi đang có.
- Chạy suite bằng `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp <thư-mục-mới>` với TEMP/TMP nằm ngoài repository trong writable root: **613 passed in 64.41s, exit 0**.
- Test mặc định dùng Qt offscreen, OCR/capture giả và HTTP giả; không gọi API dịch thật, đọc key thật hay chụp desktop. Các probe bổ sung cũng dùng dữ liệu giả và cấu hình tạm.
- Chưa chạy build executable, benchmark game, kiểm tra click xuyên cửa sổ hoặc thử trực tiếp nhiều màn hình/DPI. Các kết luận tọa độ dưới đây được tái hiện bằng hình học màn hình giả.

## Nền tảng hiện có

Ứng dụng dùng PyQt5, mss, PaddleOCR và OpenAI-compatible SDK/HTTPX. Capture/OCR chạy riêng với backend dịch; coordinator trên GUI event loop quản lý lượt thoại và thời hạn hiển thị. Revision, session, turn và text version giúp loại kết quả cũ. Hai kiểu hiển thị gồm phụ đề chung và khối dịch theo vị trí chữ.

Đã có Google Translate, Gemini, OpenAI, DeepSeek và Custom API; queue giới hạn, cache 300 bản dịch, retry, trạng thái pause/retry riêng cho Google, lưu thiết lập nguyên tử và bảo vệ API key bằng Windows DPAPI. Đây là những phần nên giữ và mở rộng, không cần xây lại từ đầu.

## Lỗi có bằng chứng

### B1 — P1: Worker đã dừng nhưng giao diện vẫn báo đang hoạt động

**Cập nhật sau rà soát:** Đã sửa theo yêu cầu người dùng. Controller đồng bộ khi capture thread kết thúc, giữ ý định restart và bỏ qua thông báo kết thúc cũ khi phiên mới đang chạy. Lỗi engine hiện trong nhật ký UI; capture/OCR có hướng xử lý. Regression quan sát 2 FAIL trước sửa, sau sửa nhóm liên quan 14 PASS và toàn suite **617 PASS, 59.03 giây, exit 0**. Các lỗi B2–B4 chưa được sửa trong đợt này.

**Nguồn:** `core/worker.py:551–561`, `main.py:95`, `main.py:168`, `ui/controller.py:262–283`.

Nếu không mở được bộ chụp màn hình, worker phát lỗi `capture`, dừng backend và đặt `_is_running = False`. Controller chỉ cập nhật trạng thái lúc người dùng bấm Start/Stop, không đồng bộ khi worker tự kết thúc. Trong wiring của `main.py`, lỗi chung được in ra console; chỉ `capture_geometry` đi vào luồng hiển thị lỗi trên controller. Lỗi OCR cũng không có thông báo giải thích tương ứng trên giao diện. Log của service dịch có mã lỗi API, nhưng không thay thế cho thông báo lỗi capture/OCR.

**Tái hiện:** Dùng guard của `tests/conftest.py` để từ chối capture, tạo worker/controller thật và bấm Start qua `start_ocr()`. Kết quả: lỗi `capture`; hai thread đều kết thúc; `is_running() == False`; sidebar vẫn là **Đang hoạt động** và nhật ký rỗng. Probe exit 0.

**Hướng sửa:** Phát tín hiệu trạng thái runtime thống nhất, kết nối việc tự dừng vào controller; hiển thị `EngineError.user_message` cho capture/OCR/API và hành động khắc phục phù hợp. Cần giữ riêng trạng thái OCR đang chạy và dịch đang pause. Bổ sung regression cho lỗi mở capture, lỗi OCR và worker kết thúc ngoài nút Stop.

### B2 — P2: Phụ đề nhảy sai màn hình

**Cập nhật:** Đã sửa 26/10: helper logical geometry và integration giữ màn hình/origin/taskbar/clamp/max width; final suite670 PASS, review sạch. Native nhiều màn hình/DPI chưa chạy.

**Nguồn:** `ui/overlay.py:148–167`, `ui/overlay.py:248–252`.

Preset căn giữa dùng `screen.width()` nhưng thiếu `screen.left()`. Vị trí dưới dùng `screen.height()` nhưng thiếu `screen.top()`. Khi cập nhật chữ, clamp cũng dùng biên từ 10 tới width/height, thay vì biên toàn cục của `availableGeometry()`.

**Tái hiện:** Với màn hình phải `(1920, 0, 1920, 1080)` và overlay `300×60`, preset bottom-center trả `(810, 940)`, trong khi x theo màn hình này phải là 2730. Sau cập nhật chữ overlay vẫn ngoài màn hình đã chọn. Probe cho màn hình trái và phía trên cũng xác nhận không nằm trong hình học mong đợi; exit 0.

**Hướng sửa:** Tính vị trí và clamp theo left/top/right/bottom của màn hình đích; xử lý giới hạn chiều rộng khi đổi màn hình và khôi phục vị trí custom sau khi tháo màn hình. Thêm test có tọa độ dương, âm và vùng làm việc bị taskbar thu hẹp.

### B3 — P2: Phụ đề diễn giải nội dung dịch thành HTML

**Cập nhật:** Đã sửa 26/10: PlainText trước text đầu tiên, 6 regression về markup/entities/lifecycle; final suite670 PASS, review sạch.

**Nguồn:** `ui/overlay.py:68–69`, `ui/overlay.py:242`.

Overlay kế thừa QLabel, giữ `Qt.AutoText` và truyền nguyên bản dịch vào `setText()`. Nội dung có thẻ như `<b>literal tag</b>` bị hiển thị thành chữ đậm và mất phần thẻ, thay vì giữ văn bản nguyên gốc. Điều này có thể làm sai phụ đề chứa ví dụ mã hoặc nội dung dạng markup. Renderer khối dùng QTextLayout nên không có cùng cách diễn giải này.

**Tái hiện:** Xác nhận overlay có `textFormat() == Qt.AutoText`; QLabel dùng cùng chuỗi có sizeHint rộng 187 ở AutoText và 306 ở PlainText, xác nhận thẻ được xử lý. Probe exit 0.

**Hướng sửa:** Đặt `Qt.PlainText` cho phụ đề. Test các chuỗi chứa thẻ HTML, dấu `<`, `>` và `&`.

### B4 — P1 khi phát hành: Cấu hình build phụ thuộc đường dẫn máy cũ

**Cập nhật:** Đã triển khai 26/10: gói OCR Anh/Nhật, classifier/dictionary/hash, dependency build khóa và spec không hard-code username; build thành công, mở/đóng executable exit0 trên host. Cổng clean-VM/offline/read-only vẫn chưa kiểm chứng. Xem docs/plans/2026-10-26-remaining-fixes-results.md.

**Nguồn:** `main.spec:4` và `requirements-dev.txt`.

`datas` trong spec trỏ trực tiếp tới `C:\Users\Windows\.paddleocr`. Đường dẫn này không tồn tại trên checkout đang đánh giá. Môi trường `.venv` cũng không có metadata PyInstaller và dependency phát triển chưa khai báo công cụ build. Vì vậy quy trình build hiện tại chưa tái lập được từ các dependency được khai báo.

**Bằng chứng:** Parse AST của spec và kiểm tra nguồn model bằng `Path.exists()` trả False; tra metadata PyInstaller trả PackageNotFoundError. Chưa chạy một build hoàn chỉnh, không khẳng định mọi lỗi đóng gói đã được tìm hết.

**Hướng sửa:** Tạo cấu hình build riêng, khai báo công cụ build, lấy model từ vị trí cấu hình được hoặc nguồn asset trong dự án, đóng gói logo và kiểm tra bản phát hành trên máy sạch. Xác minh OCR thực sự sử dụng model được đóng gói; hiện `SimplePaddleOCR.__init__` chưa truyền đường dẫn model tường minh.

## Vấn đề kỹ thuật và phần cần kiểm chứng thêm

| Ưu tiên | Vấn đề | Bằng chứng / tác động | Việc nên làm |
|---|---|---|---|
| P2 | Nhiều distribution cùng ghi vào `cv2` | Môi trường hiện có opencv-python 4.13.0.92, opencv-contrib-python 5.0.0.93 và opencv-python-headless 5.0.0.93; cả ba RECORD đều chứa `cv2/__init__.py`. Đây là rủi ro tái lập môi trường, chưa phải bằng chứng app đang crash. | Chốt tập dependency OCR/OpenCV tương thích, lock cả dependency bắc cầu, kiểm chứng cài mới và OCR thật. |
| P2 | Thiếu kiểm chứng môi trường desktop thật | Suite chặn native capture và dùng OCR/HTTP giả. Các ca DPI, fullscreen, click xuyên overlay và OBS cần kiểm chứng riêng. | Có checklist smoke tự chọn, video/ảnh và số đo từ máy thật; không trộn kết quả mock với benchmark. |
| P2 | Thiếu hướng dẫn khởi động/phát hành ở cấp repository | Chưa có README gốc hoặc CI trong checkout; launcher yêu cầu `.venv` đã được chuẩn bị. | Viết hướng dẫn Python/dependency/model, lần chạy đầu, khắc phục lỗi; thêm CI cho test offline và build. |
| P3 | Mã compatibility làm tăng chi phí bảo trì | `_process_frame()` là đường đồng bộ legacy; runtime `run()` dùng coordinator bất đồng bộ. Còn các nhánh/kiểu payload phục vụ caller cũ. | Ghi rõ API công khai và tiêu chí bỏ legacy; ưu tiên test hành vi qua runtime hiện tại. |

Các heuristic lượt thoại vẫn có giới hạn: hai lượt có chữ giống nhau hoặc nối tiếp mà không quan sát được khoảng trống có thể khó phân biệt. Đây là giới hạn đã được tài liệu dự án ghi nhận; cần corpus có nhãn để đo trước khi thay chính sách. Không coi lựa chọn pause/retry Google hiện tại là lỗi, vì đó là hành vi có chủ đích.

## Tính năng đề xuất

Đây là danh sách hướng phát triển, chưa phải thiết kế hoặc kế hoạch triển khai được phê duyệt.

| Thứ tự | Tính năng | Giá trị và cách nối vào nền tảng hiện có |
|---|---|---|
| 1 | Phím tắt toàn cục và khay hệ thống | Start/Stop, ẩn/hiện phụ đề, chọn vùng mà không phải rời game; cần cho phép đổi tổ hợp phím và xử lý xung đột. |
| 2 | Profile theo game/ứng dụng | Lưu tên profile cùng vùng OCR, ngôn ngữ, provider/model, kiểu overlay và style. Không sao chép API key vào profile. |
| 3 | Preview vùng OCR và trạng thái khởi tạo model | Xem ảnh crop, chữ nguồn, bounding box, confidence và thông báo tải/nạp model; giúp phân biệt chọn sai vùng, OCR sai và dịch sai. |
| 4 | Glossary và ngữ cảnh hội thoại | Giữ tên nhân vật/thuật ngữ nhất quán; prompt hiện tại dịch từng nội dung với chỉ dẫn chung. Với AI, giới hạn cửa sổ ngữ cảnh và ngân sách; với Google cần chính sách riêng. |
| 5 | Lịch sử song ngữ, copy và xuất TXT/SRT | Nâng từ nhật ký 300 dòng trong RAM thành bản ghi phiên có nguồn, bản dịch và timestamp. SRT cần thống nhất thời điểm bắt đầu/kết thúc lượt thoại. |
| 6 | Theo dõi cửa sổ đích | Vùng OCR đi theo cửa sổ khi di chuyển/resize; tạm dừng khi minimize hoặc mất cửa sổ. Capture hiện dùng tọa độ desktop cố định. |
| 7 | Bảng đo hiệu năng thực | Thời gian capture/OCR/request, độ trễ đến lúc hiển thị, cache hit, queue, token, CPU/RAM. Các thẻ hiện tại chủ yếu tóm tắt cấu hình. Dùng số đo để làm chế độ tiết kiệm CPU/tự điều chỉnh tần suất. |
| 8 | Chế độ dịch local và kiểm tra kết nối | Hoàn thiện UX cho endpoint local qua Custom API, hỗ trợ server không yêu cầu key và kiểm tra endpoint/model trước khi chơi. Cần đo tài nguyên vì OCR và model dịch dùng chung máy chạy game. |
| 9 | Mở rộng ngôn ngữ và tự nhận diện | Hiện nguồn gồm English/Japanese/Chinese/Korean, đích gồm Vietnamese/English. Mở rộng theo khả năng OCR/provider, xử lý rõ chi phí đổi model OCR. |

## Thứ tự phát triển khuyến nghị

1. **Ổn định bản nền:** B1 → B2 → B3; xử lý B4 trước phát hành executable. Thêm regression đúng các trường hợp đã tái hiện, chuẩn hóa dependency và smoke bản cài trên máy sạch.
2. **Tăng tiện ích khi chơi game:** phím tắt/khay hệ thống → profile → preview OCR/trạng thái model. Đây là nhóm ít đụng tới chính sách lượt thoại nhưng giảm thao tác hằng ngày.
3. **Nâng chất lượng có số đo:** thêm telemetry nội bộ và corpus game có nhãn; sau đó thử glossary/ngữ cảnh, theo dõi cửa sổ và điều chỉnh tần suất OCR. So sánh chất lượng/độ trễ trên cùng dữ liệu trước khi đổi mặc định.

Tiêu chí hoàn thành từng đợt nên gồm test offline, smoke desktop có mục tiêu và số liệu trước/sau phù hợp với thay đổi. Chưa ước lượng thời gian vì cần chốt tính năng cụ thể, phần cứng đích và yêu cầu phát hành.
