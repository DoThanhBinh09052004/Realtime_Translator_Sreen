# Game Dialogue Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giữ mạch đọc hội thoại game đang hiện dần bằng state lượt thoại chung cho Google/AI, phụ đề cố định và overlay theo khối, không xóa/bỏ bản dịch vì chữ nối thêm hoặc nhiễu dấu câu.

**Architecture:** Một DialogueTrack thuần Python phân biệt track, turn và text version; các session xử lý phụ đề hoặc hình học khối. DialogueCoordinator trên GUI event loop sở hữu state/presentation và deadline; capture chỉ phát OCR observation, một backend thread sở hữu TranslationService và phát start/result bất đồng bộ. Overlay chỉ vẽ frame có revision/render sequence hợp lệ.

**Tech Stack:** Python 3.10+, PyQt5 5.15.11, PaddleOCR/OpenCV, OpenAI SDK/httpx hiện có, pytest/pytest-qt, fake clock và fake HTTP. Không thêm dependency.

**Spec:** [2026-10-24-game-dialogue-overlay-design.md](../specs/2026-10-24-game-dialogue-overlay-design.md). Hành vi đã chốt trong hội thoại, tài liệu và kế hoạch chờ đọc duyệt. Giữ lựa chọn thực thi Native trước đó nếu người dùng tiếp tục chọn triển khai theo kế hoạch; không thực thi chỉ vì file kế hoạch tồn tại.

## Global Constraints

- Áp dụng chung cho Google Translate và mọi công cụ AI hiện có, ở cả phụ đề cố định và overlay theo khối.
- Nhịp cân bằng: xét dịch khi chữ ngừng thêm khoảng **0,5 giây**; nếu chữ chạy liên tục, xét phần mới mỗi **1,5 giây**. Đây là mốc đủ điều kiện, không phải cam kết thời gian API/OCR hay cho phép request song song.
- Khi xác nhận hội thoại kết thúc, phụ đề cố định giữ bản cuối thêm **3 giây** rồi ẩn.
- Khối chữ biến mất: gỡ bản dịch ở vị trí đó sau **2 lần OCR thành công liên tiếp** không thấy khối. Chữ dài thêm, xuống dòng hoặc lệch dấu câu không phải là mất khối.
- Khi kết quả mới của **cùng lượt** về quá nhanh, giữ bản đang hiển thị ít nhất **1 giây**, sau đó thay bằng kết quả mới nhất. Chỉ giữ một kết quả chờ trình bày, không phát lại các bản trung gian.
- Tối đa 32 track; toàn ứng dụng một request in flight, tối đa một job chờ mới nhất mỗi track, tổng tối đa 32 job chờ. Kết quả/bản chờ hữu hạn.
- Giữ giới hạn 2000 ký tự/request; vượt giới hạn báo `invalid_input` một lần cho phiên bản, không cắt chữ hay tự chia đoạn ngầm.
- Python 3.10+, PyQt5 hiện có; không thêm dependency, thay OCR engine, đổi endpoint Google, prompt AI, capture exclusion hay thuật toán vẽ/layout.
- Giữ Google batchexecute → clients5 → GTX, một HTTP request vật lý mỗi lần gọi adapter; giữ retry/cooldown, pause thủ công và Retry-After đã có. Chữ mới hoặc cache không được chữa pause hay bỏ cooldown.
- Không tự chuyển công cụ dịch hoặc gọi AI ngoài lựa chọn người dùng. Không có AI suy luận lượt thoại phụ trợ.
- Không sửa `config.json`, `.env`, `MORT/`, video mẫu, launcher hoặc những thay đổi sẵn có của người dùng. Không chạy smoke mạng trong suite mặc định.
- Giữ log request/response dịch đã thêm; không khôi phục log OCR đầy đủ mà người dùng đã yêu cầu bỏ. Không log key, token bí mật, URL có query hay exception/response thô.
- Dừng, thoát, đổi provider/model/key/ngôn ngữ/vùng/mode và revision không còn phù hợp phải vô hiệu hóa callback/presentation đang chờ, xóa ngay; thời gian đọc tối thiểu không vượt các thao tác đó.
- Các giá trị thiết kế kỹ thuật bổ sung: tick 25 ms; khoảng cách dispatch tối thiểu 0,5 giây; challenger hai scan tương thích; regression hai scan và ít nhất 0,5 giây; freshness không có scan tốt: blocks 3 giây, subtitle 6 giây. Đọc spec trước khi thay đổi các giá trị này.

## Review Focus

- Hai câu khác phủ định/số nhưng có chung tên hoặc đầu câu phải chuyển lượt, không bị merge fuzzy — Task 1 và Task 2.
- Start-ack đến sau OCR mới, hoặc A→B→A trong lúc request chạy, không làm hồi sinh turn cũ/mất request cùng turn — Task 4 và Task 5.
- Hai khối gần nhau, đổi vị trí hoặc mất một scan không đổi chéo track hay lưu bản dịch ở vị trí cũ — Task 3 và Task 6.
- GUI nhận kết quả/cache khi capture đang kẹt trong OCR phải áp đúng deadline, không đứng chờ scan — Task 5 và Task 6.
- OCR lỗi kéo dài, scan đi ngược thứ tự hoặc Stop/switch trong thời gian giữ một giây không để callback/timer cũ hồi sinh — Task 3, Task 5 và Task 6.

