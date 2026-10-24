# Kiểm chứng overlay hội thoại game

Ngày triển khai: 2026-10-24. Spec và plan tương ứng ở `docs/superpowers/`.

## Hành vi và kiến trúc

- Dùng chung cho Google và các công cụ AI, subtitle và blocks. Capture/OCR không chờ HTTP.
- Đủ điều kiện xét dịch: chữ yên 0,5 giây hoặc luồng chữ tăng liên tục đạt 1,5 giây. Chỉ một request đang chạy; mỗi track giữ phần mới nhất chờ dịch.
- Bản đang đọc không bị xóa do append hoặc nhiễu spacing/period. Cập nhật cùng turn giữ ít nhất một giây; bản chờ chỉ giữ mới nhất.
- Subtitle kết thúc sau hai scan thành công rỗng và giữ cuối ba giây. Blocks gỡ sau hai scan không match; vị trí cập nhật không bị timer đọc giữ lại.
- Không có OCR tốt trong ba giây (blocks) hoặc sáu giây (subtitle) thì tạm ẩn để tránh dữ liệu quá cũ. Lỗi OCR không giả thành scan rỗng.
- Coordinator QObject trên GUI event loop chỉ làm state/deadline; một backend thread giữ SDK/client/cache. Job/result có revision/track/turn/version. Managed frames dùng render sequence; không chạy timer UI tự ẩn cũ.
- Google giữ nguyên thứ tự endpoint, gate pause/retry/cooldown và nút Thử lại. Cache không chữa pause. Lượt mới không hồi sinh callback đã đóng.

Nhận diện là heuristic từ OCR, không đọc trạng thái nội bộ game. Không merge mọi câu gần giống; số/phủ định/dấu hỏi vẫn có nghĩa. Nếu game chuyển trang mà nguồn mới giống hoàn toàn hoặc nối tiếp nguồn cũ và không bắt được khoảng trống, app có thể chưa phân biệt được lượt mới. Vùng OCR cắt mất chữ vẫn gây lỗi nhận diện; tính năng này không sửa nội dung OCR bằng AI.

## Bằng chứng TDD và suite

- Task 1: RED hai lỗi thiếu module; GREEN 30 policy/contracts/results/geometry.
- Task 2: RED tám lỗi thiếu track; GREEN tám track tests.
- Task 3: RED thiếu session/contracts và regression 33 track; GREEN 20 session/track tests, giới hạn 32 được giữ.
- Task 4: RED thiếu signal/active-key contract; GREEN 53 queue/Google-priority tests, gồm latest pending/fairness/retry khi source version đổi.
- Task 5: RED thiếu coordinator; GREEN 31 policy/track/session/coordinator tests. Kết quả queued tới sink trong 100ms khi event loop rảnh, OCR vẫn bị giữ bằng Event.
- Task 6: RED 14 integration failures; GREEN 435 toàn suite trước các test bổ sung, sau đó tám hard-invalidation tests và 51 focused tests sau khi xóa nhánh Google/block cũ khỏi worker.
- Task 7: RED thiếu tool; GREEN bốn replay/CLI tests ở latency 0/700/2000ms. Fixture có expected turn độc lập và có cả lượt đủ dài để nhận được phản hồi 2s; không ép hiển thị kết quả của lượt ngắn đã kết thúc.

Kết quả cuối sau review được ghi bổ sung ở phần cuối tài liệu. Suite mặc định không gọi mạng, không chụp desktop hoặc tải model OCR. Test dùng thư mục TEMP/TMP mới ngoài repository như hướng dẫn trong plan.

## Record và replay riêng

```powershell
.\.venv\Scripts\python.exe tools/replay_dialogue_video.py record --video "tests/GENSHIN IMPACT Prologue All Cutscenes (Game Movie) 1080p 60FPS HD [2m55s-3m15s].mp4" --out scratch/dialogue-overlay-20261024/record
.\.venv\Scripts\python.exe tools/replay_dialogue_video.py replay --transcript scratch/dialogue-overlay-20261024/record/transcript.json --latency-ms 700 --mode both --out scratch/dialogue-overlay-20261024/replay-700
```

