# Overlay cho hội thoại game hiện dần

Ngày: 2026-10-24. Trạng thái: người dùng đã duyệt triển khai Native; bảy task và một lượt sửa sau review đã hoàn tất, kết quả tại `docs/testing/game-dialogue-overlay.md`.

## Mục đích và bằng chứng

Giúp người chơi đọc bản dịch liên tục khi game viết dần từng ký tự, một lượt thoại có thể gồm nhiều câu. OCR khác nhẹ không được làm mất bản dịch đang đọc; API trả nhanh phải sớm đến được overlay.

Lượt replay thật ghi tại `scratch/video_overlay_diagnostic_15044/results.json`: 31 lần OCR, trung bình 0,432 giây, 22 lần đổi candidate; ba request Google thành công trung bình 0,499 giây. Một kết quả 0,735 giây bị bỏ vì dấu chấm thay đổi; bản lấy lại từ cache chỉ hiện 0,549 giây. Kết quả cuối chờ thêm 0,818 giây mới cập nhật widget. Qt chạy offscreen; vùng video bị cắt hẹp ở câu đầu; đây không phải đo trình bày GPU hay benchmark tổng quát.

Hiện tại `GoogleSubtitleSession` đổi candidate/xóa bản dịch khi chuỗi nguồn khác; queue và session so khớp chính xác source. `BlockSession` cũng xóa bản dịch khi text đổi và loại track ngay khi mất một scan. Worker lấy kết quả sau OCR; nhánh phụ đề AI còn gọi dịch đồng bộ. Overlay tự ẩn phụ đề sau 6 giây qua timer riêng.

## Các cách đã cân nhắc

1. Tuần tự kiểu MORT: chụp → OCR → đợi dịch → cập nhật. Giữ mạch đọc dễ hơn, ít điều phối; không tiếp tục quan sát trong lúc dịch và có thể bỏ lỡ chuyển thoại.
2. Theo dõi lượt thoại, giữ bản dịch như MORT, dịch bất đồng bộ theo đợt — **người dùng chọn**. OCR tiếp tục; phân biệt lượt thoại với phiên bản chữ trong lượt, giữ nội dung đang đọc trong lúc đợi nội dung mới. Chi phí là state machine và kiểm tra callback/geometry chặt hơn.

Đây là một dự án tích hợp có các phần phụ thuộc nhau, không tách thành những tính năng phát hành độc lập theo từng provider.

## Quyết định của người dùng

- Áp dụng chung cho Google Translate và mọi công cụ AI hiện có, ở cả phụ đề cố định và overlay theo khối.
- Một lượt thoại có thể gồm nhiều câu, xuống dòng, tiếp tục dài thêm; không tách lượt chỉ vì dấu kết câu.
- OCR tiếp tục khi dịch; một request đang chạy toàn ứng dụng, chờ phần nội dung mới nhất thay vì xếp hàng mọi ký tự.
- Giữ bản dịch đang đọc đến khi có bản thay thế hợp lệ. Khi chuyển lượt có thể giữ phần hiển thị cũ làm bản chờ, nhưng kết quả trả muộn của lượt đã đóng không được cập nhật.
- Nhịp cân bằng: xét dịch khi chữ ngừng thêm khoảng **0,5 giây**; nếu chữ chạy liên tục, xét phần mới mỗi **1,5 giây**. Đây là mốc đủ điều kiện, không phải cam kết thời gian API/OCR hay cho phép request song song.
- Khi xác nhận hội thoại kết thúc, phụ đề cố định giữ bản cuối thêm **3 giây** rồi ẩn.
- Khối chữ biến mất: gỡ bản dịch ở vị trí đó sau **2 lần OCR thành công liên tiếp** không thấy khối. Chữ dài thêm, xuống dòng hoặc lệch dấu câu không phải là mất khối.
- Khi kết quả mới của **cùng lượt** về quá nhanh, giữ bản đang hiển thị ít nhất **1 giây**, sau đó thay bằng kết quả mới nhất. Chỉ giữ một kết quả chờ trình bày, không phát lại các bản trung gian.
- Sau khi đã đóng lượt vì biến mất, xuất hiện lại ở cùng vị trí vẫn là lượt mới; cache có thể cung cấp bản dịch cho request mới, callback cũ không được hồi sinh.

