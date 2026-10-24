# Thiết kế khối overlay gọn theo nội dung

Ngày: 2026-10-24

Trạng thái: Người dùng đã duyệt kế hoạch và triển khai Native; đang kiểm chứng và review cuối đợt.

## Mục đích

Khối dịch phủ đủ chữ gốc và chứa bản dịch, không kéo nền đến hết vùng quét khi không cần. Áp dụng cho chế độ overlay theo khối với mọi công cụ dịch đang có.

## Hiện trạng và nguyên nhân

`ui/block_layout.py:layout_blocks` khởi tạo `view_rect` bằng toàn bộ khoảng trống từ vị trí chữ gốc đến mép vùng quét hoặc vật cản. `paint_blocks` tô nền toàn bộ `view_rect`. Vì vậy bản dịch ngắn vẫn có một dải nền dài.

Cửa sổ overlay trong suốt có thể tiếp tục rộng bằng vùng quét. Phần cần thu gọn là hình chữ nhật được tô nền và bố trí chữ của từng khối.

## Các hướng đã cân nhắc

1. **Lấy toàn bộ khoảng trống bên phải:** cách hiện tại, đơn giản nhưng tạo nền thừa; loại bỏ.
2. **Giữ nguyên chiều rộng chữ gốc:** nền gọn nhưng bản dịch dài dễ tăng nhiều dòng hoặc phải giảm cỡ chữ; không chọn.
3. **Mở rộng vừa đủ, rồi xuống dòng, cuối cùng giảm cỡ chữ:** người dùng đã chọn. Tận dụng khoảng trống khi cần, giữ chữ dễ đọc và tránh che giao diện vô ích.

## Hành vi đã chốt

- Bắt đầu từ khung chữ gốc đã đổi sang tọa độ overlay và giới hạn trong vùng quét.
- Nếu bản dịch đã vừa, giữ khung này. Nền không nhỏ hơn vùng chữ gốc cần che, kể cả khi bản dịch ngắn hơn.
- Nếu bản dịch không vừa, ưu tiên mở rộng sang phải vừa đủ theo kích thước chữ đo thực tế; không mặc định lấy hết khoảng trống.
- Khi chạm mép vùng quét hoặc khối chữ khác, xuống dòng và tăng chiều cao vừa đủ trong khoảng trống cho phép.
- Chỉ giảm cỡ chữ khi việc mở rộng và xuống dòng vẫn không đủ. Giữ giới hạn cỡ chữ và cách xử lý cắt chữ hiện có khi không thể hiển thị hết.
- Không vượt vùng quét và không chủ động mở rộng đè lên khối khác. Với các khung OCR vốn chồng nhau hoặc bị cắt ở biên, giữ cơ chế xử lý va chạm và cắt theo biên; không thể bảo đảm phủ trọn cả hai khung cùng lúc.
- Không có khối bên cạnh vẫn chỉ nới vừa đủ; sự vắng mặt của vật cản không phải lý do để kéo nền hết vùng quét.
- Mỗi khối có một nền hình chữ nhật chung. Không tô nền riêng ôm sát từng dòng hay từng ký tự. Các dòng ngắn có thể còn khoảng trống đến mép chung của khối.
- Giữ vị trí neo ban đầu ở góc trái trên của khung chữ gốc. Không thêm căn giữa hoặc hiệu ứng chuyển động mới.

## Ví dụ

Các tỷ lệ dưới đây chỉ minh họa, không phải ngưỡng cứng:

| Chữ gốc | Bản dịch cần | Kết quả |
| --- | --- | --- |
| Rộng 40% vùng quét | 30% | Giữ nền 40% để che chữ gốc |
| Rộng 40% vùng quét | 55%, còn đủ khoảng trống | Nới nền vừa đủ khoảng 55% |
| Không còn đủ chỗ bên phải | Nhiều chữ | Xuống dòng, tăng chiều cao vừa đủ; thiếu chỗ mới giảm cỡ chữ |

## Tham khảo MORT

Trong bản MORT clone đang đọc, `TransFormOver.cs` bắt đầu bằng khung OCR, tô nền theo `ViewRect`. Khi bật tự điều chỉnh kích thước chữ, nó tìm mức mở rộng nhỏ nhất đáp ứng phép đo chữ. Nền là hình chữ nhật của khối, không phải nền riêng từng dòng. Thiết kế này học cách mở rộng có điều kiện; không sao chép toàn bộ thuật toán MORT.

## Phạm vi và ràng buộc

- Xử lý kích thước bố trí và phần nền của overlay theo khối; giữ các thiết lập font, màu, độ mờ và giới hạn cỡ chữ hiện có.
- Dùng PyQt5 và công cụ đo chữ hiện có; không thêm thư viện.
- Không thay OCR, cách nhóm câu, lời nhắc dịch, cache, hàng chờ, retry hoặc endpoint dịch.
- Không thay đổi bố trí của chế độ phụ đề cố định.
- Lỗi giữ bản dịch cũ do biến thể OCR là vấn đề riêng, không được coi là đã sửa bởi thay đổi này.
- Không thêm log OCR vào giao diện.
- Không thêm cơ chế giữ chiều rộng theo cả lượt thoại trong đợt này; bố trí theo khung nguồn và bản dịch đang được hiển thị, không dựa vào kết quả còn đang chờ.

## Kiểm chứng và tiêu chí đạt

- Dùng các frame game và vùng OCR đã có trong dự án để đối chiếu trước/sau; trường hợp không có khối bên cạnh phải được kiểm tra trực tiếp.
- Bản dịch ngắn không tạo nền kéo hết khoảng trống và không làm lộ chữ gốc do thu nền quá nhỏ.
- Bản dịch dài hơn được mở rộng vừa đủ ở cỡ chữ ưu tiên khi có chỗ.
- Kiểm tra mép phải, giới hạn chiều cao, khối kế bên, nhiều dòng tiếng Việt có dấu và vùng quét nhỏ.
- Đo bằng đúng font và bộ bố trí Qt dùng để vẽ; phép đo và phần vẽ phải đồng nhất.
- Các khối không vượt vùng quét, các khung ban đầu không chồng nhau không bị mở rộng chồng nhau; vẫn hiển thị hoặc cắt an toàn khi quá chật.
- Bản mẫu trình duyệt chỉ xác nhận ý tưởng bố trí; kết quả đo chữ Qt và ảnh trên frame thật mới xác nhận triển khai.

## Phần để người triển khai quyết định

Chọn thuật toán tìm kích thước nhỏ nhất, sai số làm tròn và cách tái sử dụng kết quả đo. Giữ padding và hợp đồng dữ liệu hiện có nếu không có bằng chứng cần thay đổi. Các chi tiết này không được làm thay đổi thứ tự ưu tiên hoặc phạm vi nêu trên.
