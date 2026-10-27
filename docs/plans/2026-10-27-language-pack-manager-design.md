# Quản lý gói ngôn ngữ OCR — thiết kế

Ngày: 27/10/2026. Trạng thái: thiết kế và các lựa chọn kỹ thuật để review trước khi code.

## 1. Yêu cầu đã được người dùng xác nhận

- Ô chọn ngôn ngữ nguồn chỉ hiện những ngôn ngữ đã cài và dùng được, giống thao tác đổi English/Japanese hiện tại.
- Cuối ô chọn có dòng **“Quản lý gói ngôn ngữ…”**, mở nơi tải thêm và xóa gói. Dòng này là hành động, không phải giá trị ngôn ngữ.
- Đổi ngôn ngữ đã cài áp dụng trực tiếp; không thêm nút xác nhận hoặc “Tải và bắt đầu”. Giữ trạng thái chạy/dừng hiện tại.
- Cho xóa các gói tải thêm. **English/Japanese có sẵn được giữ lại**, theo trả lời của người dùng ngày 27/10/2026.
- UI dùng `ui-ux-pro-max`, ưu tiên component và style global đang có; không thiết kế lại toàn bộ ứng dụng.
- Yêu cầu hiện tại là xây dựng kế hoạch, chưa triển khai mã sản phẩm.

## 2. Phạm vi và các mặc định kỹ thuật đề xuất

Mục tiêu bản đầu: English/Japanese có sẵn; Chinese (giản thể) và Korean tải thêm. Cấu trúc cho thêm ngôn ngữ khác bằng dữ liệu và khai báo mapping, không tạo nhánh theo tên trong worker/UI.

Các mặc định sau là đề xuất của người lập kế hoạch, chưa phải yêu cầu người dùng tự nêu:

- Quản lý bằng một `QDialog` có một instance, mở bằng `open()`, không chờ bằng vòng event `exec_()` để quản lý tác vụ.
- Chỉ bắt đầu tải khi bấm **“Tải”** trong trình quản lý. Tải xong thêm lựa chọn vào select, **không tự đổi ngôn ngữ hoặc tự Start**.
- Một tác vụ cài/xóa tại một thời điểm; thao tác quét/dịch vẫn chạy. Đóng hộp thoại không hủy tải; mở lại thấy đúng tiến độ.
- Bản đầu chưa có HTTP byte-range resume: tác vụ dở được nhận diện và dọn ở lần mở sau; thử lại tải lại thành phần chưa hoàn tất, dùng lại thành phần đã được xác thực.
- Không thêm nhập gói offline, tự nhận diện đa ngôn ngữ, lựa chọn model nhanh/chính xác, remote catalog, tự cập nhật model hoặc provider mới.
- Không thay danh sách ngôn ngữ đích hiện tại: Vietnamese/English. Ngôn ngữ đích không phụ thuộc gói OCR.

## 3. Hiện trạng cần thay đổi

- `core/config.py:46–53` quản lý source/target riêng; `engines/google_translate.py:15` có bảng mã riêng; `core/worker.py:439` ánh xạ sang Paddle bằng một dict khác với mã Google.
- `core/ocr_models.py:31–78` chỉ chấp nhận bundle schema 1, ngôn ngữ `en/japan`; resolver chưa đọc model tải thêm.
- `engines/ocr.py:17–30` đã nhận đường dẫn model tường minh và giữ một engine OCR hoạt động. Không để Paddle tải model tự động thay bộ quản lý.
- `core/paths.py:24` đặt models dưới cache. Gói tải thêm cần đường dẫn dữ liệu bền vững riêng; không đổi AppData/credentials hoặc xóa cache cũ.
- `ui/pages/ocr_settings_page.py:34–37` dùng `currentTextChanged`; cần phân biệt item ngôn ngữ và item hành động.
- `SettingsCoordinator` đã có persist-before-apply và snapshot immutable; tiếp tục sử dụng, không đưa network/filesystem vào page/widget.
- `tools/prepare_ocr_models.py` chỉ copy model có sẵn; chưa có trình tải runtime. `tools/bundle_layout.py` đang dùng allowlist dựa trên manifest.

## 4. Các phương án đã cân nhắc

| Phương án | Đánh đổi | Quyết định |
|---|---|---|
| Hiện mọi ngôn ngữ trong select và tải ngay khi chọn | Dễ chọn nhầm; trộn chọn nguồn với cài đặt | Không dùng theo yêu cầu select chỉ hiện gói đã cài |
| Select gói đã cài + dòng mở trình quản lý | Giữ luồng đổi ngôn ngữ quen thuộc; quản lý tải/xóa riêng | Người dùng đã chọn |
| Đóng gói sẵn mọi ngôn ngữ | Bản cài lớn, cập nhật model gắn với cập nhật app | Giữ English/Japanese, tải thêm theo nhu cầu |