---

## Trạng thái, cách thực thi và kiểm thử

Chỉ tạo hai tài liệu ở lượt lập kế hoạch. Không coi suite 385 PASS của đợt Google trước là kết quả hiện tại: có thay đổi log chưa commit, `config.json` đã đổi, `MORT/`, launcher và video là dữ liệu hiện có. Kiểm tra `git status` trước khi thực thi, giữ checkout hiện tại trừ khi có yêu cầu cách ly; stage theo đường dẫn task, không dùng `git add .`.

Thực thi Native tuần tự theo thứ tự bảy task vì cùng dùng identity, mailbox và vòng đời Qt. Sau triển khai có một reviewer độc lập đọc toàn bộ thay đổi; các commit task là deliverable kiểm thử được, không phải điểm yêu cầu người dùng duyệt lại. Thực thi vẫn cần người dùng đọc duyệt tài liệu trước.

Định nghĩa helper PowerShell này ở đầu phiên triển khai, dùng thư mục test mới ngoài repository mỗi lần chạy. Đây là hướng dẫn tương lai, không chạy trong lượt viết kế hoạch:

```powershell
function Invoke-DialogueTests([string[]]$TestTargets) {
    $dialogueRun = Join-Path 'C:\Users\Admin\.codex\visualizations\2026\10\22\01a163c1-4a28-7b82-a049-27fb5d7d7c0f' ('dialogue-tests-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force (Join-Path $dialogueRun 'temp') | Out-Null
    $previousTaskTemp, $previousTaskTmp = $env:TEMP, $env:TMP
    try {
        $env:TEMP = Join-Path $dialogueRun 'temp'
        $env:TMP = $env:TEMP
        & .\.venv\Scripts\python.exe -m pytest @TestTargets -q -p no:cacheprovider --basetemp (Join-Path $dialogueRun 'pytest')
        if ($LASTEXITCODE -ne 0) { throw "pytest exited $LASTEXITCODE" }
    } finally { $env:TEMP = $previousTaskTemp; $env:TMP = $previousTaskTmp }
}
```

Mỗi task theo RED → GREEN rồi commit. Không chạy mạng thật/desktop capture thật trong pytest; giữ guard của `tests/conftest.py`. Một test cũ kiểm tra đường AI đồng bộ sẽ được thay bằng test AI bất đồng bộ có assertion tương đương về dịch, retry, stale và lifecycle, không chỉ xóa assertion.

## Bản đồ file và contract chung

| File | Trách nhiệm |
|---|---|
| `core/dialogue/policy.py` (mới) | Policy immutable, identity và phân loại chữ thuần Python |
| `core/dialogue/models.py` (mới) | Observation và presentation immutable, không giữ ảnh |
| `core/dialogue/track.py` (mới) | Turn/version, challenger, eligibility và bản chờ trình bày của một track |
| `core/dialogue/subtitle_session.py` (mới) | Một track phụ đề, biến mất/giữ cuối ba giây/freshness |
| `core/dialogue/coordinator.py` (mới) | QObject chủ state, timer và tín hiệu backend/UI |
| `core/blocks/models.py`, `core/contracts.py` | Thêm metadata version và render sequence, constructor cũ vẫn hợp lệ |
| `core/blocks/session.py` | Giữ ghép hình học, dùng DialogueTrack, missing hai scan |
| `core/blocks/translation_worker.py` | Mailbox latest-per-track, start/result signals, active turn, retry/fairness |
| `core/worker.py` | Capture/OCR observation, facade/lifecycle, một nhánh async cho mọi provider/mode |
| `ui/overlay.py` | Guard render sequence, bỏ timer tự ẩn ở frame managed |
| `tools/replay_dialogue_video.py` (mới) | Record/replay riêng, live chỉ qua cờ explicit |
| `tests/fixtures/dialogue/`, `docs/testing/game-dialogue-overlay.md` (mới) | Transcript rút gọn, kết quả kiểm chứng và cách chạy |

Các tuple identity không chứa source text hoặc key:
- Định nghĩa hai type aliases dưới đây tại `core/dialogue/models.py`; property trong `core/blocks/models.py` có thể annotate tuple trực tiếp để không import ngược tạo vòng tròn.
- `RequestKey = tuple[int, int, int, int]`: revision, track_id, turn_id, text_version.
- `ActiveTurnKey = tuple[int, int, int]`: revision, track_id, turn_id.
- Dùng `BlockJob.block_id` làm track_id hiện có. Bổ sung `turn_id: int = 0`, `text_version: int = 0` và property `request_key` vào BlockJob và BlockTranslationResult. Source snapshot vẫn là trường `source_text`.
- Thêm `SubtitleFrame.render_sequence: int = 0`; giá trị >0 là frame managed. `OverlayFrame.frame_id` do coordinator xuất tăng trên mỗi render publication, không bị giới hạn bởi số scan.

