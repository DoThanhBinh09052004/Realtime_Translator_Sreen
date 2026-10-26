# Subtitle Plain Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiển thị nguyên văn nội dung dịch, không để QLabel diễn giải thành HTML.

**Architecture:** Đặt `Qt.PlainText` ở constructor của Overlay. Dùng regression qua đường SubtitleFrame và các chuyển trạng thái hiện có; không escape chuỗi hoặc đổi renderer blocks.

**Tech Stack:** Python 3.10, PyQt5 5.15.11, pytest, pytest-qt.

**Spec:** `docs/plans/2026-10-25-remaining-fixes-design.md`, mục B3; finding B3 trong `docs/plans/2026-10-25-project-audit.md`.

## Global Constraints

- Đọc ràng buộc chung và harness `Test-Plan` trong spec trước khi chạy.
- "Đặt `Qt.PlainText` một lần trong `Overlay.__init__`, trước lần `setText` đầu tiên."
- "Không escape nội dung"; giữ Unicode/xuống dòng và không double-escape.
- Giữ nền alpha, animation 280ms, timer legacy 6000ms và versioning; bảo toàn phần overlay đang sửa chưa commit.
- Không sửa tọa độ, provider, dependency hoặc renderer blocks trong task này.

## Review Focus

- Thẻ `<img>` hoặc `<a>` trong kết quả dịch phải là chữ, không tạo resource/link.
- `&amp;` phải còn nguyên thay vì bị giải mã hoặc double-escape.
- Nội dung Nhật/Việt và xuống dòng phải giữ nguyên sau SubtitleFrame.
- Drag mode và đổi style phải giữ PlainText khi phục hồi phụ đề.
- Đổi mode rồi nhận frame cũ không được hồi sinh chữ hay bật lại AutoText.

---

## File Structure

| File | Vai trò |
|---|---|
| Modify `ui/overlay.py:34–93` | Đặt text format trước text ban đầu |
| Create `tests/test_subtitle_plain_text.py` | Regression trên widget thật, Qt offscreen |
| Modify `docs/plans/2026-10-25-project-audit.md` | Cập nhật B3 sau kiểm chứng |

### Task 1: Giữ nguyên văn bản qua mọi đường cập nhật phụ đề

**Files:** Modify `ui/overlay.py:34–93`; Create/Test `tests/test_subtitle_plain_text.py`.

**Interfaces:**
- Consumes: `Overlay()`, `set_mode(mode, revision)`, `update_subtitle(SubtitleFrame)`, `set_drag_mode(bool)`, `apply_style(...)` hiện có.
- Produces: mọi Overlay có `textFormat() == Qt.PlainText` suốt vòng đời; chữ source không bị biến đổi.

- [ ] **Step 1: Viết regression tham số hóa trên widget thật.** Dùng dữ liệu `'<b>literal</b>'`, `'<img src="file:///missing.png">'`, `'<a href="https://example.invalid">link</a>'`, `'A < B > C &amp; D'`, `'日本語\nTiếng Việt'`. Test cốt lõi:

```python
@pytest.mark.parametrize('text', [
    '<b>literal</b>', '<img src="file:///missing.png">',
    '<a href="https://example.invalid">link</a>',
    'A < B > C &amp; D', '日本語\nTiếng Việt'])
def test_subtitle_keeps_literal_text(qtbot, text):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    overlay.set_mode('subtitle', 2)
    overlay.update_subtitle(SubtitleFrame(2, 1, 'source', text))
    assert overlay.textFormat() == Qt.PlainText
    assert overlay.text() == text
```

Thêm `test_drag_style_and_mode_preserve_plain_text`: nhận `<b>original</b>` revision 2; bật drag, nhận `<i>latest</i>` candidate 2, đổi màu, tắt drag; assert chữ là `<i>latest</i>` và PlainText. Sau `set_mode('subtitle', 3)`, frame revision 2 phải bị bỏ, label rỗng và PlainText; frame revision 3 chứa `日本語 &amp; Việt` phải giữ đúng.

- [ ] **Step 2: Chạy RED.** `Test-Plan -Targets @('tests/test_subtitle_plain_text.py')`. Mong đợi FAIL vì AutoText, không phải import lỗi. Kiểm tra log thất bại trước sửa.
- [ ] **Step 3: Sửa constructor.** Thêm `self.setTextFormat(Qt.PlainText)` trước `self.setText('Subtitle Ready')`; không đổi chữ qua `html.escape`.
- [ ] **Step 4: Chạy GREEN.** `Test-Plan -Targets @('tests/test_subtitle_plain_text.py','tests/test_google_subtitle_overlay.py','tests/test_subtitle_background.py','tests/test_worker_status_ui.py')`. Mong đợi toàn bộ PASS.
- [ ] **Step 5: Chạy toàn suite và kiểm tra diff.** `Test-Plan`; `git diff --check -- ui/overlay.py`. Mong đợi exit 0; ghi kết quả thật vào finding B3 của audit.
- [ ] **Step 6: Commit riêng phần sửa.** `git add tests/test_subtitle_plain_text.py`; dùng `git add -p -- ui/overlay.py` để chỉ stage hunk PlainText, giữ phần nền phụ đề đã có. `git diff --cached` phải không chứa cấu hình/asset/thay đổi nền của người dùng. Commit `fix: render subtitles as plain text`. Nếu audit cần đi cùng commit, `git add -f -- docs/plans/2026-10-25-project-audit.md` sau khi kiểm tra nội dung.

## Self-Review

- Review Focus được ghim bởi test tham số hóa và test vòng đời ở Task 1 Step 1.
- Không có API mới hoặc phụ thuộc kế hoạch geometry/build; có thể triển khai trước để giảm rủi ro.
- Không cần test pixel so font máy cụ thể: format PlainText cùng nội dung nguyên vẹn là contract rendering QLabel cần bảo vệ.
