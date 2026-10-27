# Phạm vi ba sửa lỗi còn lại — 25/10/2026

## Yêu cầu và quyết định

Nguồn: `docs/plans/2026-10-25-project-audit.md`, các finding B2, B3, B4. B1 đã sửa và có baseline toàn suite 617 PASS; không triển khai lại B1. Người dùng yêu cầu lập kế hoạch bằng writing-plans và đã chọn **đóng gói sẵn tiếng Anh và tiếng Nhật**.

Các quyết định kỹ thuật dưới đây là đề xuất để người dùng duyệt, chưa phải phần đã triển khai. Tách thành ba kế hoạch vì từng lỗi có thể sửa, test và phát hành độc lập:

1. `2026-10-25-subtitle-plain-text-plan.md`: B3, sửa nhỏ nhất.
2. `2026-10-25-subtitle-monitor-geometry-plan.md`: B2, tọa độ màn hình.
3. `2026-10-25-windows-ocr-bundle-plan.md`: B4, đóng gói Windows với OCR offline English/Japanese.

## Ràng buộc chung

- Windows x64; Python 3.10; PyQt5 5.15.11; PaddleOCR 2.10.0; PaddlePaddle 2.6.2.
- Giữ màu, nền alpha, font, animation 280ms, timer legacy 6000ms, revision/turn/render-sequence và hành vi Google pause/retry hiện tại.
- Giữ các thay đổi chưa commit, đặc biệt `config.json`, `ui/overlay.py`, `tests/test_subtitle_background.py`, `core/worker.py`, `ui/controller.py`, `tests/test_worker_status_ui.py`; không stage cả thư mục.
- Mọi kế hoạch/spec/progress ở `docs/plans/` với tên có ngày. Thư mục này hiện bị ignore; khi cần commit chỉ dùng `git add -f` với từng tài liệu chỉ định, không thay toàn bộ `.gitignore` để track tài liệu.
- Tra CodeGraph trước khi sửa; dùng root từ `git rev-parse --show-toplevel`, không tạo/rebuild index. Không tạo worktree khi chỉ lập kế hoạch.
- Unit/integration test dùng `.venv/Scripts/python.exe`, guard hiện có trong `tests/conftest.py`, không gọi API dịch, dùng key thật, chụp desktop hay tải model.
- Trước khi test, đặt TEMP, TMP và basetemp vào thư mục mới trong writable root ngoài repository theo `docs/testing/isolation.md`. Xem harness bên dưới.

## B3: hiển thị văn bản nguyên gốc

Đặt `Qt.PlainText` một lần trong `Overlay.__init__`, trước lần `setText` đầu tiên. Không escape nội dung: `<b>`, `&amp;`, `<img ...>`, xuống dòng và Unicode phải giữ nguyên chuỗi; không double-escape. Drag mode, `set_mode`, cập nhật style và đường `SubtitleFrame` không được bật lại AutoText. Block renderer dùng QTextLayout, không đổi.

## B2: hình học phụ đề

- Đơn vị là tọa độ **logical của Qt**, không nhân thêm devicePixelRatio và không sửa vùng capture vật lý.
- Chọn màn hình chứa tâm overlay trước khi đổi kích thước. Nếu tâm không thuộc màn hình nào, dùng màn hình của widget còn hợp lệ, cuối cùng dùng màn hình chính. Không tự chuyển phụ đề sang màn hình của vùng OCR; đây là lựa chọn vị trí overlay hiện tại.
- Dùng `availableGeometry()`, gồm độ lệch trái/trên và phần taskbar; biên phải/dưới được tính dạng exclusive bằng `x + width`, `y + height`.
- Preset giữ khoảng cách: top_center 60px từ trên; bottom_left 60px từ trái; hai preset dưới 80px từ dưới. Giữ fallback kích thước preset `max(width, 200)` và `max(height, 40)`.
- Clamp sau layout cách mép 10px mỗi trục nếu kích thước cửa sổ cộng 20px còn vừa trục đó; nếu không thì margin trục đó bằng 0. Nếu cửa sổ lớn hơn màn hình, neo trái/trên trên trục bị tràn để tránh clamp đảo chiều. Không cam kết hiển thị hết đoạn cao hơn màn hình trong đợt sửa này.
- Giới hạn chiều rộng bằng `max(1, int(available.width() * 0.75))` khi apply preset và trước layout bản dịch mới. Lấy màn hình trước resize để câu dài không làm đổi màn hình giữa chừng.
- Sau tháo màn hình/khôi phục vị trí custom ngoài desktop, lần update hoặc bật drag mode kế tiếp phải đưa overlay về màn hình còn dùng được. Không thêm schema lưu screen ID hoặc hệ thống profile.

## B4: bản Windows kèm model