### Task 1: Policy, identity và contract immutable

**Files:** Create `core/dialogue/__init__.py`, `core/dialogue/policy.py`, `core/dialogue/models.py`, `tests/test_dialogue_policy.py`; Modify `core/contracts.py`, `core/blocks/models.py`, `tests/conftest.py`.

**Interfaces:**
- Produces `DialoguePolicy` frozen dataclass và `DEFAULT_DIALOGUE_POLICY`: `quiet_s=.5`, `continuous_s=1.5`, `min_dispatch_gap_s=.5`, `min_read_s=1.0`, `subtitle_end_hold_s=3.0`, `absent_scans=2`, `subtitle_fresh_s=6.0`, `block_fresh_s=3.0`, `tick_ms=25`.
- Produces `identity_text(text: str) -> str`, `classify_text(previous: str, current: str) -> Literal['same','append','regression','different']` theo spec; `source_text` không bị thay bằng identity để dịch.
- Produces frozen `DialogueObservation(revision: int, scan_id: int, captured_at_s: float, completed_at_s: float, settings: RuntimeSettings, ocr: OcrResult, geometry: CaptureGeometry | None)` và `TrackPresentation(turn_id: int, text_version: int, source_text: str, text: str)`.
- Produces contract bổ sung trong bản đồ trên; fixtures `dialogue_observation` tạo observation với geometry tùy chọn, `dialogue_result(job, text='Xin chào', error=None)` sao chép đúng identity và source snapshot của job. Fixtures là factory dữ liệu, không gọi thuật toán sản phẩm.

- [ ] **Step 1: Viết test RED** `test_policy_values_and_identity_contracts` với assertions `(.5,1.5,1.0,3.0,2)` cho quiet/continuous/min_read/end_hold/absent. `classify_text('gods,this','gods, this') == 'same'`; `('but..','but.') == 'same'`; `('now here','nowhere')`, `('I can go','I cannot go')`, `('Take 1','Take 2')`, `('Go?','Go!')` đều `different`; prefix tăng nhiều câu/CJK là `append`, nguồn ngắn hơn là `regression`. Assert constructors cũ còn chạy và metadata mới có request_key đúng.

```python
def test_policy_values_and_identity_contracts():
    p = DEFAULT_DIALOGUE_POLICY
    assert (p.quiet_s, p.continuous_s, p.min_read_s, p.subtitle_end_hold_s, p.absent_scans) == (.5, 1.5, 1.0, 3.0, 2)
    assert classify_text('gods,this', 'gods, this') == 'same'
    assert classify_text('but..', 'but.') == 'same'
    for before, after in [('now here','nowhere'), ('I can go','I cannot go'), ('Take 1','Take 2'), ('Go?','Go!')]:
        assert classify_text(before, after) == 'different'
```

- [ ] **Step 2: Chạy RED** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_policy.py')`; FAIL vì module/contract chưa tồn tại.
- [ ] **Step 3: Tạo interfaces** đúng signatures ở trên, chuẩn hóa NFC/khoảng trắng quanh dấu câu và đuôi period/ellipsis; không thêm thư viện fuzzy hoặc bỏ mọi khoảng trắng.
- [ ] **Step 4: Chạy GREEN** cùng lệnh; PASS, rồi `tests/test_engine_results.py` và `tests/test_block_geometry.py` vẫn PASS.
- [ ] **Step 5: Commit** stage đúng các file Task 1; `git commit -m "feat: define game dialogue identity and timing policy"`.

### Task 2: Một track biết lượt thoại, phiên bản và thời gian đọc

**Files:** Create `core/dialogue/track.py`, `tests/test_dialogue_track.py`.

**Interfaces:** Consumes Task 1. Produces `DialogueTrack(track_id: int, *, policy=DEFAULT_DIALOGUE_POLICY)` với:
- `observe(text: str, *, now_s: float) -> None`, `miss(*, now_s: float) -> bool` (True khi đủ hai lần mất và turn đóng).
- `job(*, revision: int, settings: RuntimeSettings, now_s: float) -> BlockJob | None` trả snapshot mới nhất đủ điều kiện, không đánh dấu dispatch thật.
- `mark_dispatched(job: BlockJob, *, now_s: float) -> None` đăng ký snapshot thật từ backend và đặt mốc dispatch.
- `apply_result(result: BlockTranslationResult, *, now_s: float) -> bool`, `advance(*, now_s: float) -> bool` (True khi presentation đổi).
- `active_turn(revision: int) -> ActiveTurnKey | None`; read-only `presentation: TrackPresentation | None`, `has_pending: bool`, `last_seen_s: float`.