Về nguồn tải, đề xuất dùng các archive HTTPS chính thức được PaddleOCR **2.10.0 đã pin trong dự án** khai báo; đóng gói từ điển nhỏ và catalog hash cùng app. Không cần dựng dịch vụ hosting mới hoặc dùng key dịch để tải model. Đây là lựa chọn kỹ thuật để review.

## 5. Ràng buộc chung

- Windows x64; Python 3.10; PyQt5 5.15.11; PaddleOCR 2.10.0; PaddlePaddle 2.6.2; httpx 0.28.1. Không thêm dependency runtime.
- Giữ English/Japanese trong bundle, read-only và không thể xóa qua trình quản lý.
- Giữ config `source_lang`/`target_lang` dạng tên English/Japanese/Chinese/Korean/Vietnamese để tương thích; ID nội bộ độc lập với tên hiển thị.
- Chỉ gói xác thực đủ file, hash và tương thích mới xuất hiện trong select; file đang tải không phải gói đã cài.
- Không download, hash model lớn, giải nén, xóa thư mục hoặc khởi tạo Paddle trên GUI thread.
- Không có “Tải và bắt đầu”; tải xong không đổi source, không khởi động worker.
- Không ghi vào bundle, `.env`, config trong repo hoặc credential; mọi dữ liệu gói tải thêm ở user data.
- Unit/integration test dùng model giả, HTTP giả, config tạm và guard trong `tests/conftest.py`; native OCR/download thật là smoke riêng.
- Mọi spec/plan/progress của tính năng ở `docs/plans/` với tên có ngày; giữ nguyên thay đổi chưa commit của người dùng.

## 6. Danh mục ngôn ngữ và danh mục artifact

`core/languages.py` là nguồn duy nhất cho ID, tên config, mã OCR, mã Google, vai trò source/target và cờ có sẵn trong app:

| ID | Tên config/nhãn hiện tại | Paddle | Google | Nguồn | Đích | Có sẵn |
|---|---|---|---|---|---|---|
| `en` | English | `en` | `en` | Có | Có | Có |
| `ja` | Japanese | `japan` | `ja` | Có | Không | Có |
| `zh-Hans` | Chinese | `ch` | `zh-CN` | Có | Không | Không |
| `ko` | Korean | `korean` | `ko` | Có | Không | Không |
| `vi` | Vietnamese | Không | `vi` | Không | Có | Không |

Mapping từ ID sang các component cũng thuộc registry này: `en=(det-en,rec-en,cls)`, `ja=(det-ml,rec-ja,cls)`, `zh-Hans=(det-ch,rec-ch,cls)`, `ko=(det-ml,rec-ko,cls)`. Resource dictionary lần lượt là `dict-en`, `dict-ja`, `dict-ch`, `dict-ko`; resource `notice` dùng chung. Không suy ra detector bằng phép `en if ... else ml`.

`assets/ocr/language-packs.json` chỉ quản lý artifact: schema 1, engine/version, revision của component, HTTPS URL, kích thước archive, SHA-256 archive, danh sách file sau giải nén với kích thước/hash, dictionary/notice resource đã pin. Không lặp lại bảng mã ngôn ngữ. ID/revision hợp lệ theo `[a-zA-Z0-9_-]+`; language ID không được dùng trực tiếp làm đường dẫn không kiểm tra.

Tool authoring lấy URL và dictionary từ package đã pin qua metadata/AST, không import Paddle. Đọc archive thật qua HTTPS ở bước chuẩn bị phát hành để tính size/hash thật; không dùng hash giả hoặc hash tự lấy từ file đang tải ở runtime. Commit catalog đã pin sau review nguồn và native smoke. URL gốc đối chiếu được ở `.venv/Lib/site-packages/paddleocr/paddleocr.py:94–165`:

- Chinese detector/recognizer: PP-OCRv4/chinese/ch_PP-OCRv4_{det,rec}_infer.tar.
- Korean recognizer: PP-OCRv4/multilingual/korean_PP-OCRv4_rec_infer.tar.
- Detector dùng chung Japanese/Korean: PP-OCRv3/multilingual/Multilingual_PP-OCRv3_det_infer.tar.
- Classifier chung: dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar.
- Host: `paddleocr.bj.bcebos.com`. Giữ notice và provenance, kiểm tra điều kiện phân phối khi chuẩn bị release.

## 7. Kho gói và tính toàn vẹn

Thêm `get_language_pack_root() -> Path` trả `get_app_paths().config_dir / 'models'`; không đổi cấu trúc `AppPaths` hay di chuyển/xóa cache cũ. Resource bundled dùng `_MEIPASS/assets/ocr` hoặc project assets như hiện tại.