## Giới hạn toàn dự án

- Python 3.10+, PyQt5 hiện có; không thêm dependency, thay OCR engine, đổi endpoint Google, prompt AI, capture exclusion hay thuật toán vẽ/layout.
- Giữ Google batchexecute → clients5 → GTX, một HTTP request vật lý mỗi lần gọi adapter; giữ retry/cooldown, pause thủ công và Retry-After đã có. Chữ mới hoặc cache không được chữa pause hay bỏ cooldown.
- Không tự chuyển công cụ dịch hoặc gọi AI ngoài lựa chọn người dùng. Không có AI suy luận lượt thoại phụ trợ.
- Giữ giới hạn 2000 ký tự/request; vượt giới hạn báo `invalid_input` một lần cho phiên bản, không cắt chữ hay tự chia đoạn ngầm.
- Tối đa 32 track; toàn ứng dụng một request in flight, tối đa một job chờ mới nhất mỗi track, tổng tối đa 32 job chờ. Kết quả/bản chờ hữu hạn.
- Không sửa `config.json`, `.env`, `MORT/`, video mẫu, launcher hoặc những thay đổi sẵn có của người dùng. Không chạy smoke mạng trong suite mặc định.
- Giữ log request/response dịch đã thêm; không khôi phục log OCR đầy đủ mà người dùng đã yêu cầu bỏ. Không log key, token bí mật, URL có query hay exception/response thô.
- Dừng, thoát, đổi provider/model/key/ngôn ngữ/vùng/mode và revision không còn phù hợp phải vô hiệu hóa callback/presentation đang chờ, xóa ngay; thời gian đọc tối thiểu không vượt các thao tác đó.

## Nhận diện chữ và lượt thoại — đề xuất kỹ thuật

Các ngưỡng sau do người thiết kế đề xuất để kiểm chứng, không phải con số người dùng đã tự chọn. Dùng module Python thuần, không gửi dữ liệu thêm ra dịch vụ.

Giữ riêng `source_text` dùng để dịch và `identity_text` dùng nhận diện. Source chỉ NFC/thu gọn khoảng trắng như hiện tại; không bỏ tên, chữ, số hoặc ký tự mang nghĩa. Identity chuẩn hóa khoảng trắng quanh dấu câu, dấu nháy cong thành dạng tương ứng và bỏ dao động dấu chấm/ellipsis ở cuối. Giữ `?`, `!`, số và chữ. Không bỏ mọi khoảng trắng giữa từ; `now here` khác `nowhere`.

So sánh có bốn kết quả: `same`, `append`, `regression`, `different`:

- `same`: identity giống nhau. Không tạo phiên bản dịch, không reset timer yên chữ; dấu câu gốc vẫn được giữ cho bản nguồn đã chọn.
- `append`: identity mới chứa toàn bộ identity hiện tại ở đầu. Giữ turn ID, tăng text version; request trước của cùng turn vẫn có giá trị trình bày khi chưa có bản mới hơn.
- `regression`: identity mới là tiền tố ngắn hơn. Một scan hụt không làm lùi source đã gom. Nếu tiền tố ngắn tiếp tục đủ hai scan thành công và tồn tại ít nhất 0,5 giây, chuyển nó thành challenger để không che khuất việc game bắt đầu câu khác cùng tiền tố.
- `different`: mở challenger. Hai scan thành công liên tiếp tương thích với challenger (cùng chữ hoặc nối thêm) xác nhận lượt mới. Nếu nguồn cũ trở lại trước xác nhận thì bỏ challenger. Không merge fuzzy chỉ theo phần trăm giống hoặc tên nhân vật; các cặp khác phủ định/số phải tách.

Khi challenger chưa rõ, giữ bản đang đọc, dừng tạo job cho lượt nghi cũ và tạm giữ tối đa một kết quả của lượt ấy. Challenger bị bác thì xét lại kết quả; xác nhận lượt mới thì loại kết quả đó. Định danh track theo hình học riêng với turn ID và text version. Không thể bảo đảm nhận ra chuyển trang nếu game không có khoảng trống và chữ trang mới hoàn toàn giống/nối tiếp trang cũ; ghi nhận đây là giới hạn OCR, không suy diễn ngữ nghĩa.