- [ ] **Step 1: Viết RED** `test_quiet_and_continuous_dispatch`: observe `Hello` ở 0, `Hello world` ở .25; job ở .749 là None, ở .75 có source đầy đủ. Chuỗi nối thêm mỗi .25s chưa có hai scan giống nhau vẫn có job ở 1.5s. Sau mark_dispatched tại 1.5, không thêm job cùng source và không gửi phần mới trước min gap .5.

```python
def test_quiet_dispatch_boundary(runtime_settings):
    track = DialogueTrack(7)
    track.observe('Hello', now_s=0)
    track.observe('Hello world', now_s=.25)
    assert track.job(revision=1, settings=runtime_settings, now_s=.749) is None
    job = track.job(revision=1, settings=runtime_settings, now_s=.75)
    assert job.source_text == 'Hello world'
    assert job.request_key == (1, 7, 1, job.text_version)
```

- [ ] **Step 2: Chạy RED** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_track.py')`; FAIL module thiếu.
- [ ] **Step 3: Triển khai turn/version và eligibility** theo các interface; challenger cần hai scan tương thích; regression ngắn không lùi source đã gom, sau hai scan và .5s mới có thể xác nhận reset. Giữ snapshot in flight và pending mới nhất, không lưu lịch sử mọi version.
- [ ] **Step 4: Thêm test RED cho receipt/presentation**: `test_older_prefix_result_survives_growth` cho result v1 sau observe v2 vẫn được áp; `test_newer_result_never_regresses` loại v1 sau khi v2 đã áp. `test_punctuation_does_not_clear_or_requeue`, `test_one_second_hold_keeps_only_latest` nhận v2/v3 trong một giây chỉ hiện v3 ở deadline; repaint cùng text không reset đồng hồ. `test_challenger_and_a_b_a_retire_old_result` cùng tên/khác phủ định và A→B→A không tái dùng turn; callback bị giữ trong challenger chỉ xét lại nếu challenger bị bác. `test_oversized_and_empty_never_dispatch` giữ nguồn >2000, không cắt.
- [ ] **Step 5: Hoàn thiện thuật toán và chạy GREEN** cùng lệnh, toàn bộ assertions PASS. Không dùng edit distance tổng quát để merge các trường hợp phủ định/số.
- [ ] **Step 6: Commit** `core/dialogue/track.py`, `tests/test_dialogue_track.py`; `git commit -m "feat: track progressive dialogue turns and presentation"`.

### Task 3: Session phụ đề và khối giữ đúng chữ, vị trí, deadline

**Files:** Create `core/dialogue/subtitle_session.py`, `tests/test_dialogue_sessions.py`; Modify `core/blocks/session.py`, `tests/test_block_session.py`.

**Interfaces:**
- Produces `SubtitleDialogueSession(*, policy=DEFAULT_DIALOGUE_POLICY)`; `reset(revision: int, settings: RuntimeSettings) -> None`, `observe(text: str, *, now_s: float) -> None`, `tick(*, now_s: float) -> None`, `translation_jobs(*, now_s: float) -> tuple[BlockJob,...]`, `mark_dispatched(job, *, now_s)`, `apply_result(result, *, now_s) -> bool`, `current_frame() -> SubtitleFrame | None`; read-only `active_turns`, `needs_scan`.
- BlockSession giữ `reset()` và `observe(blocks, *, settings, revision, frame_id, geometry, now_s)` hiện có, đổi internals sang DialogueTrack; bổ sung `tick`, `mark_dispatched`, `apply_result(result, *, now_s)`, `translation_jobs(*, now_s)`, `active_turns`, `needs_scan`. `drain_errors()` vẫn trả lỗi oversized hữu hạn. Session không sinh render sequence; coordinator phụ trách publication.
- Consumes Track Task 2, hiện có group_spans/geometry. `active_turns` là frozenset ActiveTurnKey, không phải mọi phiên bản source.

- [ ] **Step 1: Viết RED** `test_subtitle_empty_confirmation_and_three_second_tail`: một scan rỗng giữ turn, scan thứ hai tại t=2 đóng turn; frame còn bản cuối ở 4.999, rỗng ở 5.0; empty scan thêm không gia hạn. `test_reappearing_same_text_is_new_turn` sau xác nhận mất rồi xuất hiện cùng text không nhận callback turn cũ; cache phải có job mới hợp lệ. `test_block_missing_counter_is_not_text_change`: một miss giữ, match lại reset, hai miss mới gỡ.

```python
# test_subtitle_empty_confirmation_and_three_second_tail:
# arrange a valid displayed result 'Xin chào', then submit empty scans at t=1, t=2.
session.tick(now_s=4.999)
assert session.current_frame().text == 'Xin chào'
session.tick(now_s=5.0)
assert session.current_frame().text == ''
assert session.active_turns == frozenset()
# test_block_missing_counter_is_not_text_change: first miss retains the block;
# a matching scan resets the counter; only two consecutive misses remove it.
assert len(frame_after_first_miss.blocks) == 1
assert len(frame_after_match.blocks) == 1
assert frame_after_two_consecutive_misses.blocks == ()
```

