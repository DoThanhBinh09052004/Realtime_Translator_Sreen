import sys
import os
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QPalette, QColor, QIcon

from core.config import State, load_config, load_region, initialize_user_storage, ConfigError
from core.worker import TranslationWorker
from ui.overlay import Overlay
from ui.controller import ControllerWindow
from ui.selector import RegionSelector
from ui.screen_geometry import ScreenGeometryProvider
from ui.game_controls import GameControls
from ui.region_selection import RegionSelectionLifecycle
from core.blocks.geometry import resolve_capture_geometry, subtitle_mask_rect


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
    """Compatibility wrapper: the controller owns save and apply ordering."""
    return controller.apply_region_selection(new_region)


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName('TranslateHUD')
    app.setApplicationName('TranslateHUD')
    setup_dark_theme(app)
    try:
        initialize_user_storage()
    except ConfigError as error:
        QMessageBox.warning(None, 'Không thể lưu thiết lập', str(error))

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

    # ===== 3. Khởi tạo Background Worker =====
    worker = TranslationWorker(state=state, region=region, interval_ms=load_config()["interval_ms"])
    geometry_provider = ScreenGeometryProvider(app)
    capture_geometry = None

    def sync_geometry():
        nonlocal capture_geometry
        selected = load_region()
        capture_geometry = resolve_capture_geometry(selected, geometry_provider.snapshot(), (selected['width'], selected['height']))
        revision = worker.set_capture_geometry(capture_geometry)
        overlay.set_mode(state.overlay_mode, revision)
        sync_mask(overlay.get_geometry_rect())

    def sync_mask(rect):
        worker.set_overlay_rect(subtitle_mask_rect(rect, capture_geometry) if capture_geometry is not None else rect)

    overlay.capture_geometry_changed.connect(sync_mask)
    geometry_provider.changed.connect(sync_geometry)
    worker.revision_changed.connect(lambda revision: overlay.set_mode(state.overlay_mode, revision))
    sync_geometry()

    # Kết nối Signal giữa Worker Thread và UI Thread (Thread-safe)
    # Versioned frames prevent queued AI subtitles from resurfacing after a
    # switch to Google (or back); the legacy string signal stays public.
    worker.text_unchanged.connect(overlay.refresh)
    worker.blocks_updated.connect(overlay.update_blocks)
    worker.subtitle_updated.connect(overlay.update_subtitle)
    worker.error_occurred.connect(lambda err: print(f"⚠️ Worker Error [{err.code}]: {err.user_message}"))

    # ===== 4. Controller & GameControls Lifecycle =====
    controller = None
    game_controls = None
    region_lifecycle = None

    quitting = False
    app.setQuitOnLastWindowClosed(False)

    def on_shutdown_finished():
        if quitting:
            overlay.close()
            app.quit()

    worker.shutdown_finished.connect(on_shutdown_finished)

    def on_quit():
        nonlocal quitting
        if quitting:
            return
        quitting = True
        if region_lifecycle is not None:
            region_lifecycle.close()
        if game_controls is not None:
            game_controls.shutdown()
        if controller is not None:
            controller.hide()
        overlay.clear()
        worker.stop_worker()

    controller = ControllerWindow(
        worker=worker,
        state=state,
        on_select_region=lambda: region_lifecycle.start_selection() if region_lifecycle else None,
        on_quit=on_quit,
        overlay=overlay
    )

    game_controls = GameControls(
        controller=controller,
        worker=worker,
        app=app,
        on_select_region=lambda: region_lifecycle.start_selection() if region_lifecycle else None,
        on_quit=on_quit
    )
    controller.set_game_controls(game_controls)

    region_lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=overlay,
        geometry_provider=geometry_provider,
        game_controls=game_controls,
        on_sync_geometry=sync_geometry
    )

    # Show toolbar floating HUD without auto-starting translation
    game_controls.toolbar.show()
    def on_overlay_error(error):
        worker.stop_worker()
        overlay.clear()
        controller.show_overlay_error(error)

    overlay.block_error.connect(on_overlay_error)
    worker.translation_status_updated.connect(controller.show_translation_status)
    worker.revision_changed.connect(lambda revision: controller.clear_translation_status())
    worker.error_occurred.connect(lambda error: on_overlay_error(error) if error.code == 'capture_geometry' else None)
    controller.settings_coordinator.settings_changed.connect(lambda snapshot, field: sync_geometry() if field == 'region' else None)
    controller.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