## Nhịp gửi và chấp nhận kết quả

Mỗi turn có thời gian bắt đầu, lần thêm chữ có nghĩa cuối, lần dispatch thật cuối và phiên bản đã yêu cầu/áp dụng. Cần tối thiểu hai quan sát thành công trước request đầu. Phần chữ chưa gửi đủ điều kiện khi yên ít nhất 0,5 giây hoặc đạt 1,5 giây từ đầu turn/lần dispatch gần nhất; khoảng cách dispatch tối thiểu 0,5 giây. Timer không tạo request nếu nguồn không thay đổi về identity, đang có challenger, rỗng hoặc quá 2000 ký tự. Capture cần tiếp tục OCR khi còn phần chưa ổn định; không bỏ scan xác nhận chỉ vì ảnh thumbnail gần như đứng yên.

Một track có thể vừa có request đang chạy vừa có một phiên bản mới nhất đang chờ. Pending chỉ được dispatch khi không còn request toàn cục và gate cho phép. Mốc dispatch tính ở lúc translation thread thật sự bắt đầu, không tính khi snapshot được enqueue. Với nhiều khối, giữ thứ tự đọc ban đầu rồi phục vụ luân phiên; không để khối liên tục thay đổi làm các khối khác chết đói.

Job/result gắn `(revision, track_id, turn_id, text_version)` và source snapshot bất biến. Queue không bỏ request cùng turn chỉ vì source tiếp tục dài thêm. Session chỉ nhận phiên bản đã phát hành của turn còn hoạt động, source trùng snapshot đã phát hành, chưa bị áp bởi bản mới hơn. Kết quả của lượt đã đóng hoặc revision khác bị loại, kể cả A → B → A. Kết quả Google lỗi vẫn cập nhật gate trước kiểm tra stale-source. Cache hit đi qua cùng quy tắc identity/presentation và không reset ngân sách lỗi.

Pending/issued snapshot chỉ giữ cho một request in flight và một phiên bản pending mỗi track; dọn lịch sử ngay khi xong/đóng lượt. Retry không tạo thêm nguồn chờ và không gọi SDK trên GUI/capture thread. AI giữ chặn auth/quota/cooldown; retry cho cùng turn không được reset chỉ vì text version tăng.

Backend lọc quyền tồn tại theo active turn `(revision, track_id, turn_id)`, không theo source/version hiện tại. `job_started` và `result_ready` phát cùng backend thread theo đúng thứ tự, coordinator đăng ký snapshot thật đã dispatch ở sự kiện đầu trước khi xử lý sự kiện sau. Cách này tránh mất request đang chạy khi bản pending bị thay trước khi GUI nhận start-ack. `last_done_version` và retry của backend lưu theo active turn, không giữ set mọi phiên bản vô hạn.

## Trình bày và biến mất

State trình bày tách khỏi state chữ mới nhất. Thay đổi OCR không tự phát frame rỗng. Khi cùng turn có bản mới về, nếu chưa đủ một giây từ lần thay chữ thật gần nhất thì chỉ giữ bản mới nhất chờ deadline; tick có thể trình bày mà không đợi OCR khác. Không reset đồng hồ một giây bằng repaint cùng chữ, chuyển geometry hay cache trả lại cùng nội dung. Bản của turn mới có thể thay bản chờ cũ ngay khi hợp lệ; quy tắc một giây chỉ dành các cập nhật cùng turn.

**Phụ đề cố định:** hai scan OCR thành công rỗng liên tiếp xác nhận kết thúc (đề xuất kỹ thuật). Đóng turn ngay ở lần xác nhận thứ hai, hủy quyền áp dụng callback cũ; phần đang nhìn được giữ đúng ba giây từ đó. Hết hạn thì ẩn cả khi OCR đang bận. Lặp scan rỗng không gia hạn; lỗi OCR không tính rỗng. Thoại quay lại mở turn mới; callback/cache mới hợp lệ có thể thay phần cũ trước hết ba giây. Nếu đang đợi lượt mới khi thoại còn tồn tại, giữ phần cũ đến khi có bản mới hoặc tới điều kiện kết thúc/hard invalidation đã nêu.

