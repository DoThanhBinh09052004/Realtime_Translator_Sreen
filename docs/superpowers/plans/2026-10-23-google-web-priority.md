# Google Web Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ưu tiên batchexecute → clients5 → GTX cho Google, không thêm request ẩn hoặc vượt ngân sách/cooldown chung.

**Architecture:** Thêm parser và trạng thái chọn đường trong GoogleTranslateClient, giữ facade/worker/gate/UI hiện có. Một translate là tối đa một HTTP request; lỗi retry được mới tiến đường, thành công giữ đường hiện tại đến khi client đóng.

**Tech Stack:** Python/PyQt5, httpx 0.28.1, pytest/MockTransport; không thêm dependency.

**Spec:** ../specs/2026-10-23-google-web-priority-design.md. Người dùng đã duyệt thiết kế, cho phép lập kế hoạch rồi triển khai Native trong cùng lượt.

## Global Constraints

- Thứ tự batchexecute → clients5 → GTX; tới GTX không quay vòng.
- Mỗi translate tối đa một HTTP request, timeout 8 giây, không redirect/retry ngầm.
- Core giữ lần đầu + tối đa 3 retry; 429 tôn trọng Retry-After, thiếu/invalid dùng 30 giây. Không đổi GoogleRecoveryGate.
- Thành công giữ đường; input/rỗng không chuyển; 403/redirect/HTML/payload sai vẫn nonretry, không tự fallback.
- Giữ API translate/TranslationResult và cấu hình Google/AI; không sửa UI/OCR/capture/MORT/config.json/.env/video.
- Parse đủ segment, giữ Unicode/khoảng trắng; không cache lỗi hoặc log source/query/body/exception thô.
- Pytest không gọi mạng thật. Python .venv; TEMP/TMP/basetemp mới nằm ngoài repo trong writable visualization root.

## Review Focus

- Batch có nhiều frame/RPC và nhiều đoạn, metadata chứa chữ không được dùng làm bản dịch — Task 1.
- HTTP200 với HTML, JSON thiếu/segment hỏng không được làm mất chữ hoặc chuyển route âm thầm — Tasks 1, 2.
- Scene cũ lỗi vẫn làm dịch vụ chờ; đổi scene và cache không reset route/budget — Task 3.
- Chuyển sang clients5/GTX sau 429 không được dispatch trước deadline; đủ bốn lỗi thì không request thứ năm — Task 3.
- Client đóng rồi dùng lại ưu tiên batch; query clients5 và POST body không lọt log — Task 2.

## File map

- engines/google_translate.py: parsers batch/clients5, route selection, HTTP request, log redaction; GOOGLE_ADAPTER_VERSION=2.
- tests/test_google_web_priority.py: new parser/adapter/queue integration tests, synthetic RPC fixtures local to test.
- tests/test_google_adapter.py, tests/test_google_translate.py, tests/test_google_app_integration.py: migrate successful fake GTX payloads to the now-default batch shape without weakening old assertions.
- tools/smoke_google_translate.py: keep CLI contract, optionally add safe route field only if needed.
- docs/testing/google-translate-verification.md: current full-suite and live smoke evidence; preserve old observations as history.

### Task 1: Strict Google web response parsers

**Files:** engines/google_translate.py, tests/test_google_web_priority.py.
**Interfaces:** Add parse_batch_response(content: str) -> str and parse_clients5_response(payload: object) -> str; both raise ValueError for invalid/empty responses. Keep parse_google_response(payload) for GTX.

