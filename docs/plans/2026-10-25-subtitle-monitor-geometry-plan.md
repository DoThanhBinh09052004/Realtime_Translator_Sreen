# Subtitle Monitor Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giữ phụ đề trên màn hình đích khi màn hình có origin khác 0, taskbar hoặc độ phân giải khác nhau.

**Architecture:** Tách phép tính preset/clamp thuần sang module nhỏ dùng Qt logical coordinates. Overlay chọn màn hình trước resize, cập nhật giới hạn rộng và áp dụng helper; không đổi capture geometry hoặc block overlay.

**Tech Stack:** Python 3.10, PyQt5 QtCore/QtWidgets, pytest, pytest-qt.

**Spec:** `docs/plans/2026-10-25-remaining-fixes-design.md`, mục B2; finding B2 trong audit cùng ngày.

## Global Constraints

- Áp dụng ràng buộc chung và harness Test-Plan trong spec.
- "Đơn vị là tọa độ **logical của Qt**, không nhân thêm devicePixelRatio và không sửa vùng capture vật lý."
- Khoảng cách preset: trên 60px, trái 60px, dưới 80px; clamp 10px nếu vừa trục; max width 75% vùng làm việc.
- Screen target lấy trước resize; fallback widget screen còn hợp lệ rồi primary. Không tự chọn theo vùng OCR.
- Giữ public API hiện có, revision/sequence, nền alpha và sửa B1. Giữ PlainText nếu kế hoạch B3 đã được thực hiện.

## Review Focus

- Origin màn hình âm ở cả x/y không được ép phụ đề về tọa độ dương.
- Taskbar nằm trên/trái phải làm lệch vùng làm việc đúng một lần.
- Một bản dịch dài không được đổi màn hình do resize và phải cập nhật max width theo màn hình đó.
- Vị trí custom ngoài desktop sau tháo màn hình phải được đưa về màn hình khả dụng ở lần update/drag tiếp theo.
- Cửa sổ lớn hơn vùng làm việc không làm clamp đảo chiều; logical DPI không bị nhân lần hai.

---

## File Structure

| File | Vai trò |
|---|---|
| Create `ui/subtitle_geometry.py` | Phép tính preset/clamp thuần, không QApplication hoặc I/O |
| Modify `ui/overlay.py:34–93,148–194,228–254` | Chọn màn hình, giới hạn width, ghép helper vào layout |
| Create `tests/test_subtitle_geometry.py` | Số liệu oracle cố định cho phép tính |
| Create `tests/test_subtitle_monitor_ui.py` | Integration widget và fallback màn hình |
| Modify `docs/testing/subtitle-monitor-geometry.md` (create if absent) | Checklist smoke desktop thật và kết quả |

### Task 1: Phép tính vị trí độc lập với desktop

**Files:** Create `ui/subtitle_geometry.py`; Create/Test `tests/test_subtitle_geometry.py`.

**Interfaces:**
- Consumes: `QRect` available logical, `QSize` cửa sổ, `QPoint` vị trí mong muốn.
- Produces: `preset_position(available: QRect, size: QSize, preset: str) -> QPoint | None`; `clamp_position(available: QRect, size: QSize, position: QPoint, margin: int = 10) -> QPoint`. Preset không hợp lệ/custom trả None; không mutate input.

- [ ] **Step 1: Viết test với oracle cố định.** `test_preset_in_global_work_area` tham số hóa các hàng dưới với size `(300,60)`; so kết quả chính xác bằng `QPoint`:

| available `(x,y,w,h)` | preset | expected `(x,y)` |
|---|---|---|
| `(1920,0,1920,1080)` | bottom_center | `(2730,940)` |
| `(-1920,0,1920,1080)` | bottom_center | `(-1110,940)` |
| `(0,-1080,1920,1080)` | bottom_center | `(810,-140)` |
| `(1920,40,1880,1000)` | bottom_center | `(2710,900)` |
| `(-1920,-1080,1920,1080)` | top_center | `(-1110,-1020)` |
| `(-1920,-1080,1920,1080)` | bottom_left | `(-1860,-140)` |

`test_clamp_uses_exclusive_global_edges`: area `(-1920,-1080,1920,1080)`, size `(300,60)`, input `(500,500)` → `(-310,-70)`; input `(-5000,-5000)` → `(-1910,-1070)`. `test_oversized_overlay_anchors_at_origin`: area `(1920,0,200,100)`, size `(300,150)`, any position → `(1920,0)`. `test_custom_preset_does_not_move` asserts None. `test_small_preset_uses_legacy_minimum_size`: area `(0,0,1920,1080)`, size `(20,20)`, bottom_center → `(860,960)`.

