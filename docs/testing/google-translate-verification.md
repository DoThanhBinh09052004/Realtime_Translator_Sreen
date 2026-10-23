# Google Translate — kiểm chứng 2026-10-23

## Cập nhật: batchexecute → clients5 → GTX

- Thiết kế/kế hoạch mới: docs/superpowers/specs/2026-10-23-google-web-priority-design.md và docs/superpowers/plans/2026-10-23-google-web-priority.md; người dùng duyệt Native.
- Sau thay adapter: **381 passed in 13.67s, exit 0**, không skip/xfail Google. `git diff --check` exit 0.
- Adapter mới bắt đầu bằng batchexecute, lỗi retry được mới chuẩn bị clients5 rồi GTX; mỗi lượt translate tối đa một HTTP request. Đường thành công được giữ đến khi client đóng. Không quay vòng khi đã đến GTX.
- HTTP429 vẫn chờ Retry-After hoặc mặc định30 giây, dù request kế tiếp dùng đường khác. Bốn lỗi liên tiếp trên batch/clients5/GTX/GTX vẫn làm gate pause. Lỗi input/nonretry không chuyển đường.
- Integration fake HTTP + queue thật xác nhận lỗi429 của scene cũ vẫn tính ngân sách/deadline; scene hiện tại chỉ gửi sau12 giây; không có request thứ5 dù clock10000 hoặc scene mới. Cache hit không đổi route hoặc chữa budget.
- Parser giữ toàn bộ segment/Unicode, gồm U+2028/U+2029; không coi ký tự phân dòng Unicode là framing HTTP. Query clients5/GTX và body batch không lọt log HTTPX INFO.
- Vẫn dùng checkout feature hiện có và PowerShell harness trên Windows; đánh đổi là thay đổi cùng nhánh cũ và không sinh review package bằng Bash. Không sửa config.json/.env/MORT/video hoặc thêm dependency.

Smoke **qua adapter mới** (cùng CLI bên dưới): **exit0**, translated_text=`Xin chào thế giới`, error_code=null, duration **1.906 giây**, English→Vietnamese, câu mẫu `Hello world`. Client mới dùng batchexecute và trả thành công ngay lượt đầu. Đây là kết quả mạng thật tại lần thử ngày2026-10-23, không bảo đảm khả dụng lâu dài hoặc hiệu năng game.

Lượt so sánh đọc mạng trước khi triển khai, mỗi đường một request cùng câu mẫu: batch HTTP200/1.297s, clients5 HTTP200/0.329s, GTX HTTP429/0.453s. Các số này là quan sát đơn lẻ, không phải benchmark.

Review độc lập toàn bộ đợt ưu tiên ba đường: đang thực hiện; kết quả sẽ được bổ sung trước khi chốt.

## Kết quả triển khai

- Plan: docs/superpowers/plans/2026-10-23-google-translate.md.
- Native execution, baseline cũ 286 test PASS khi bỏ test Google nháp chưa triển khai.
- Sau T1–T8 và sửa lỗi review cuối: **347 passed in 12.49s, exit 0**, toàn bộ test, không skip/xfail Google.
- Pytest dùng Qt offscreen, fake OCR/capture và HTTP MockTransport; không dùng key hoặc nội dung màn hình thật.
- httpx 0.28.1 được khai báo trực tiếp, các dependency khác giữ nguyên; requirements giữ encoding UTF-16 vốn có.

## Ma trận kiểm chứng

| Hành vi | Kết quả |
| --- | --- |
| Default Google khi chưa có công cụ, giữ AI đã lưu | PASS unit/config; đọc không ghi migration |
| Google không key/model, không tạo OpenAI client | PASS facade/UI/fake HTTP |
| Mã ngôn ngữ English/Japanese/Chinese/Korean/Vietnamese, nhiều đoạn/Unicode | PASS adapter |
| Timeout/network/408/429/5xx/403/redirect/HTML/payload lỗi | PASS adapter; thông báo có cấu trúc |
| Retry-After số/ngày HTTP/invalid, 429 mặc định 30 giây | PASS adapter/recovery |
| FIFO cache 300, metadata cache hit không reset ngân sách, đổi công cụ không trộn cache | PASS facade/recovery |
| 32 job và thay scene không vượt ngân sách 4 lần thất bại | PASS queue |
| Capture tiếp tục khi request Google bị giữ, subtitle và blocks | PASS worker/integration |
| Hết retry tạm dừng, không tự thăm dò; bấm Thử lại dùng scene mới | PASS tích hợp cả hai mode |
| Pause giữ qua đổi vùng/source/mode, selector suspend/resume và Google→AI→Google | PASS lifecycle |
| Stop/Start chủ động mở phiên mới; state không ghi config | PASS lifecycle/recovery |
| UI key/model/capabilities, save rollback, status cũ, Retry nhiều click | PASS UI |
| Lưu cấu hình thất bại vẫn giữ trạng thái pause/nút Thử lại | PASS regression provider và style rollback |
| HTTPX INFO không ghi query chứa câu nguồn Google | PASS regression; log host khác giữ nguyên |
| Revision-bound subtitle ngăn callback cũ khi đổi công cụ; API legacy giữ lại | PASS regression |
| Window close chờ thread/request cleanup | Bộ regression lifecycle PASS; bổ sung review cuối nếu có phát hiện |
| Dừng rồi đổi provider/mode khi HTTP còn chờ không tự chạy lại | PASS hai regression Event-held |
| Bấm Start trong lúc restart nội bộ không reset phiên/pause Google | PASS regression Event-held |
| Chơi game, OBS, RAM/CPU/độ trễ với video Genshin và dịch vụ thật | Chưa chạy, chưa có số đo |

