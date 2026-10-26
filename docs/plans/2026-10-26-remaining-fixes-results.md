# Kết quả triển khai ba kế hoạch — 26/10/2026

## Đã thực hiện

- PlainText: QLabel hiển thị nguyên văn, giữ HTML-like text/entities/Unicode và vòng đời drag/mode.
- Geometry: tọa độ logical toàn cục, origin âm, taskbar, clamp từng trục, giới hạn rộng theo màn hình, khôi phục vị trí ngoài desktop; giữ background alpha có trước.
- Bundle: model OCR English/Japanese và classifier/dictionary kèm sẵn, manifest SHA-256; frozen thiếu model/ngôn ngữ khác trả lỗi không retry/download. Source vẫn giữ Trung/Hàn như trước.
- Ba implementer GPT-6.1 Sol Light và reviewer cùng mức; một finding source-language đã sửa và re-review. Final source review spec PASS / quality PASS.

## Bằng chứng

- Baseline: 617 PASS, 84.27s.
- Tích hợp trước review correction: 669 PASS, 131.58s.
- Toàn suite cuối sau sửa: **670 PASS, 65.44s, exit 0**. Network/capture/model giả trong suite mặc định.
- OCR native với socket/DNS chặn trước import, cả .venv cũ và .venv-build khóa dependency: English `Hello worlg` (fragment Hello đạt), Japanese `日本語の翻訳テスト` đạt. Không có engine error. Lần thử đầu với câu `こんにちは世界` đọc thành `二んにちは世界`, exact oracle FAIL; đã giữ raw evidence. Đây không phải cam kết OCR chính xác tuyệt đối.
- Build: PyInstaller 6.22.3, 342.787s, exit 0. `scratch/b4dist-20261026/main/main.exe`; toàn folder 9,480 file / **901,505,001 bytes**, exe 24,932,930 bytes. Giữ cả folder khi chạy/copy, không tách mỗi exe.
- Hash 18 manifest entries và logo trong `_internal` đã xác thực.
- Packaged startup từ foreign cwd: window `Translate HUD - Realtime Screen Translator`, mở được và gửi WM_CLOSE đóng sạch, **exit 0**; không bật capture/API. Kết quả trong `2026-10-26-packaged-startup.json`.
- Lượt startup đầu bị ConfigError modal do sandbox chặn AppData; diagnostic all-window một lượt nhận nhầm Default IME. Harness sửa nhận đúng cửa sổ app và lấy exit code Win32; kiểm tra cuối chạy với quyền AppData thông thường qua escalation đã được chấp thuận. Không cần sửa mã sản phẩm để che các lỗi harness/quyền này.
- Diff whitespace checks trên file sản phẩm đã sửa: sạch; có thông báo Git LF/CRLF sẵn có, không phải lỗi test.

## Quyết định và chi phí

1. Dùng checkout develop hiện tại thay vì chuyển trạng thái dirty sang worktree khác; giảm cách ly, bù bằng ownership và snapshot baseline.
2. Ba implementer theo plan, cùng Sol Light theo yêu cầu; review theo plan và cuối tích hợp thay vì tạo implementer mới cho mỗi task. Chi phí là ít gate độc lập hơn so với SDD mặc định.
3. Progress/review/spec ở docs/plans theo AGENTS; dùng PowerShell thay harness Bash. Tài liệu hiện ignore bởi Git, cần stage có chủ đích nếu muốn commit.
4. Không stage/commit/push: .git chỉ đọc trong permission profile và có nhiều thay đổi người dùng có trước. Kết quả nằm trong workspace, chưa được version hóa.
5. Source Trung/Hàn vẫn legacy dù có staging EN/JP; giữ lựa chọn người dùng cũ, đổi lại có nhánh source/frozen khác nhau.

Build-only albumentations 1.3.1 được pin từ lỗi import Torch của clean resolution; runtime requirements và .venv cũ giữ nguyên. Bytecode tạm bị loại khỏi datas. Output path dài gặp MAX_PATH nên dùng scratch output ngắn, giữ nguyên dist/main cũ. Chồng lấn các distribution OpenCV vẫn là giới hạn đã biết.

## Chưa kiểm chứng

- Máy/VM Windows sạch, cache trống, thư mục app read-only, đường dẫn Unicode và mạng tắt với executable.
- Capture/game thật, nhiều màn hình vật lý, hotplug và DPI 100%/150%.
- Do đó đây là bản build kiểm chứng trên host, chưa chứng nhận hoàn tất cổng phát hành clean-VM.

Chi tiết ở report từng plan và `2026-10-26-execution-progress.md`. Không xóa ledger/snapshot vì chưa có lịch sử commit thay thế.