**Theo khối:** giữ ghép exact text trong khoảng max(64 px, 4× chiều cao), sau đó ghép prefix append/regression có containment trên khối nhỏ ít nhất 0,60 và điểm neo cạnh/tâm lệch không quá max(16 px, chiều cao hai khối), rồi mới fallback IoU tối thiểu 0,30. Đây là hiệu chỉnh kỹ thuật sau review: chỉ IoU sẽ mất track khi typewriter tăng chiều rộng trên 3,33 lần hoặc xuống dòng. Ghép luôn một-một, ưu tiên điểm neo gần để không đổi chéo khối gần nhau. Mỗi lần OCR thành công không match tăng missing_count, match lại reset về 0. Hai scan không match đóng track/turn và gỡ cả hình học lẫn chữ. Một lần mất giữ vị trí cuối; không tính tick/ảnh bỏ qua/error thành mất. Khối match và di chuyển cập nhật vị trí hiện tại ngay, không để lại bản ở tọa độ cũ; timer một giây chỉ giữ chữ, không giữ vị trí. Track mới không thừa hưởng callback track bị đóng dù ở cùng tọa độ. Các khối khác không bị xóa khi một khối mất. Không giữ khối bằng danh sách nguồn OCR cũ không có hạn.

OCR lỗi giữ chính sách retry và trạng thái lỗi hiện có, không giả vờ đã xác nhận nguồn biến mất. Không gia hạn deadline kết thúc hoặc resurrect turn từ lỗi. Giới hạn an toàn khi ngừng nhận quan sát thành công: sau **3 giây** kể từ scan thành công cuối, tạm ẩn khối; phụ đề cố định tạm ẩn sau **6 giây**. Đây là đề xuất kỹ thuật bảo vệ freshness, không đóng turn chỉ vì OCR lỗi; chỉ cho hiện lại sau một quan sát mới còn hợp lệ. Không coi heartbeat/capture thành công là OCR thành công; không đưa cache/kết quả dịch muộn lên khi freshness đã hết.

## Sở hữu state và thread

Không sửa bằng cách gọi `drain_results()` trước OCR rồi vẫn để state ở capture thread: cách đó vẫn chặn kết quả bởi OCR dài. Dùng **DialogueCoordinator(QObject) trên GUI event loop** làm chủ duy nhất của session, track, pending presentation và deadline. Công việc coordinator bị chặn bởi tối đa 32 chuỗi 2000 ký tự, không làm OCR, HTTP hay capture; quan sát và kết quả đi qua queued signals dưới dạng immutable. Timer 25 ms chạy khi phiên hoạt động, xử lý deadline 0,5/1/1,5/3 giây; các mốc là thời gian monotonic, không đếm tick.

- Capture `TranslationWorker.run()` chỉ lấy snapshot settings/region, chụp, mask theo mode hiện có, OCR và emit observation có revision, scan ID, thời điểm chụp/kết thúc, settings, OcrResult, geometry. Giữ frame-change detection và retry OCR; bỏ nhánh AI subtitle gọi dịch trực tiếp. Không truyền ảnh vào queue dịch.
- Coordinator nhận OCR, giữ thứ tự scan tăng dần mỗi revision, gọi session phù hợp, thay pending của backend; nhận kết quả và áp ngay theo **quan sát hoàn tất gần nhất**, không phải đợi OCR đang chạy. Một cảnh chưa OCR xong đương nhiên chưa thể biết; kết quả không được vượt qua lượt mới đã xác nhận.
- Translation thread giữ một TranslationService/client/cache, phát `job_started` và `result_ready` sau khi nhả condition lock. Gate cập nhật ở backend; callback tới coordinator không giữ mutex/condition của capture hoặc backend.
- `worker` tiếp tục là facade lifecycle/signals cho main/controller. Revision/settings đổi reset coordinator và pending ngay trên owner thread; start/stop nối timer theo ý định running, không theo thread HTTP đang drain. Stop/quit không chờ mạng trên GUI.
- GoogleRecoveryGate giữ nguyên qua restart nội bộ và provider switch như hiện tại; explicit Stop/Start mở phiên mới, giữ 429 cooldown. Lỗi stale vẫn tính ở đúng generation. Tín hiệu translation status giữ kiểm tra provider/revision/session của UI.
- `SubtitleFrame` bổ sung render sequence tăng trên mỗi publication, độc lập turn/text version; giữ constructor cũ bằng default 0. Frame mới có sequence >0 dùng sequence làm guard. Frame legacy default 0 chỉ giữ candidate guard khi revision đó chưa nhận frame managed; sau frame managed đầu tiên phải bỏ frame legacy cùng revision. `OverlayFrame.frame_id` trở thành sequence trình bày tăng cho mọi publication, kể cả timer/result/move không có scan mới. Revision luôn kiểm tra trước.
- Với frame do coordinator quản lý, tắt timer tự ẩn 6 giây cũ của UI; coordinator phát frame hết hạn rõ ràng. UI không tự quyết đóng turn. Các thao tác clear/mode/revision vẫn xóa ngay và không được để timer/signal cũ hồi sinh chữ.

