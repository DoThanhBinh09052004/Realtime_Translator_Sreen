# Compact Block Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khối dịch có nền vừa đủ che chữ gốc và chứa bản dịch, thay vì chiếm hết khoảng trống trong vùng quét.

**Architecture:** Giữ `OverlayFrame → layout_blocks → paint_blocks` và cửa sổ trong suốt hiện có. Thay cách chọn `PlacedBlock.view_rect` bằng đo chữ Qt và mở rộng có điều kiện; giữ nguyên hợp đồng dữ liệu, font và màu. Xác minh bằng phép đo, ảnh QImage và frame game thật với bản dịch cố định, không gọi dịch vụ.

**Tech Stack:** Python của `.venv`, PyQt5/QTextLayout/QPainter/QImage, pytest/pytest-qt; OpenCV hiện có chỉ dùng đọc video trong công cụ đối chiếu.

**Spec:** `docs/superpowers/specs/2026-10-24-compact-block-overlay-design.md` (người dùng chuyển sang lập kế hoạch sau khi chốt hướng).

## Global Constraints

- “Nếu bản dịch đã vừa, giữ khung này. Nền không nhỏ hơn vùng chữ gốc cần che, kể cả khi bản dịch ngắn hơn.”
- “Nếu bản dịch không vừa, ưu tiên mở rộng sang phải vừa đủ theo kích thước chữ đo thực tế; không mặc định lấy hết khoảng trống.”
- “Khi chạm mép vùng quét hoặc khối chữ khác, xuống dòng và tăng chiều cao vừa đủ trong khoảng trống cho phép.”
- “Chỉ giảm cỡ chữ khi việc mở rộng và xuống dòng vẫn không đủ.”
- “Mỗi khối có một nền hình chữ nhật chung.” Giữ neo trái trên; không thêm hiệu ứng.
- “Dùng PyQt5 và công cụ đo chữ hiện có; không thêm thư viện.”
- “Không thay OCR, cách nhóm câu, lời nhắc dịch, cache, hàng chờ, retry hoặc endpoint dịch.”
- “Không thay đổi bố trí của chế độ phụ đề cố định.” “Không thêm log OCR vào giao diện.”
- Giữ giới hạn cỡ chữ hiện có, padding hiện có, cơ chế cắt chữ an toàn. Lỗi kẹt bản dịch cũ là ngoài phạm vi.
- Không giữ chiều rộng theo lượt thoại; chỉ bố trí nguồn và bản dịch đang hiển thị. Vùng nguồn vốn chồng nhau/ngoài biên được xử lý theo cơ chế an toàn hiện có.
- Không sửa hoặc đưa vào commit các thay đổi đang có ở `config.json`, `ui/overlay.py`, `tests/test_subtitle_background.py`, các launcher hoặc thư mục MORT.

## Review Focus

1. Bản dịch ngắn nhưng khung nguồn dài: nền phải che đủ chữ gốc, không kéo đến biên (Task 1: `test_short_translation_keeps_source_box`).
2. Khung OCR thấp hơn một dòng Qt cộng padding: cho phép tăng chiều cao vừa đủ trước khi giảm font, tránh nới ngang vô ích (Task 1: `test_shallow_source_grows_height_without_full_width`).
3. Vật cản nằm chéo phía dưới: không cắt mất neo/nguồn vốn không chồng nhau hoặc giảm font sớm khi vẫn có khoảng trống hợp lệ (Task 1: `test_diagonal_obstacle_preserves_source_and_readable_font`).
4. DPI lẻ, vùng nguồn bị cắt tại biên, CJK không có khoảng trắng: đo/vẽ nhất quán, không vẽ ngoài canvas hoặc tạo Rect không hợp lệ (Task 1: `test_fractional_geometry_and_tiny_canvas_stay_safe`).
5. Cửa sổ overlay rộng nhưng khối ngắn, sau khi đổi câu/style: phần ngoài khối phải trong suốt và không còn nền cũ (Task 2: `test_compact_background_pixels_and_relayout`).

## Files and responsibilities

- Modify `ui/block_layout.py`: chọn kích thước khối nhỏ nhất phù hợp ưu tiên, dùng cùng font khi đo/vẽ; giữ `PlacedBlock` và API công khai.
- Modify `tests/test_block_layout.py`: tiêu chí kích thước, thứ tự mở rộng/giảm font và an toàn hình học.
- Modify `tests/test_block_overlay.py`: ảnh nền thực tế, cập nhật frame/style và tính trong suốt bên ngoài khối.
- Create `tests/fixtures/blocks/compact_game_dialogue.json`: vài quan sát OCR thật, bản dịch tiếng Việt cố định, thời điểm video/crop/kích thước ảnh có nguồn gốc rõ ràng; không chứa khóa/config.
- Create `tools/render_block_layout_preview.py`: dựng ảnh so sánh trước/sau từ fixture và video cục bộ, qua chính `layout_blocks`/`paint_blocks`.
- Create `tests/test_compact_block_preview.py`: kiểm tra công cụ với ảnh tổng hợp, không phụ thuộc video không tracked, Paddle hoặc HTTP.
- Create `docs/testing/compact-block-overlay.md`: lệnh, ảnh và số đo đối chiếu, kết quả test cùng giới hạn kiểm chứng.