- [ ] **Step 2: Chạy RED.** `Test-Plan -Targets @('tests/test_subtitle_geometry.py')`; mong đợi thiếu module/helpers.
- [ ] **Step 3: Implement hai signature trên.** Dùng origin + extent; tính margin riêng từng trục như spec. Không gọi màn hình thật hoặc thay capture Rect.
- [ ] **Step 4: Chạy GREEN.** Cùng lệnh; tất cả oracle PASS.
- [ ] **Step 5: Commit.** `git add ui/subtitle_geometry.py tests/test_subtitle_geometry.py`; `git commit -m "fix: calculate subtitle positions in global work areas"`.

### Task 2: Áp dụng vào Overlay và khôi phục vị trí khi đổi màn hình

**Files:** Modify `ui/overlay.py`; Create/Test `tests/test_subtitle_monitor_ui.py`; Create `docs/testing/subtitle-monitor-geometry.md`.

**Interfaces:**
- Consumes: Task 1 helpers; `QGuiApplication.screenAt(QPoint)`, `QApplication.screens()`, `QApplication.primaryScreen()`, `QScreen.availableGeometry()`.
- Produces: private `Overlay._available_geometry(self) -> QRect` chọn màn hình theo policy; public `apply_preset(self, preset: str)`, `update_text(self, text: str)`, `set_drag_mode(self, enabled: bool)` giữ signature.

- [ ] **Step 1: Viết regression integration.** Patch `_available_geometry` để trả QRect cố định, không patch widget move/layout. `test_secondary_monitor_preset` resize overlay `(300,60)`, area `(1920,0,1920,1080)`, bottom_center → `overlay.pos() == QPoint(2730,940)`. `test_update_keeps_negative_monitor` dùng area `(-1920,-1080,1920,1080)`, gọi preset rồi update một đoạn Nhật/Việt dài; assert area chứa frameGeometry và `maximumWidth()==1440`. `test_update_uses_new_monitor_width` đổi area từ 1920 rộng sang 1280 rộng trước update; assert maximumWidth 960 và frame thuộc area mới. `test_restore_offscreen_position_on_update_and_drag` move `(9000,9000)`, area primary `(0,0,1920,1080)`, lần lượt update và bật drag; mỗi lần assert frame thuộc primary. `test_monitor_selection_uses_pre_resize_center` dùng fake screens logical với devicePixelRatio 1.5/2, patch `QGuiApplication.screenAt` trả fake screen với area `(1920,40,1280,680)` và ghi điểm đầu vào; assert diện tích helper trả đúng area không scale; screenAt nhận tâm frame trước update. `test_missing_monitor_falls_back_to_primary` cho screenAt None, widget screen None, primary có area âm; assert helper trả nguyên area primary.
- [ ] **Step 2: Chạy RED.** `Test-Plan -Targets @('tests/test_subtitle_monitor_ui.py')`; mong đợi thiếu helper hoặc sai origin/max width. Dùng monkeypatch `raising=False` chỉ cho helper chưa có để các test preset thực sự bắt lỗi cũ.
- [ ] **Step 3: Ghép helper vào Overlay.** Lấy area trước đổi text/adjustSize, set max width theo area, giữ anchor center/bottom hiện tại rồi clamp. Apply preset tính theo helper. Bật drag cũng set max width, adjustSize và clamp trước show. Không lưu tọa độ mới chỉ do clamp tự động; chỉ user drag release mới phát position_changed như hiện tại.
- [ ] **Step 4: Chạy GREEN và regression.** `Test-Plan -Targets @('tests/test_subtitle_geometry.py','tests/test_subtitle_monitor_ui.py','tests/test_overlay_mask.py','tests/test_google_subtitle_overlay.py','tests/test_subtitle_background.py','tests/test_worker_status_ui.py')`. Mong đợi PASS; nếu B3 đã có, chạy thêm `tests/test_subtitle_plain_text.py`.
- [ ] **Step 5: Kiểm chứng đầy đủ.** `Test-Plan`; `git diff --check -- ui/overlay.py ui/subtitle_geometry.py`. Smoke có mục tiêu trên Windows thật: màn hình phải/trái/trên, taskbar trên/trái, scaling 100%/150%, kéo overlay, đổi câu dài, tháo màn hình rồi update. Ghi trường hợp đã chạy/chưa chạy vào tài liệu smoke; test offscreen không chứng minh native DPI. Cập nhật B2 audit theo bằng chứng.
- [ ] **Step 6: Commit.** Stage test/tài liệu chỉ định và `git add -p -- ui/overlay.py`; giữ các hunk nền alpha có trước. `git diff --cached` chỉ gồm task này. Commit `fix: keep subtitles on the selected monitor`.

## Self-Review

Task 1 ghim origin âm, taskbar và cửa sổ quá lớn; Task 2 ghim chọn màn hình trước resize, DPI logical, thay width và custom ngoài desktop. Hai task dùng cùng QRect/QSize/QPoint; không có phụ thuộc vào plan build hoặc thay schema config.