## Cấu trúc phần mềm và kiểm chứng

Module chung `core/dialogue/` gồm policy/identity, immutable observation, một DialogueTrack thuần Python, SubtitleDialogueSession và Qt coordinator. `BlockSession` dùng lại track chung và giữ trách nhiệm ghép hình học; `BlockTranslationWorker` dùng request identity mới; facade/adapter dịch không đổi giao thức mạng.

Test bằng fake clock, HTTP/capture/OCR giả và Qt offscreen: append nhiều câu/CJK, dấu chấm/spacing, thay phủ định/số, OCR hụt, A→B→A, stale scan/result/geometry, một pending mới nhất, fairness, deadline khi OCR bị giữ, đọc tối thiểu/expiry, Google cooldown/cache/pause, AI auth/quota, Stop/selector/provider/mode/restart. Suite hiện có giữ assertions quan trọng, sửa fixture/signature có chủ đích khi contract thay đổi, không xóa test để suite xanh.

Replay video thật là lệnh riêng: recorder tạo transcript OCR có captured/completed times và geometry, rồi replay xác định với backend latency giả để so policy không phụ thuộc mạng. Live smoke chỉ bật bằng flag explicit và provider explicit, không tự đọc active provider để chi tiền; ghi nhận crop, warm-up, EOF giải mã thật, phần tail và Qt offscreen. Dùng fixture transcript rút gọn chứa cả `gods,this`/`gods, this`, `but..`/`but.`, một scan mất và chuyển thoại thật. Không chốt ngưỡng bằng cách thuộc lòng tên Paimon hoặc video này.

Chấp nhận khi: chữ nối thêm/dao động dấu câu không xóa overlay, kết quả cùng turn được dùng đúng version, kết quả đã nhận đến widget trong tối đa 100 ms ở test Qt với event loop rảnh ngay cả OCR bị giữ (không gồm timer một giây), đúng mốc 0,5/1/1,5/3 và hai scan mất, geometry không để bóng cũ, hồi phục/lifecycle giữ nguyên. Không hứa latency 100 ms trên mọi máy; đo replay thật riêng.

## Trạng thái kiểm tra thiết kế

Builder check độc lập ngày 2026-10-24: reviewer đã đọc tài liệu và code liên quan, kết luận `nothing important left`. Những con số do người thiết kế đề xuất (freshness 3/6 giây, xác nhận challenger, tick 25 ms) vẫn được phân biệt với lựa chọn của người dùng để xem cùng kế hoạch. Chưa có triển khai sản phẩm trong lượt viết tài liệu này.

Triển khai Native đã được người dùng cho phép ngày 2026-10-24. Review code cuối bổ sung ba quy tắc kiểm chứng: thoại xuất hiện lại trước hạn kết thúc hủy hạn cũ để giữ placeholder đang nhìn, nhưng phần đã hết hạn không được hồi sinh; ghép geometry progressive như trên; một scan thành công rỗng làm đứt chuỗi xác nhận challenger, còn lỗi OCR không được giả thành scan rỗng. Kết quả triển khai và kiểm thử cuối tại `docs/testing/game-dialogue-overlay.md`.