## Execution setup

Đề xuất **Native**: hai task dùng chung cách đo và vẽ; một reviewer độc lập cuối đợt. Chờ người dùng duyệt kế hoạch và phương thức trước khi triển khai. Khi triển khai, đọc skill using-git-worktrees và tái sử dụng checkout phù hợp theo chỉ dẫn workspace; không tự chuyển nhánh hoặc mang thay đổi đang có đi nơi khác.

Dùng `.venv/Scripts/python.exe`. Trước mỗi lượt pytest, tạo thư mục tạm riêng ngoài repo tại writable visualization root, gán `TEMP`/`TMP` và truyền `--basetemp` là thư mục con mới; không tái sử dụng basetemp của lượt trước. Ví dụ PowerShell:

```powershell
$testRun = Join-Path 'C:\Users\Admin\.codex\visualizations\2026\10\22\01a163c1-4a28-7b82-a049-27fb5d7d7c0f' ('compact-overlay-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRun | Out-Null
$env:TEMP = $testRun
$env:TMP = $testRun
# Dùng --basetemp (Join-Path $testRun 'pytest') trong lệnh pytest ngay sau đó.
```

### Task 1: Khung vừa đủ, giữ neo nguồn và thứ tự ưu tiên

**Files:** Modify `ui/block_layout.py:19-88`, `tests/test_block_layout.py`.

**Interfaces:** Consumes `OverlayFrame(revision, frame_id, geometry, blocks)`, `OverlayBlock(block_id, source_text, translated_text, source_rect)`, `Rect` và `ocr_rect_to_overlay(rect, geometry)`. Produces nguyên API `layout_blocks(frame: OverlayFrame, *, max_font_px: int, font_family: str = 'Segoe UI') -> tuple[PlacedBlock, ...]`; giữ các field của `PlacedBlock`.

- [x] **Step 1: Viết regression test cho nền ngắn và mở rộng ngang tối thiểu.**

  `test_short_translation_keeps_source_box`: nguồn `Rect(20,20,320,40)`, dịch `Xin chào`, canvas 800×600; assert `view_rect == source_rect`, font ưu tiên không giảm, `clipped is False`.

  `test_horizontal_growth_is_minimal`: nguồn `Rect(10,10,30,40)`, dịch `Vị thần điều khiển gió`, max font 22; assert giữ x/y/height, rộng hơn nguồn nhưng nhỏ hơn khoảng trống đến canvas, font giữ mức ưu tiên, chữ vừa. Đo lại bằng `QTextLayout` với font của khối và padding tổng 4px; giảm chiều rộng 1 logical pixel phải không còn vừa nếu chưa chạm chiều rộng nguồn. Không dùng tỷ lệ 40%/55% như ngưỡng thuật toán.

- [x] **Step 2: Chạy hai test mới để thấy FAIL do khối chiếm hết khoảng trống.**

  Run: `.venv/Scripts/python.exe -m pytest tests/test_block_layout.py -q --basetemp <unique-path>`.
  Expected: các assertion giữ khung/mở rộng tối thiểu thất bại trên code cũ; ghi nhận kết quả trước khi sửa.

- [x] **Step 3: Bổ sung các test về thứ tự ưu tiên và hình học.**

  `test_wraps_and_grows_height_before_shrinking`: nguồn sát mép phải; bản dịch dài buộc nhiều dòng; assert tăng chiều cao vừa đủ, giữ font ưu tiên khi canvas đủ cao, giữ neo/phủ nguồn, không tràn. Giảm height 1px phải làm mất fit nếu height đã vượt nguồn.

  `test_shallow_source_grows_height_without_full_width`: nguồn rộng 320 nhưng cao 8; dịch ngắn một dòng; assert giữ width 320, tăng height đủ chứa chữ và 4px padding, giữ font ưu tiên (mức sàn 10px).

  `test_diagonal_obstacle_preserves_source_and_readable_font`: khung nguồn không chồng nhau, một khung dưới/phải chặn phương án mở rộng lớn; chọn độ dài dịch bằng đo Qt để tồn tại phương án hẹp/cao ở font ưu tiên; assert giữ neo, phủ nguồn, không giao khối/vật cản, giữ font đó. Thêm ca vật cản ngang và dưới trực tiếp.

  `test_fractional_geometry_and_tiny_canvas_stay_safe`: parameterize mapping logical/physical 1:1 và 1:1.25, nguồn cắt biên, canvas 30×12, chuỗi Việt/CJK dài; assert Rect dương trong canvas, font trong giới hạn hiện hành, clipped khi không vừa và không crash. Giữ test cũ về CJK/va chạm; thêm ca nguồn vốn chồng nhau chỉ yêu cầu kết quả an toàn, không yêu cầu phủ cả hai nguồn.