- Giữ dạng PyInstaller **one-folder**, đầu ra `dist/main/main.exe`, `console=False`. Chưa tạo installer, auto-update hoặc ký số.
- OCR offline chỉ kèm `en` (English) và `japan` (Japanese). Google/API AI vẫn cần mạng để dịch.
- Giữ UI ngôn ngữ hiện có và chế độ chạy source. Bản frozen chọn ngôn ngữ chưa kèm hoặc thiếu model trả `EngineError('ocr_model_missing', ..., False)` với lời nhắc chọn English/Japanese hoặc cài lại gói đầy đủ; không tự tải và không fallback im lặng sang English.
- Giữ PP-OCRv4 như mặc định của PaddleOCR 2.10.0. Theo mã package đã cài, English dùng detector en PP-OCRv3, Japanese dùng detector multilingual PP-OCRv3, recognizer riêng PP-OCRv4, classifier chung `ch_ppocr_mobile_v2.0_cls_infer` và hai dictionary. Classifier vẫn được `maybe_download` kiểm tra dù `use_angle_cls=False`; phải kèm đủ file của nó.
- Chuẩn hóa staging: `assets/ocr/det/en/`, `det/ml/`, `rec/en/`, `rec/japan/`, `cls/`, `dict/en_dict.txt`, `dict/japan_dict.txt`, `manifest.json`. Mỗi model cần `inference.pdmodel` và `inference.pdiparams`; giữ `inference.pdiparams.info` nếu nguồn có.
- Manifest schema 1 chứa `paddleocr_version='2.10.0'`, `ocr_version='PP-OCRv4'`, `languages=['en','japan']`, `files` ánh xạ relative POSIX path sang SHA-256 và provenance từng nguồn model. Không đặt hash giả trong kế hoạch; tool tạo từ asset thực, review và lưu manifest của gói phát hành.
- Chỉ copy file model/dictionary/manifest/notice đã xác định. `NOTICE.paddleocr.txt` là bản sao `LICENSE` của package PaddleOCR 2.10.0, được hash trong manifest cùng provenance nguồn model; không mặc định rằng notice code thay thế thông tin phân phối trọng số. Không bundle `.env`, `config.json`, credential, cache người dùng, `MORT/`, video hay toàn bộ repository. Không copy toàn bộ thư mục home `.paddleocr` vào spec.
- Frozen đọc resource dưới `sys._MEIPASS/assets/ocr` (layout one-folder `_internal/assets/ocr`); không ghi vào bundle. Config/key vẫn theo AppData/DPAPI hiện có. Source có staging hợp lệ thì dùng, không có staging thì giữ cách PaddleOCR cũ.
- Build tool nhận đường dẫn source cache đã chuẩn bị, không phụ thuộc username. Chuẩn bị model được phép tải trước bằng thao tác riêng có hướng dẫn; runtime frozen không tải. Bước lập kế hoạch này không tải hoặc cài gì.
- Pin công cụ build PyInstaller 6.22.3, tạo lock riêng trên Windows/Python 3.10, giữ runtime version đang khai báo. Vấn đề nhiều distribution OpenCV là rủi ro đã biết: ghi nhận versions thực, smoke native và lưu lock; không tuyên bố đã loại hết chồng lấn `cv2` trong đợt B4.
- Chỉ kết luận phát hành đạt sau smoke trên Windows sạch/VM với cache OCR rỗng và mạng bị tắt. Unit test fake không thay thế cổng này.

## Harness test dùng chung khi triển khai

Với session hiện tại, writable root ngoài repository là thư mục visualization đã cấp. Sang session khác phải chọn root được cấp tương ứng; không xin mở rộng quyền chỉ để dùng lại đường dẫn này.

```powershell
$TestBase = 'C:\Users\Admin\.codex\visualizations\2026\10\25\01a1734a-77f0-7383-b4aa-34f65c30681f'
function Test-Plan {
    param([string[]]$Targets = @('tests'))
    $runDir = Join-Path $TestBase ('plan-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $runDir | Out-Null
    $env:TEMP = $runDir
    $env:TMP = $runDir
    $env:PYTHONUTF8 = '1'
    & .\.venv\Scripts\python.exe -m pytest @Targets -q -p no:cacheprovider --basetemp (Join-Path $runDir 'pytest')
    if ($LASTEXITCODE -ne 0) { throw 'Pytest failed; inspect output before continuing.' }
}
```

Ở bước RED, exception của helper do pytest exit 1 là kết quả dự kiến; đọc failure bên trên để xác nhận thiếu đúng hành vi/API, không phải lỗi fixture hoặc dependency ngoài dự kiến. Baseline 617 chỉ là lần đo trước đó; executor chạy baseline mới và báo chính xác số test hiện tại.

## Nguồn kỹ thuật đã đối chiếu

- [PyInstaller spec files](https://pyinstaller.org/en/stable/spec-files.html): cấu hình data/one-folder và đường dẫn tương đối của spec.
- [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html): `sys._MEIPASS`, `_internal` và resource theo `__file__`.
- Mã PaddleOCR đã cài: `.venv/Lib/site-packages/paddleocr/paddleocr.py:628–689`, `parse_lang:519–527`, `ppocr/utils/network.py:106–129`. Đọc trực tiếp, không import package hoặc tải model khi lập kế hoạch.
