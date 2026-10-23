# Google Translate — kiểm chứng 2026-10-23

## Kết quả triển khai trước review cuối

- Plan: docs/superpowers/plans/2026-10-23-google-translate.md.
- Native execution, baseline cũ 286 test PASS khi bỏ test Google nháp chưa triển khai.
- Sau T1–T8: **342 passed in 12.40s, exit 0**, toàn bộ test, không skip/xfail Google.
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
| Revision-bound subtitle ngăn callback cũ khi đổi công cụ; API legacy giữ lại | PASS regression |
| Window close chờ thread/request cleanup | Bộ regression lifecycle PASS; bổ sung review cuối nếu có phát hiện |
| Chơi game, OBS, RAM/CPU/độ trễ với video Genshin và dịch vụ thật | Chưa chạy, chưa có số đo |

## Smoke mạng thật

Lệnh riêng, chỉ gửi câu mẫu không nhạy cảm:

```powershell
.\.venv\Scripts\python.exe tools/smoke_google_translate.py --source English --target Vietnamese --text "Hello world"
```

Kết quả thực tế: **exit 1**, error_code=`rate_limit` (HTTP 429), translated_text rỗng, duration 0.687 giây.

Google đã giới hạn yêu cầu tại môi trường/mạng hiện tại. **Chưa xác nhận một lần dịch thành công qua mạng thật.** Không tự chuyển endpoint, không chuyển AI và không lặp smoke liên tục sau 429. Các bài mock PASS kiểm chứng cách xử lý, không thay thế smoke thành công của Google.

## Cách dùng

Trang **Công cụ dịch** có Google Translate cùng các công cụ AI hiện tại. Chọn Google không cần nhập Model/API key. Config có lựa chọn hợp lệ giữ nguyên công cụ đó; config mới dùng Google.

Google dùng tối đa ba retry sau lỗi đầu tiên, ngân sách chung cho dịch vụ. Hết ngân sách thì OCR vẫn quét nhưng ngừng gửi dịch Google. Trang Tổng quan hiển thị trạng thái và nút **Thử lại**; nút không bỏ qua hạn chờ rate-limit. Không tự chuyển sang AI có phí.

## Quyết định triển khai

- Dùng checkout feature hiện có, giữ config.json/MORT/video và các file người dùng.
- Dùng PowerShell cho ledger/test harness của skill Bash trên Windows; các cổng RED/GREEN vẫn được ghi nhận.
- Để không hồi sinh callback AI cũ khi chuyển Google/AI, GUI dùng SubtitleFrame có revision cho cả hai; signal str và đường dịch AI đồng bộ vẫn được giữ cho compatibility.
- Chưa có thay đổi capture exclusion, layout overlay hoặc kết luận tăng chất lượng/giảm RAM so với MORT.