- [x] **Step 1:** Write test_batch_framing_rpc_and_all_segments: XSSI/numeric framing, unrelated RPC preceding MkEWBc, multiple segments `'Xin chào. '` + `'世界\nDòng 2'` yield exact joined string; malformed matching RPC/segment and HTML fail. test_clients5_parser_preserves_segments rejects empty/mixed/non-list; GTX parser regression remains.
- [x] **Step 2:** Run those tests with isolated TEMP; expect missing parser imports (RED).
- [x] **Step 3:** Implement parsers with JSON decoding, exact RPC identity and strict shape/type checks. Reject malformed translation segments, ignore unrelated metadata frames; join all translated segments without invented spaces.
- [x] **Step 4:** Run parsers + current adapter tests; expect all PASS.
- [x] **Step 5:** Commit exact source/test files: feat: parse Google batch and clients5 responses.

### Task 2: Ordered single-request adapter and compatibility tests

**Files:** engines/google_translate.py, tests/test_google_web_priority.py, tests/test_google_adapter.py, tests/test_google_translate.py, tests/test_google_app_integration.py.
**Interfaces:** Keep GoogleTranslateClient(*, client_factory=None, wall_clock=time.time), translate(text,source_lang,target_lang), close(). Internal integer route index starts0, advances only on retryable error capped2; close resets0. GOOGLE_ADAPTER_VERSION=2 consumed by existing facade cache.

- [x] **Step 1:** Write test_adapter_priority_and_sticky_success (batch503→clients5 success→clients5 success); test_retries_progress_to_gtx_without_looping (all503: batch,clients5,gtx,gtx); verify RPC request/source/target Unicode and input/token invariants. Invalid input,400,403,302,HTML/malformed keep route. close then reuse batch; owner-thread lifecycle includes POST. Capture httpx logs for all hosts while ensuring actual q/body still reaches transport.
- [x] **Step 2:** Run new adapter tests; expect current GET/GTX default and missing routes RED.
- [x] **Step 3:** Implement route/request dispatch using Task1 parsers. Map response/errors as before; move route only after structured retryable failure. Share one lazy httpx client, no loops/retries inside translate; redact both GET query hosts.
- [x] **Step 4:** Update successful fake transports to batch format/POST mocks; retain error/cache/thread assertions. Run all adapter/provider/service/smoke tests and app integration; expect PASS.
- [x] **Step 5:** Commit exact files: feat: prioritize Google batch with clients5 and GTX fallback.

### Task 3: Shared recovery proof, full verification and independent review

**Files:** tests/test_google_web_priority.py, docs/testing/google-translate-verification.md; source changes only for reproduced defects.
**Interfaces:** Consume actual TranslationService, BlockTranslationWorker, GoogleRecoveryGate and fake clock/MockTransport. Preserve run_smoke(text,source_lang,target_lang,*,adapter_factory=GoogleTranslateClient).

- [ ] **Step 1:** Add integration coverage: batch429 Retry-After12 → no clients5 before12; then clients5 failure, GTX failure, GTX failure → paused; advance clock10000 -> no fifth request. Stale scene after first failure still counts/cools down and next current source uses next route; cache hit does not heal service gate. New tests already GREEN are integration coverage, not artificial RED.
- [ ] **Step 2:** Run focused Google/queue/lifecycle tests; expect PASS or investigate actual assertion failure before source changes.
- [ ] **Step 3:** Run full suite with isolated TEMP and git diff --check; expect all PASS without skip/xfail Google. Run CLI smoke ONCE with Hello world; record actual translation/error/duration, no repeated probe after429. Update docs with counts, mock/live separation and decisions.
- [ ] **Step 4:** Commit exact files: test: verify ordered Google fallback and shared cooldown.
- [ ] **Step 5:** Dispatch one fresh whole-change reviewer, spec/plan/ledger/base..HEAD, skill requesting-code-review; fix Important/Critical in one RED→GREEN pass, full suite. Keep current feature branch, no merge/push.

## Self-review and execution

Spec coverage: endpoints/route/budget -> Tasks2/3; parser/log/cache/thread -> Tasks1/2; unchanged UI/lifecycle -> full regressions Task3. Interfaces all stay compatible with existing facade/queue. No new architecture/dependency required. Native execution is already authorized by the user's design approval; proceed after saving this plan without another permission round.