- [ ] **Step 2: Chạy RED** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_sessions.py','tests/test_block_session.py')`; FAIL contract mới/session thiếu.
- [ ] **Step 3: Triển khai sessions** dùng track chung, giữ trình bày cũ riêng với turn mới. Blocks giữ phép ghép IoU .30 / khoảng exact text max(64,4×height); không tái dùng ID track đã đóng trong cùng revision. OCR error không gọi miss; chỉ session có observation thành công mới cập nhật last_seen. Tick freshness 3s blocks/6s subtitle chỉ tạm ẩn, callback muộn không tự mở lại visibility trước scan mới.
- [ ] **Step 4: Thêm regression** `test_two_nearby_blocks_never_swap_translations`, `test_geometry_moves_without_old_position_or_hold_delay`, `test_missing_one_block_keeps_other_blocks`, `test_ocr_error_is_not_absence_and_freshness_hides`, `test_recovery_requires_new_observation_before_cached_result_is_visible`. Thêm nguồn tăng nhiều câu/CJK không clear, >32 khối cắt theo thứ tự đọc hiện có và source quá dài báo một lần/version.
- [ ] **Step 5: Chạy GREEN** hai file trên; assertions geometry/matching hiện có được giữ hoặc chuyển sang version-aware, không giảm phạm vi.
- [ ] **Step 6: Commit** chỉ các file Task 3; `git commit -m "feat: retain dialogue overlays across OCR variation"`.

### Task 4: Mailbox theo turn, start/result signals và hàng chờ công bằng

**Files:** Modify `core/blocks/translation_worker.py`, `tests/test_block_translation_worker.py`, `tests/test_google_translation_queue.py`, `tests/test_google_web_priority.py`; Create `tests/test_dialogue_translation_queue.py`.

**Interfaces:**
- `replace_pending(jobs: tuple[BlockJob,...], active_turns: frozenset[ActiveTurnKey], revision: int) -> None` thay active source-text keys cũ bằng turn keys; migrate callers/tests có chủ đích.
- Signals `job_started = pyqtSignal(object)` và `result_ready = pyqtSignal(object)` phát job/result immutable theo đúng thứ tự, sau nhả condition lock. Backend vẫn sở hữu client, Google gate và cleanup.
- Một in flight toàn cục; pending latest-per-track ≤32. In-flight cùng turn được giữ quyền trả kết quả khi pending version thay đổi trước start-ack. `_done` thay bằng highest done version mỗi active turn; retry AI theo active turn, Google theo gate. `drain_results()` có thể giữ tạm cho caller legacy nhưng đường app mới chỉ dùng signal, không áp hai lần.

- [ ] **Step 1: Viết RED** `test_one_inflight_and_latest_pending_per_track`: giữ service bằng Event, enqueue v1 rồi v2/v3; xác nhận chỉ một request đang chạy, pending chỉ v3, completion v1 vẫn phát nếu turn còn active. `test_start_ack_precedes_result_even_when_source_advanced` giữ queued delivery đến sau observation v2, start v1 và result v1 vẫn đúng thứ tự.

```python
# test_one_inflight_and_latest_pending_per_track, using held fake service + qtbot:
assert started.wait(timeout=2)
queue.replace_pending((v3,), frozenset({(1, v1.block_id, v1.turn_id)}), 1)
assert queue.pending_count == 1
assert calls == [v1.source_text]
release.set()
qtbot.waitUntil(lambda: len(calls) == 2)
assert calls == [v1.source_text, v3.source_text]
assert events[0] == ('started', v1.request_key)
assert ('result', v1.request_key) in events
assert peak_inflight == 1
```

- [ ] **Step 2: Chạy RED** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_translation_queue.py')`; FAIL signal/contract chưa có.
- [ ] **Step 3: Triển khai mailbox** duy trì order của track đang chờ qua replace snapshot, chuyển track vừa phục vụ xuống sau các track đang đợi; dùng active turn cho liveness và RequestKey cho done/version. Dọn retry/done khi turn đóng, không tạo state mỗi ký tự vô hạn; signal emission không ở trong condition lock.
- [ ] **Step 4: Thêm test** `test_three_changing_tracks_get_fair_service`, `test_retired_turn_error_still_updates_google_gate`, `test_cache_does_not_heal_pause_or_retry_after`, `test_ai_auth_and_quota_block_until_reconfigure`, `test_ai_text_growth_does_not_reset_retry_budget`. Dùng MockTransport/Event/fake clock; migrate các queue fixture cũ sang turn/version, giữ assertion thứ tự batch→clients5→GTX và bốn lần lỗi tối đa.
- [ ] **Step 5: Chạy GREEN** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_translation_queue.py','tests/test_block_translation_worker.py','tests/test_google_translation_queue.py','tests/test_google_web_priority.py')`; PASS không mạng.
- [ ] **Step 6: Commit** các file Task 4; `git commit -m "feat: deliver versioned dialogue results from shared queue"`.

