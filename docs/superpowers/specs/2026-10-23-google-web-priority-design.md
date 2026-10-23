# Google Web: batchexecute → clients5 → GTX

Ngày: 2026-10-23. Trạng thái: người dùng đã chọn hướng; chờ duyệt thiết kế ngắn này.

## Mục tiêu và bằng chứng

Ứng dụng dịch màn hình dùng Google không cần key, ưu tiên đường đang dịch được tại mạng hiện tại. Giữ cache, hai kiểu overlay, OCR bất đồng bộ và cơ chế tạm dừng/Thử lại đã triển khai.

Test đọc mạng riêng với câu literal `Hello world`, mỗi đường một request:

| Đường | HTTP | Kết quả | Thời gian |
| --- | --- | --- | --- |
| batchexecute | 200 | Xin chào thế giới | 1.297s |
| GTX | 429 | Không có bản dịch | 0.453s |
| clients5 | 200 | Xin chào thế giới | 0.329s |

Một lần thành công không bảo đảm khả dụng lâu dài hoặc tốc độ khi chơi game.

## Các hướng và lựa chọn

1. **batchexecute chính, clients5 rồi GTX dự phòng — người dùng đã chọn và bổ sung thứ tự GTX cuối cùng.** Có đường thay thế khi gặp lỗi tạm thời, nhưng phải tính từng request vào ngân sách Google chung.
2. **Chỉ batchexecute.** Đơn giản hơn nhưng không có đường dự phòng khi đường chính lỗi.

Thứ tự đã chốt: **batchexecute → clients5 → GTX**. GTX vẫn được giữ cuối chuỗi dù lần test vừa rồi trả 429. Không tự chuyển sang AI hoặc Google Cloud.

## Thiết kế đề xuất

Thay đổi tập trung trong `engines/google_translate.py`; giữ API `GoogleTranslateClient.translate()` và `TranslationResult`. Không thêm provider hoặc lựa chọn endpoint trong UI.

- Client mới bắt đầu bằng batchexecute. Gửi POST form `f.req` đến `https://translate.google.com/_/TranslateWebserverUi/data/batchexecute`, RPC `MkEWBc`, tham số `rpcids=MkEWBc&rt=c`; nguồn/đích dùng map ngôn ngữ Google hiện có. Origin/Referer giống MORT.
- clients5 dùng GET `https://clients5.google.com/translate_a/t`, `client=dict-chrome-ex`, `sl`, `tl`, `q`.
- GTX dùng GET `https://translate.googleapis.com/translate_a/single`, `client=gtx`, `sl`, `tl`, `dt=t`, `q`, với parser hiện có.
- **Mỗi lần gọi translate chỉ gửi tối đa một HTTP request.** Không gọi nhiều đường trong một lần translate, không retry ngầm và không chạy song song.
- Với lỗi có thể retry (timeout/network/408/429/5xx), adapter chuẩn bị đường kế tiếp theo thứ tự đã chốt cho lần được core cho phép gửi tiếp. Nếu đã tới GTX thì giữ GTX cho lượt retry còn lại, không quay vòng qua các đường khác. Core vẫn đếm lần đầu + tối đa 3 retry, dùng chung cho cả ba đường và mọi khối/candidate; bốn lỗi liên tiếp từ client mới là batchexecute, clients5, GTX, GTX rồi pause.
- Tôn trọng Retry-After trên cả ba đường. 429 không có header hợp lệ vẫn chờ ít nhất 30 giây theo chính sách hiện tại. Không chuyển đường ngay để bỏ qua hạn chờ.
- Thành công thì tiếp tục dùng đường vừa thành công cho vòng đời client đó; không thăm dò lại batchexecute bằng timer. Client mới sau Stop/Start hoặc thay owner thread lại ưu tiên batchexecute. Đây là lựa chọn kỹ thuật đề xuất để tránh lặp lỗi đường chính ở từng khối.
- Input sai/rỗng không chuyển đường và không gửi mạng. Lỗi không retry được (403/redirect/HTML/payload sai) vẫn tạm dừng ngay như hiện tại; không tự thử đường khác sau loại lỗi này, không xử lý đăng nhập/CAPTCHA. Nút Thử lại giữ hành vi hiện tại.
- Giới hạn 2000 ký tự; timeout 8 giây mỗi request; không follow redirect. Client tạo/dùng/đóng cùng thread. OCR vẫn chạy trong lúc chờ.

## Parser, cache và log

- Parser batchexecute đọc framing/XSSI, tìm đúng RPC `MkEWBc`, giải mã JSON lồng và nối đầy đủ các segment dịch theo thứ tự. Bỏ metadata/frame RPC khác; không lấy đoạn đầu rồi bỏ phần còn lại.
- Parser clients5 nhận danh sách chuỗi theo định dạng đã test. Sai dạng hoặc kết quả rỗng trả lỗi có cấu trúc, không cache.
- Parser GTX giữ cách nối toàn bộ segment đã được kiểm thử.
- Giữ khoảng trắng/Unicode của segment; không tạo khoảng trắng tùy ý. Fixture phải có nhiều đoạn, xuống dòng, Việt/CJK, frame thiếu/sai và HTML.
- Tăng GOOGLE_ADAPTER_VERSION vì backend/parser thay đổi. Cache vẫn nằm ở TranslationService, dùng chung cho ba đường; cache hit không thay route hoặc reset ngân sách lỗi.
- Che query của clients5 và GTX trong log HTTPX; không log POST body, source, phản hồi thô hoặc exception thô. Chẩn đoán/smoke có thể ghi tên đường, mã lỗi và thời gian an toàn.

## Phạm vi và kiểm chứng

Không đổi UI, cấu hình AI, key/model, OCR, overlay/capture, MORT/, video hoặc config.json của người dùng. Giữ nguyên GoogleRecoveryGate và các quy tắc pause qua đổi vùng/ngôn ngữ/mode, Stop/Start và callback cũ.

Kiểm thử giả lập xác nhận request mặc định là batchexecute; lỗi retry được chuyển đúng batchexecute → clients5 → GTX ở những lần gọi kế tiếp; đường thành công được giữ; bốn lỗi chung gây pause và không quay vòng; không request nào trước Retry-After; lỗi input/nonretry không fallback; cache và vòng đời thread vẫn đúng. Chạy full regression suite, không gọi mạng thật trong pytest.

Smoke thật chạy riêng một câu mẫu qua adapter mới. Không tự lặp probe sau 429. Kết quả thật được ghi riêng với thời điểm/thời gian; không suy từ mock rằng mạng thật thành công.

Đây là thay đổi adapter và test, không thay kiến trúc worker. Sau khi duyệt sẽ viết kế hoạch triển khai ngắn theo các mục trên.
