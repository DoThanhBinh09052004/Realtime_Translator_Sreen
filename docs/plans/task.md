| Task | Status | Details |
| --- | --- | --- |
| Task 1: Mở rộng quản lý cấu hình phụ đề trong core/config.py | COMPLETED | Added font_size, overlay_preset, overlay_x, overlay_y to State and config.json persistence |
| Task 2: Nâng cấp ui/overlay.py thành Modern Gaming HUD | COMPLETED | Added QGraphicsDropShadowEffect, dynamic font size, smart max width, presets, and drag mode |
| Task 3: Nâng cấp Tab 4 trong ui/controller.py & Live Preview | COMPLETED | Added Font Size Slider, Position Presets combo, Drag toggle button, and Live Preview update |
| Task 4: Kết nối đồng bộ giữa main.py, ControllerWindow và Overlay | COMPLETED | Connected position_changed signal, restored saved overlay geometry, synced worker mask |
| Task 5: Kiểm thử toàn diện hệ thống (End-to-End Verification) | COMPLETED | Passed all 5 new unit/integration tests and verify_all.py full suite with zero regressions |
| S01: Isolated test harness | COMPLETED | RED: missing isolated_config; GREEN: 11 tests passed; config/.env hashes unchanged; spec and quality reviewed. |
| S02: Validate and persist settings safely | COMPLETED | RED: 47 regressions failed on original code; GREEN: 70 tests passed with cache disabled; config/.env hashes unchanged; spec and code quality self-review completed. Qt tested offscreen; no live desktop/API checks. |