### Task 5: Coordinator Qt áp kết quả và deadline độc lập OCR

**Files:** Create `core/dialogue/coordinator.py`, `tests/test_dialogue_coordinator.py`.

**Interfaces:**
- `DialogueCoordinator(*, clock=time.monotonic, policy=DEFAULT_DIALOGUE_POLICY, parent=None)` là QObject trên GUI thread, sở hữu hai sessions và QTimer 25ms.
- Slots/public methods: `reset(settings: RuntimeSettings, *, revision: int, session_id: int, running: bool) -> None`, `observe(observation: DialogueObservation) -> None`, `on_job_started(job: BlockJob) -> None`, `on_result(result: BlockTranslationResult) -> None`, `tick() -> None`.
- Signals: `jobs_changed(object, object, int)` = jobs/active_turns/revision; `scan_policy_changed(int, bool)` = revision/needs_scan; `subtitle_updated(object)`, `blocks_updated(object)`, `error_occurred(object)`, `diagnostic_event(object)`.
- Coordinator gọi group_spans cho blocks, tick/observe/apply sessions, sinh sequence publication tăng và emits chỉ trên owner thread. `diagnostic_event` chỉ mốc identity/thời gian/lý do/độ dài; replay bật recorder, không nối log OCR vào trang Tổng quan.

- [ ] **Step 1: Viết RED** `test_result_reaches_overlay_sink_while_next_ocr_is_held`: mô phỏng OCR chưa hoàn tất bằng Event ở thread khác, gửi một observation ổn định và start-ack, sau đó result qua queued signal; qtbot xác nhận sink nhận bản dịch trong 100ms khi event loop rảnh, không nhả OCR. `test_read_and_expiry_deadlines_need_no_new_ocr`: advance fake clock tới một giây/ba giây, gọi tick; frame đổi đúng mốc dù không có observation mới.

```python
# test_result_reaches_overlay_sink_while_next_ocr_is_held: emit the production
# result_ready from a background sender after job_started for the issued job.
qtbot.waitUntil(lambda: any(f.text == 'Xin chào' for f in frames), timeout=100)
assert not release_ocr.is_set()
# test_every_presented_frame_has_monotonic_sequence:
sequences = [f.render_sequence for f in frames]
assert sequences == sorted(set(sequences))
assert min(sequences) > 0
```

- [ ] **Step 2: Chạy RED** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_coordinator.py')`; FAIL module thiếu.
- [ ] **Step 3: Triển khai slots/signals** theo interfaces, lọc revision, settings identity và scan_id tăng dần; dùng `completed_at_s` cho quan sát nguồn và owner clock khi áp/trình bày. Start/result cùng sender có thứ tự queued; không suy luận source snapshot từ text hiện tại. Mọi frame publication kể cả timer/result có render sequence mới, không dùng OCR scan_id làm frame_id cho blocks.
- [ ] **Step 4: Thêm test** `test_late_scan_cannot_rewind_turn_or_geometry`, `test_a_b_a_and_unconfirmed_challenger`, `test_reset_during_hold_drops_timer_and_queued_result`, `test_cache_result_gets_same_identity_checks`, `test_every_presented_frame_has_monotonic_sequence`. Parametrize mode subtitle/blocks và Google/AI settings. Assert không có OCR/SDK call trên GUI từ coordinator.
- [ ] **Step 5: Chạy GREEN** file Task 5 và ba nhóm policy/track/sessions; PASS. Test thời gian 100ms dùng queued events có qapp rảnh, không dùng deadline mạng thật.
- [ ] **Step 6: Commit** `core/dialogue/coordinator.py`, `tests/test_dialogue_coordinator.py`; `git commit -m "feat: coordinate dialogue presentation independently of OCR"`.

### Task 6: Tích hợp worker, overlay, retry và lifecycle cho mọi provider

**Files:** Modify `core/worker.py`, `ui/overlay.py`, `tests/test_google_worker.py`, `tests/test_google_worker_lifecycle.py`, `tests/test_google_app_integration.py`, `tests/test_worker_stabilization.py`, `tests/test_worker_recovery.py`, `tests/test_worker_settings.py`, `tests/test_worker_blocks.py`, `tests/test_worker_block_lifecycle.py`, `tests/test_google_subtitle_overlay.py`; Create `tests/test_dialogue_worker_integration.py`.

**Interfaces:** Consumes Tasks 1–5. Worker remains public facade/signals. Add `observation_ready = pyqtSignal(object)` and `request_dialogue_scan(revision: int, needs_scan: bool) -> None` updating a mutex-protected scan-policy bit. `_uses_async(settings)` returns True for all supported providers/modes. `run()` calls one `_process_dialogue_frame(img_gray, settings, revision, geometry)` to capture timestamps/OCR and emit DialogueObservation; no session mutation, service.translate or backend result polling in capture path.