Lệnh toàn bộ test: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp <fresh-path>`. Đặt TEMP/TMP và basetemp vào thư mục mới trong writable root ngoài repository, PYTHONUTF8=1; không dùng system Python.

## Review cuối

Review độc lập toàn bộ range `3a711c8..b922e5d` đã hoàn tất bằng gpt-6.1-sol high sau khi lượt Astra bị ngắt do hạn mức. Reviewer xác nhận lỗi restart sau Dừng, cùng rủi ro ghi đè ý định giữ phiên khi bấm Start giữa restart nội bộ. Các regression đã chạy RED rồi GREEN; suite cuối 347/347. Hai lỗi rollback và log HTTPX cũng có bằng chứng RED/GREEN. Không có finding Critical hoặc minor được hoãn.

Phần reviewer chưa thể kết luận: dịch thành công qua Google thật và hiệu năng/game/RAM. Giữ hai phần này là chưa kiểm chứng, vì smoke chỉ nhận 429 và test dùng fake capture/HTTP; chi phí là chưa thể bảo đảm dịch vụ thật hoặc công bố số đo hiệu năng.

## Smoke ban đầu: GTX trước đợt ưu tiên ba đường

Lệnh riêng, chỉ gửi câu mẫu không nhạy cảm:

```powershell
.\.venv\Scripts\python.exe tools/smoke_google_translate.py --source English --target Vietnamese --text "Hello world"
```

Kết quả thực tế: **exit 1**, error_code=`rate_limit` (HTTP 429), translated_text rỗng, duration 0.687 giây.

Ở lượt ban đầu, GTX đã giới hạn yêu cầu và chưa có lần dịch thành công qua mạng thật. Đợt cập nhật phía trên đã có smoke batchexecute thành công sau khi người dùng duyệt đổi thứ tự đường gọi. Không lặp smoke liên tục sau429; kết quả mock vẫn được phân biệt với kết quả mạng thật.

## Cách dùng

Trang **Công cụ dịch** có Google Translate cùng các công cụ AI hiện tại. Chọn Google không cần nhập Model/API key. Config có lựa chọn hợp lệ giữ nguyên công cụ đó; config mới dùng Google.

Google dùng tối đa ba retry sau lỗi đầu tiên, ngân sách chung cho dịch vụ. Hết ngân sách thì OCR vẫn quét nhưng ngừng gửi dịch Google. Trang Tổng quan hiển thị trạng thái và nút **Thử lại**; nút không bỏ qua hạn chờ rate-limit. Không tự chuyển sang AI có phí.

## Quyết định triển khai

- Dùng checkout feature hiện có, giữ config.json/MORT/video và các file người dùng.
- Dùng checkout hiện có nên thay đổi nằm cùng nhánh feature cũ, không tách nhánh riêng.
- Dùng PowerShell cho ledger/test harness của skill Bash trên Windows; các cổng RED/GREEN vẫn được ghi nhận. Đánh đổi: không có review package sinh bằng Bash, reviewer nhận trực tiếp range/spec/plan/ledger.
- Để không hồi sinh callback AI cũ khi chuyển Google/AI, GUI dùng SubtitleFrame có revision cho cả hai; signal str và đường dịch AI đồng bộ vẫn được giữ cho compatibility. Đánh đổi: thêm một payload signal cho mỗi bản dịch AI.
- Reviewer Astra hết hạn mức trước khi hoàn tất; thay bằng fresh-context gpt-6.1-sol high. Đánh đổi: dùng mô hình review khác với lựa chọn ban đầu.
- Chưa có thay đổi capture exclusion, layout overlay hoặc kết luận tăng chất lượng/giảm RAM so với MORT.