Lượt record thật đã hoàn tất exit 0: **34 quan sát OCR**, warm-up **2,385 giây**, ROI x=20–80%, y=75–89% và resize 796×99. Metadata video báo khoảng 24,09 giây nhưng EOF giải mã khoảng 19,92 giây; transcript giữ riêng tail hai giây. Capture/OCR được record offline tuần tự, có captured/completed timestamps; không phải benchmark FPS lúc game đang chạy.

Replay đã chạy exit 0 cho cả hai mode ở ba mức latency. Backend replay là fake transport một completion được hẹn giờ, dùng coordinator/session/widget sản phẩm; không đo retry/fairness backend thật bằng tool này (đã có integration tests). Capture exclusion native được bỏ qua trong Qt offscreen; không tuyên bố đã đo GPU, khả năng capture hay hiển thị thật trên desktop.

| Latency giả lập | Subtitle: số cập nhật có chữ | Subtitle: số lần clear | Blocks: số cập nhật có chữ | Blocks: số lần clear |
|---|---:|---:|---:|---:|
| 0ms | 6 | 0 | 12 | 1 |
| 700ms | 5 | 0 | 10 | 1 |
| 2000ms | 3 | 0 | 7 | 1 |

Blocks có nhiều lần cập nhật vị trí nên số cập nhật không phải số lượt thoại. Một lần clear blocks chưa được gán nguyên nhân ngữ nghĩa bằng nhãn thủ công. Transcript video thật không có oracle, các metric `clears_within_active_turn`/`shown_closed_turn_results` là null, không giả định luôn bằng 0. Fixture được gán turn trong suite mới kiểm chứng hai metric đó.

So sánh phụ đề kiểm soát trên **cùng transcript OCR, cùng độ trễ fake** với `GoogleSubtitleSession` legacy:

| Latency giả lập | Legacy: số cập nhật / clear | Mới: số cập nhật / clear |
|---|---:|---:|
| 0ms | 5 / 4 | 6 / 0 |
| 700ms | 4 / 3 | 5 / 0 |
| 2000ms | 2 / 1 | 3 / 0 |

Đây là so policy nhận/giữ kết quả, không phải đo tốc độ API hoặc chất lượng dịch; không so độ trễ mạng thật khác ngày rồi gán cho kiến trúc. Các artifact: `scratch/dialogue-overlay-20261024/record/transcript.json`, `replay-{0,700,2000}/events.jsonl`, `summary.json` và `comparison.json`.

## Live smoke chỉ khi chọn rõ

```powershell
.\.venv\Scripts\python.exe tools/replay_dialogue_video.py live --video "PATH_TO_VIDEO.mp4" --provider "Google Translate" --allow-network --mode subtitle --out scratch/dialogue-live
```

Thiếu provider hoặc `--allow-network` trả code 2 trước khi khởi tạo OCR/client. Live dùng video thay mss trong phạm vi lệnh, production worker/OCR/backend và Qt offscreen; không lưu provider/vùng vào config. API key được đọc nội bộ từ cấu hình provider explicit, không in key. Live AI có thể dùng quota tài khoản. Lượt triển khai này không chạy thêm live network smoke; trước đó chỉ có test Google/OpenAI của các đợt đo riêng.

## Các quyết định trong triển khai

- Dùng feature checkout hiện tại, giữ cấu hình/launcher/MORT/video; không tạo worktree mới. Đánh đổi: thay đổi nằm cùng nhánh hiện có.
- Dùng PowerShell/Python thay Bash skill harness, vẫn có briefs/ledger/RED–GREEN. Đánh đổi: không có review package sinh bằng Bash.
- Giữ zero-version jobs/drain_results cho caller legacy; đường sản phẩm mới dùng turn/version dương và result signals. Đánh đổi: thêm nhánh compatibility cần bảo trì.
- Giữ helper direct-call `_process_frame` và unit tests cũ cho embedding; `run()` chỉ đi qua capture async mới, không gọi helper đó. Đánh đổi: còn mã tương thích đồng bộ ngoài đường runtime chính.
- Commit tiếp phần log dịch đã được người dùng yêu cầu ở lượt trước cùng tích hợp, vì worker sử dụng log_callback và người dùng giữ bảng log; không sửa cấu hình người dùng. Đánh đổi: range review rộng hơn phần cơ chế hội thoại thuần túy.

## Review cuối

Chưa ghi verdict cho đến khi reviewer hoàn tất và suite cuối chạy xong; phần này được cập nhật trong commit bàn giao.