`_new_block_translator` wires job_started/result_ready to GUI coordinator with queued connections; coordinator jobs_changed calls thread-safe replace_pending. Coordinator output forwards worker existing subtitle/blocks signals. Main/controller don't create extra client or modify provider config. Reset/start/stop coordinator on owner thread and keep revision/settings/session snapshots explicit; capture thread never reads mutable coordinator fields.

- [ ] **Step 1: Viết RED** `test_all_provider_mode_combinations_keep_capture_running`: parametrize Google/OpenAI/Google Gemini/DeepSeek/Custom API và hai mode, giữ SDK fake bằng Event; OCR/capture phải tăng tiếp và active HTTP count luôn ≤1. `test_complete_path_result_does_not_wait_for_capture`: giữ OCR thứ ba, nhả translation, xác nhận production Overlay widget cập nhật mà OCR chưa nhả.

```python
# test_all_provider_mode_combinations_keep_capture_running, for all 10 cases:
qtbot.waitUntil(lambda: len(captures) >= capture_count_at_dispatch + 2)
assert len(requests) == 1
assert peak_inflight == 1
# test_complete_path_result_does_not_wait_for_capture, with fake service success:
qtbot.waitUntil(lambda: overlay.text() == 'Xin chào', timeout=100)
assert not release_ocr.is_set()
# The blocks variant asserts placed_blocks text instead of QLabel text.
```

- [ ] **Step 2: Chạy RED** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_worker_integration.py')`; FAIL AI subtitle còn sync/chưa wired coordinator.
- [ ] **Step 3: Tích hợp worker** giữ frame-change detection, periodic scan tối đa một giây khi idle và force scan khi coordinator needs_scan; OCR retry chung tiếp tục ngay cả backend pause. Xóa nhánh AI subtitle đồng bộ khỏi đường runtime, bỏ state sessions cũ trên capture thread; `GoogleSubtitleSession`/`SubtitleStabilizer` cũ có thể còn module compatibility nhưng không dùng trong đường runtime mới. Giữ intended-running restart, không resurrect thread sau Stop; giữ GoogleRecoveryGate qua internal restart/switch.
- [ ] **Step 4: Sửa Overlay**: managed SubtitleFrame sequence>0 lọc theo revision/render_sequence, tắt hide_timer 6000ms cũ, không để refresh()/cache repaint gia hạn deadline. Sequence0 giữ legacy candidate guard/timer chỉ trước frame managed đầu tiên của revision; sau đó bỏ legacy frame cùng revision. Blocks dùng frame_id publication tăng. Empty/hard reset xóa ngay và queued frame cũ không hồi sinh. Emit legacy text_translated chỉ khi một bản dịch hợp lệ thực sự được publish, không từ stale result.
- [ ] **Step 5: Viết regression lifecycle/UI** `test_stop_provider_model_language_region_and_mode_clear_held_output`, `test_selector_restart_preserves_google_pause_and_deadline`, `test_wrong_provider_status_is_ignored`, `test_block_position_updates_during_minimum_read_hold`, `test_old_legacy_refresh_cannot_revive_managed_subtitle`. Migrate direct `_process_frame` sync tests sang observation+fake backend/coordinator; giữ assertions lỗi/retry/prompt/cache/config/stop. Update fixture factory mocks để nhận `log_callback` khi cần, không bỏ test capture-continues.
- [ ] **Step 6: Chạy GREEN** file mới và các file regression Task 6; sau đó `Invoke-DialogueTests -TestTargets @('tests')` xác nhận toàn suite PASS. Nếu test khác có giả định source-exact keys hoặc sync lane, sửa đúng fixture/contract và giữ mục đích assertion. `git diff --check` không có whitespace errors.
- [ ] **Step 7: Commit** chỉ files Task 6 và tests compatibility thật sự đổi; `git commit -m "feat: enable shared game dialogue overlays for every provider"`.

### Task 7: Replay xác định, video thật và bàn giao bằng chứng

**Files:** Create `tools/replay_dialogue_video.py`, `tests/fixtures/dialogue/progressive_game.json`, `tests/test_dialogue_replay.py`, `docs/testing/game-dialogue-overlay.md`.

**Interfaces:** CLI có ba subcommands: `record --video PATH --crop .20 .75 .80 .89 --size 796 99 --out DIR`, `replay --transcript PATH --latency-ms 700 --mode both --out DIR`, `live --video PATH --provider NAME --allow-network --mode subtitle --out DIR`. `record` và `live` dùng crop/size mặc định như ví dụ và cho ghi đè; replay/live nhận mode `subtitle|blocks|both` (mặc định replay=both, live=subtitle). Record lưu cả text/spans và geometry của vùng crop, dùng OCR thật với opt-in lệnh riêng; replay mặc định offline; live phải có cả provider explicit và allow-network, không lấy active provider ngầm. Cả ba không ghi config/key, không đổi video.

Replay nhập observation transcript vào coordinator, fake backend latency và fake clock, đưa frame qua production Overlay Qt offscreen; recorder ghi request/start/receive/accept/drop/show/clear, revision/track/turn/version, captured/completed timestamps, from_cache, crop/warm-up/tail/EOF. Ghi `summary.json` và `events.jsonl` UTF-8; không dùng stdout encoding mặc định làm hỏng worker khi bản dịch có dấu. Chỉ lưu source transcript ở output do người chạy chỉ định; không mở log OCR trong UI.