- [x] **Step 4: Sửa `layout_blocks` trong `ui/block_layout.py`.**

  Đo bằng `_lines`/`QTextLayout`; giữ padding 2px mỗi phía, công thức font ưu tiên hiện có `max(10, min(max_font_px, round(.8*source.height)))`. Nếu chữ vừa khung nguồn đã clip thì trả khung đó. Nếu không, tìm mức mở rộng ngang nhỏ nhất đủ dùng trong chiều cao nguồn; nếu chiều cao nguồn còn thiếu cho một dòng thì không nới ngang vô ích. Tiếp theo chọn khung an toàn có xuống dòng và tăng chiều cao tối thiểu; chỉ sau khi không có khung hợp lệ ở font ưu tiên mới tìm cỡ chữ nhỏ hơn, sàn 10px, rồi clipping hiện có.

  Xét các giới hạn từ canvas, tất cả khung nguồn khác và khung đã đặt, kể cả vật cản chéo phía dưới. Các nguồn không chồng nhau phải giữ neo và được khung kết quả chứa đủ; không dùng phép chọn mảnh diện tích lớn nhất làm mất neo khi mở rộng gặp vật cản. Với nguồn vốn chồng nhau giữ fallback trừ/cắt an toàn. Có thể thêm helper private trong cùng file; không tách module hay đổi schema. Sai số kích thước tối thiểu tối đa 1 logical pixel; xử lý tọa độ float bằng ceil khi tìm kích thước.

- [x] **Step 5: Chạy toàn bộ `tests/test_block_layout.py` và `tests/test_block_geometry.py`; expected PASS.** Không giảm assertion cũ về giới hạn cỡ chữ, clipping, hình học để làm test xanh.

- [x] **Step 6: Commit riêng Task 1.** `git add ui/block_layout.py tests/test_block_layout.py`; `git commit -m "fix: size block overlays to source and translated text"`.

### Task 2: Kiểm chứng nền thực tế và frame game có sẵn

**Files:** Modify `tests/test_block_overlay.py`; create fixture, tool, tool tests và report đã liệt kê.

**Interfaces:** Consumes kết quả Task 1; `paint_blocks(painter, blocks, *, bg_color, text_color)` và `BlockOverlay.set_frame(frame)`, `apply_style(...)`. Produces CLI `python tools/render_block_layout_preview.py --fixture PATH --video PATH --baseline-ref REF --out DIR`; fixture UTF-8 gồm `video_time_s`, `crop`, `image_size_px`, `blocks` (source_text, translated_text, source_rect) cho mỗi frame. Hàm testable `render_comparison(image: QImage, frame: OverlayFrame, *, baseline_layout, max_font_px: int, out_dir: Path) -> dict` trả đường dẫn ảnh và số đo hai phiên bản.

- [x] **Step 1: Thêm `test_compact_background_pixels_and_relayout` trong `tests/test_block_overlay.py`.** Với canvas trong suốt, nguồn dài/dịch ngắn, dùng `paint_blocks` vào `QImage.Format_ARGB32_Premultiplied`; assert pixel nền gần mép phải khung nguồn có alpha, điểm cách mép phải khối 5px có alpha 0. Qua `BlockOverlay` với capture exclusion fake, cập nhật frame dài→ngắn và đổi font/style: assert `placed_blocks` được đo lại, không giữ khung dài cũ, nền ngoài khối mới trong suốt. Giữ kiểm tra capture exclusion/click-through sẵn có.

- [x] **Step 2: Thêm `tests/test_compact_block_preview.py`.** Gọi `render_comparison` bằng ảnh tổng hợp và baseline callable trả khung rộng; assert tạo ảnh before/after và số đo khác nhau, pixel ngoài nền mới vẫn bằng ảnh gốc. Expected FAIL vì tool chưa tồn tại; không gọi OCR/network/config.