Kho tải thêm có `components/<id>/<revision>/`, `packs/<id>/installed.json`, `.staging/<operation-id>/`, `.trash/` và lock/lease nội bộ. `installed.json` được ghi tạm rồi `os.replace` sau cùng; component có trước marker không làm gói thành installed. Đọc kho hỏng phải trả trạng thái có thể sửa, không tạo gói giả.

- Dùng lại component bundled chỉ khi hash/version khớp catalog; không tải lại `det-ml/cls` chỉ vì cài Korean.
- Xóa một gói chỉ thu hồi component user-owned không còn gói khác tham chiếu; không xóa bundled resource.
- Tác vụ ghi được khóa giữa các instance. OCR giữ lease của gói tải thêm; gỡ từ instance khác cũng phải trả `in_use`, không xóa file engine đang dùng.
- Cấp lease và publish/remove marker dùng cùng mutation lock; không giữ lock này trong suốt request mạng. Gỡ và OCR không thể vượt qua nhau giữa kiểm tra và sử dụng.
- Rename marker sang trash trước cleanup; nếu Windows giữ file, gói đã gỡ không còn xuất hiện trong select nhưng thông báo cleanup chờ và dung lượng thực giải phóng; lần mở sau thử cleanup lại. Không báo đã thu hồi số byte chưa xóa được.
- Giải nén đúng file trong allowlist bằng stream; từ chối absolute path, `..`, link, device, duplicate member, đường dẫn vượt root và byte vượt size đã pin. Không gọi `extractall()` không kiểm tra.
- Hash theo stream, không nạp trọng số vào RAM chỉ để kiểm tra; cache kết quả theo identity/stat và invalidation khi install/remove. Không hash toàn bộ model mỗi lần chụp màn hình hay render tiến độ.

## 8. Tải, hủy và vòng đời ứng dụng

Trạng thái gói: `not_installed`, `downloading`, `verifying`, `installing`, `installed`, `removing`, `error`. `origin=bundled|downloaded|none` và `in_use` là thuộc tính riêng.

- `LanguagePackManager` sống cùng app, không thuộc lifetime của dialog. Snapshot immutable; progress/result có `operation_id` để bỏ sự kiện trễ.
- Một HTTP client thuộc transfer worker; connect timeout 5s, read timeout 15s, chunk 64 KiB, `max_retries=0` ở transport và manual retry trong UI. Client luôn close trong `finally`.
- Chỉ HTTPS tới host trong catalog đóng gói; không follow redirect tự động. Không lấy URL từ ô nhập, config model AI hoặc kết quả mạng khác.
- Kiểm tra dung lượng theo các archive chưa có + file giải nén + 16 MiB dự phòng trước tác vụ; vẫn bắt disk-full nếu dung lượng đổi giữa chừng.
- Tiến độ hiển thị byte tải/byte cần tải; kiểm tra/cài là giai đoạn riêng, không giả báo 100% installed trước commit marker.
- Hủy được kiểm tra giữa các chunk/giai đoạn. Thành phần chưa xác thực bị dọn; component đã commit hợp lệ được dùng lại lần sau. Hủy không ảnh hưởng source và phiên dịch.
- Đóng dialog tiếp tục tác vụ. Thoát app gửi cancel, chờ tín hiệu worker kết thúc bất đồng bộ rồi mới quit; không `terminate()` QThread hoặc chặn GUI bằng `wait()` dài. Crash được phục hồi bằng staging/marker ở lần mở sau.

## 9. Select, config cũ và runtime

Select giữ tên ngôn ngữ hiện tại, `itemData` là ID/action token; có separator và item hành động `__manage_language_packs__`. Chọn hành động phải phục hồi index source trước đó bằng `QSignalBlocker` rồi phát `manage_packs_requested`, không phát `source_changed`.