Tool exposes `main(argv: list[str] | None = None) -> int` và `run_replay(transcript_path: Path, *, latency_ms: int, mode: Literal['subtitle','blocks','both'], out_dir: Path) -> dict`. Summary bắt buộc có `clears_within_active_turn`, `shown_closed_turn_results`, `peak_inflight`, `peak_pending`; transcript fixture có expected turn boundaries độc lập để assertions không chỉ tin kết luận classifier của sản phẩm. Thiếu provider/allow-network của live trả code 2 trước khi tạo OCR/client.

- [ ] **Step 1: Viết RED** `test_transcript_preserves_progressive_dialogue`: fixture chứa hai lượt, nhiều câu nối thêm/CJK, punctuation jitter, một scan mất và hai scan mất; assert không clear trong cùng turn, có bản phần đầu trước khi kết thúc lượt, callback lượt đã đóng không show. `test_ready_cache_waits_only_read_deadline_not_ocr`: latency0 vẫn dùng đúng deadline, không bị scan dài chặn. `test_live_requires_explicit_provider_and_network_flag`: thiếu một cờ exit≠0 và zero network calls.

```python
def test_transcript_preserves_progressive_dialogue(tmp_path):
    summary = run_replay(Path('tests/fixtures/dialogue/progressive_game.json'),
                         latency_ms=700, mode='both', out_dir=tmp_path)
    assert summary['clears_within_active_turn'] == 0
    assert summary['shown_closed_turn_results'] == 0
    assert summary['peak_inflight'] == 1
    assert summary['peak_pending'] <= 32
```

- [ ] **Step 2: Chạy RED** `Invoke-DialogueTests -TestTargets @('tests/test_dialogue_replay.py')`; FAIL tool/fixture thiếu.
- [ ] **Step 3: Triển khai CLI/fixture** kết nối production interfaces, không sao chép state machine vào tool. Khi đọc video phải phát hiện actual decodable EOF, không tin duy nhất frame_count/fps (clip mẫu báo 24,09s nhưng giải mã được khoảng 19,92s); hold cuối hai giây phải ghi riêng. Dùng transcript như evidence quan sát, không encode expected output trong fake OCR.
- [ ] **Step 4: Chạy GREEN và kiểm chứng cuối** file replay rồi full suite `Invoke-DialogueTests -TestTargets @('tests')`, `git diff --check`. Chạy replay offline cho latency 0/700/2000ms, so số clear do jitter=0, show/drop có lý do, queue bounds/fairness và deadline. Record video thật riêng nếu có file/mô hình; live là smoke opt-in sau người dùng yêu cầu/duyệt, không tự gọi tất cả AI có phí. Không tuyên bố đã sửa trải nghiệm game chỉ dựa trên test fake; ghi rõ phần live/on-screen chưa đo nếu chưa chạy.
- [ ] **Step 5: Ghi tài liệu kiểm chứng** lệnh, exit status, số test thực tế, artifact replay và giới hạn crop/Qt offscreen/mạng; đối chiếu với `scratch/video_overlay_diagnostic_15044/report.md` bằng cùng ROI/đầu vào, không so khác crop rồi gán toàn bộ chênh lệch cho policy.
- [ ] **Step 6: Commit** chỉ file Task 7; `git commit -m "test: verify progressive game dialogue and overlay timing"`.

## Tự rà soát kế hoạch

- Coverage: nhận diện/false merge Task 1–2; nhịp .5/1.5 và min read Task 2; tail3s/miss2/freshness/geometry Task 3; one in flight/latest pending/recovery Task 4; receipt không đợi OCR và publication Task 5; cả provider/mode/lifecycle/UI Task 6; deterministic replay và evidence Task 7.
- Type consistency: block_id là track_id; turn_id và text_version truyền từ BlockJob sang result; active turn 3-tuple khác request key 4-tuple; session timestamps keyword-only, coordinator là nơi gán render sequence. Không dùng candidate_id UI thay request version.
- Review Focus năm nhóm đều có test có tên trong task sở hữu. Không còn mục TBD hoặc phụ thuộc function không được định nghĩa trong Interfaces.
- Không ghi body sản phẩm vào kế hoạch. Native giữ đúng ranh giới task; review độc lập toàn bộ sau khi các task hoàn tất, rồi sửa finding với regression có bằng chứng.

## Bàn giao

Đọc cả spec và plan, đặc biệt các đề xuất kỹ thuật do người thiết kế chọn. Bảy task đều chưa thực hiện. Sau người dùng duyệt tài liệu, dùng `superpowers:executing-plans` nếu giữ Native; nếu họ đổi lựa chọn thì dùng `superpowers:subagent-driven-development`. Không suy ra việc duyệt code từ lựa chọn hành vi trong brainstorming.