- [x] **Step 3: Tạo tool `tools/render_block_layout_preview.py`.** Dùng API Task 1 và `paint_blocks`; đọc video bằng OpenCV, crop/resize khớp fixture, ghép nền/chữ qua QPainter. Để so sánh, đọc duy nhất `ui/block_layout.py` từ `git show REF:ui/block_layout.py` của repo này và nạp thành module baseline riêng; không checkout/reset file. Dùng ref trước Task 1 đã ghi lúc bắt đầu thực thi, không mặc định HEAD sau sửa. Lưu `before-*.png`, `after-*.png`, `comparison.png`, `metrics.json` với source/view/font/clipped. Gặp video không tồn tại hoặc không giải mã được thì báo lỗi rõ, exit khác 0. Không mở ứng dụng hoặc tải model.

- [x] **Step 4: Tạo fixture từ dữ liệu thật hiện có.** Đọc `scratch/dialogue-overlay-20261024/record/transcript.json`, chọn quan sát gần giây 4/7/10 có spans dùng được; lấy block bằng `group_spans(spans, image_size_px)`, ghi đúng thời điểm capture/crop/size từ transcript. Điền bản dịch Việt cố định cho nội dung đã chọn. Không dùng rect giả làm bằng chứng frame thật và không phụ thuộc file scratch trong test thường. Nếu transcript không còn, dùng video mẫu cục bộ và một lượt OCR offline có ghi nguồn; không gọi API dịch. Thêm ca dịch ngắn trên một nguồn thật để kiểm tra nền còn che đủ chữ gốc.

- [x] **Step 5: Chạy focused suite; expected PASS.** Run `.venv/Scripts/python.exe -m pytest tests/test_block_layout.py tests/test_block_geometry.py tests/test_block_overlay.py tests/test_compact_block_preview.py -q --basetemp <unique-path>`. Nếu kiểm tra pixel phát hiện lệch đo/vẽ, sửa tối thiểu `paint_blocks`/`BlockOverlay` trong phạm vi thiết kế rồi chạy lại; không đổi phụ đề cố định.

- [x] **Step 6: Chạy tool trên video sẵn có và xem ảnh thật.** Video: `tests/GENSHIN IMPACT Prologue All Cutscenes (Game Movie) 1080p 60FPS HD [2m55s-3m15s].mp4`. Out: `scratch/compact-block-overlay/`. Kiểm tra ngắn→giữ nguồn, dài→nới đủ, nhiều dòng→nền chung, không kéo mép vô cớ. Các frame không có nút bên cạnh phải xuất hiện trong report; tình huống vật cản được chứng minh riêng bằng test tổng hợp. Không tuyên bố sửa OCR hay lỗi kẹt từ ảnh tĩnh.

- [x] **Step 7: Ghi report và chạy suite đầy đủ.** Report `docs/testing/compact-block-overlay.md` ghi baseline ref, nguồn frame/crop, font và số đo, ảnh so sánh, focused/full test results và giới hạn (offscreen, không đo live capture/provider). Lưu ảnh so sánh nhỏ gọn cần cho review dưới `docs/testing/` và link tương đối trong report; video/ảnh scratch không commit. Run `.venv/Scripts/python.exe -m pytest -q --basetemp <unique-path>`; expected tất cả PASS. Chạy `git diff --check`, phân biệt thay đổi có sẵn.

- [x] **Step 8: Commit riêng Task 2**, stage đúng tests/fixture/tool/report và ảnh so sánh; không `git add -A`.

- [x] **Step 9: Review độc lập cuối đợt theo phương thức đã được duyệt.** Đưa spec, plan, phạm vi commit và ảnh thật cho một reviewer; tập trung năm Review Focus. Sửa finding được xác minh bằng regression, chạy lại nhóm test liên quan; chỉ chạy lại full suite khi sửa code. Báo kết quả và giới hạn kiểm chứng; không tự merge/push.

Kết quả: reviewer độc lập phát hiện 1 Important (khung lồng nhau bị bỏ mất bản dịch), đã sửa qua 2 regression RED→GREEN; focused 28 PASS và full suite 481 PASS, exit 0. Báo cáo: `docs/testing/compact-block-overlay.md`. Không có Minor bị hoãn.

## Plan self-review

- Phủ spec: khung tối thiểu, mở rộng có điều kiện, wrap/height/font, va chạm, biên, DPI → Task 1; nền chữ nhật, không nền dư sau cập nhật và frame thật → Task 2.
- Giữ API/schema và thư viện; font đo/vẽ mặc định Segoe UI. Không thêm tùy chọn font mới; hỗ trợ `font_family` hiện có phải không bị làm xấu đi, không mở rộng tính năng ngoài thiết kế.
- Năm Review Focus đều có test được chỉ tên. Tỷ lệ ví dụ chỉ minh họa; test dùng phép đo Qt và quan hệ hình học thay vì số glyph phụ thuộc máy.
- Baseline không phải HEAD sau sửa; ảnh thật không dùng OCR giả, còn automated tests không yêu cầu video untracked hoặc mạng.