- Cài xong chỉ cập nhật choices; không chọn item mới và không gọi `worker.configure/start_worker`.
- Chọn gói installed đi qua `SettingsCoordinator.set_source`, kiểm tra readiness rồi persist-before-apply và revision như hiện tại. Không thêm bước Start. Dừng vẫn dừng.
- Gói đang được chọn không có nút xóa khả dụng, kể cả worker đang dừng: hướng dẫn **“Chọn ngôn ngữ khác trước khi xóa.”** Lease vẫn là chốt kiểm tra runtime độc lập khi có request cũ còn chạy.
- Config cũ lưu Chinese/Korean nhưng chưa cài: giữ giá trị trong file, select có index -1 với placeholder **“Chọn ngôn ngữ đã cài”**, thông báo bộ còn thiếu và đường mở quản lý; không âm thầm đổi sang English. Chặn Start hiện có ở preflight với lỗi rõ. Sau khi cài đúng gói, lựa chọn đã lưu xuất hiện lại, vẫn không tự Start.
- Nếu file bị xóa ngoài app hoặc native load thất bại: invalidation readiness, báo gói lỗi/cài lại, không nhận diện bằng model của ngôn ngữ khác hoặc gọi auto-download của Paddle. Không ghi đè lựa chọn mới bằng kết quả cũ.
- Native engine chỉ nạp trên OCR thread. Giữ một engine hoạt động; identity cache có language ID + pack revision. Dọn engine/lease trên thread sở hữu khi switch/stop/shutdown.
- Giữ cơ chế revision/turn/render-sequence và Google recovery; kết quả OCR/dịch cũ không được hiện sau đổi ngôn ngữ.
- Source checkout không có bundle giữ đường OCR legacy để tương thích script/test, nhưng app UI chỉ coi model có manifest/catalog hợp lệ là installed. Không quảng cáo cache Paddle không quản lý như gói sẵn sàng.

## 10. UI và tái sử dụng component

Giữ PyQt5 và dark theme hiện tại. Dùng lại `ModernCard` (`ui/widgets/cards.py`), `CYBER_PALETTE`, `SECONDARY_BUTTON_STYLE`, `get_app_stylesheet()` và `get_lucide_icon()`. Trước khi tạo component mới phải kiểm tra `ui/widgets/`; chỉ thêm một row trạng thái gói có thể tái dùng, không tạo design system mới hoặc thêm thư viện web.

Dialog có tiêu đề **“Quản lý gói ngôn ngữ”**, nhóm **“Đã cài”** và **“Có thể tải”**. Mỗi row có tên, mô tả trạng thái, dung lượng, progress nếu có và một action chính: `Tải`, `Hủy tải`, `Thử lại`, `Xóa gói`. Gói bundled hiện **“Có sẵn trong ứng dụng”**, không có nút xóa. Gói active hiện **“Đang chọn”** và lý do không thể xóa.

Xác nhận xóa nêu tên ngôn ngữ và dung lượng user-owned thực có thể thu hồi; nút mặc định là **“Hủy”**. Không dùng màu đỏ hoặc icon làm tín hiệu duy nhất.

Hộp thoại đề xuất 560×520 logical px, minimum 440×360 nhưng phải fit `availableGeometry`; danh sách cuộn và footer luôn truy cập được. Tab order theo thứ tự nhìn thấy; Escape đóng dialog, không hủy tải; mở lại focus hợp lý, đóng trả focus về select. Nhãn/action/lỗi không bị cắt mất ý nghĩa ở Windows 125/150/200% DPI.

Đã chạy và đối chiếu hai truy vấn `ui-ux-pro-max` ngày 27/10/2026: `modal keyboard focus desktop --domain ux` (áp dụng Focus States/All) và `download progress cancellation errors --domain ux` (Progress Indicators, Error Recovery, Essential Text Truncation/All). Dataset không có stack PyQt; chuyển các nguyên tắc platform-neutral sang native Qt, không áp dụng ARIA/CSS/mobile safe-area vào desktop.

## 11. Tiêu chí nghiệm thu

1. Fresh frozen app không có cache/mạng vẫn hiện và OCR được English/Japanese; Chinese/Korean chỉ xuất hiện trong trình quản lý trước khi cài.
2. Download thật + xác thực + cài Chinese/Korean thành công; sau đó restart offline vẫn chọn và OCR được cả hai, không ghi bundle.
3. Mở manager, tải/xóa/retry và đóng/mở dialog không làm đổi source, Start worker hoặc làm GUI đứng.
4. Chọn installed source khi đang chạy tiếp tục đúng ngôn ngữ; khi đang dừng không tự Start; stale subtitle bị loại.
5. Cancel/disk-full/hash mismatch/crash không tạo installed giả; bundled và gói khác không bị ảnh hưởng.
6. Gỡ gói tải thêm rồi mở lại app vẫn chưa cài; model shared/in-use không bị xóa.
7. Save config lỗi không đổi runtime; missing saved source có hướng khôi phục rõ.
8. Unit/integration suite và UI boundary tests pass; native OCR/download/build có bằng chứng riêng, không suy từ mock.

## 12. Trạng thái trước triển khai

Thiết kế này tổng hợp yêu cầu đã chốt và ghi riêng mặc định kỹ thuật để người dùng review cùng kế hoạch triển khai. Chưa tải model, chưa đổi dependency, chưa sửa source, chưa tuyên bố nguồn tải/hash hay native Chinese/Korean đã được kiểm chứng trên bản phát hành.
