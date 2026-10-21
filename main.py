import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor, QIcon

from core.config import State, load_config, load_region, save_region
from core.worker import TranslationWorker
from ui.overlay import Overlay
from ui.controller import ControllerWindow
from ui.selector import RegionSelector


from ui.styles import CYBER_PALETTE


def setup_dark_theme(app: QApplication):
    """Thiết lập giao diện Linear / Raycast Pro Dark Theme"""
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(CYBER_PALETTE["bg_main"]))
    palette.setColor(QPalette.WindowText, QColor(CYBER_PALETTE["text_primary"]))
    palette.setColor(QPalette.Base, QColor(CYBER_PALETTE["bg_input"]))
    palette.setColor(QPalette.Text, QColor(CYBER_PALETTE["text_primary"]))
    palette.setColor(QPalette.Button, QColor(CYBER_PALETTE["bg_card"]))
    palette.setColor(QPalette.ButtonText, QColor(CYBER_PALETTE["text_primary"]))
    palette.setColor(QPalette.Highlight, QColor(CYBER_PALETTE["neon_indigo"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


def apply_selected_region(controller, worker, new_region: dict) -> bool:
    """Commit before changing the live capture region; report write errors in UI."""
    if not controller._commit_settings(lambda: save_region(new_region)):
        return False
    worker.set_region(load_region())
    controller._update_region_info_lbl()
    controller._update_all_metric_cards()
    return True


def main():
    app = QApplication(sys.argv)
    setup_dark_theme(app)

    logo_path = os.path.join(os.path.dirname(__file__), "ui", "logo.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    # ===== 1. Cấu hình & Trạng thái =====
    state = State()
    region = load_region()

    # ===== 2. Khởi tạo Overlay (Phụ đề nổi) =====
    overlay = Overlay(
        bg_hex=state.bg_color,
        opacity_pct=state.bg_opacity,
        text_hex=state.text_color,
        font_size=state.font_size
    )
    if state.overlay_preset == "custom" and state.overlay_x is not None and state.overlay_y is not None:
        overlay.move(state.overlay_x, state.overlay_y)
    else:
        overlay.apply_preset(state.overlay_preset)
    overlay.show()

    # ===== 3. Khởi tạo Background Worker =====
    worker = TranslationWorker(state=state, region=region, interval_ms=load_config()["interval_ms"])
    worker.set_overlay_rect(overlay.get_geometry_rect())

    # Kết nối Signal giữa Worker Thread và UI Thread (Thread-safe)
    worker.text_translated.connect(overlay.update_text)
    worker.text_unchanged.connect(overlay.refresh)
    worker.error_occurred.connect(lambda err: print(f"⚠️ Worker Error [{err.code}]: {err.user_message}"))

    def sync_overlay_mask():
        worker.set_overlay_rect(overlay.get_geometry_rect())

    overlay.fade_anim.finished.connect(sync_overlay_mask)
    overlay.position_changed.connect(lambda x, y: sync_overlay_mask())

    # ===== 4. Controller & Selector =====
    controller = None
    selector = None

    def on_select_region():
        nonlocal selector

        # Tạm dừng worker trong lúc người dùng đang chọn vùng
        was_running = worker.is_running()
        if was_running:
            worker.stop_worker()

        controller.hide()
        overlay.hide()

        # Tạo và giữ reference của RegionSelector
        selector = RegionSelector()
        selector.show()
        selector.raise_()
        selector.activateWindow()

        def restore_ui():
            controller.show()
            overlay.show()
            sync_overlay_mask()
            if was_running:
                worker.start_worker()

        def on_region_selected(new_region):
            nonlocal selector
            apply_selected_region(controller, worker, new_region)
            restore_ui()

        selector.region_selected.connect(on_region_selected)
        selector.cancelled.connect(restore_ui)


    def on_quit():
        worker.stop_worker()
        overlay.close()
        app.quit()

    controller = ControllerWindow(
        worker=worker,
        state=state,
        on_select_region=on_select_region,
        on_quit=on_quit,
        overlay=overlay
    )
    controller.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
