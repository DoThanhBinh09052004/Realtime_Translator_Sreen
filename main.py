import sys
import os
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QPalette, QColor, QIcon

from core.config import (State, load_config, load_region, initialize_user_storage, ConfigError,
                         load_capture_profile, recover_legacy_capture_profile)
from core.worker import TranslationWorker
from ui.overlay import Overlay
from ui.controller import ControllerWindow
from ui.selector import RegionSelector
from ui.screen_geometry import ScreenGeometryProvider
from ui.game_controls import GameControls
from ui.region_selection import RegionSelectionLifecycle
from core.blocks.geometry import resolve_capture_geometry, subtitle_mask_rect


from ui.styles import CYBER_PALETTE


class ShutdownBarrier:
    """Quit only after both owners have asynchronously drained their threads."""
    def __init__(self, on_ready):
        self._on_ready = on_ready
        self._requested = False
        self._finished = set()
        self._emitted = False

    def begin(self):
        if self._requested:
            return False
        self._requested = True
        self._finished.clear()
        return True

    def finish(self, participant):
        if not self._requested or self._emitted:
            return
        self._finished.add(participant)
        if {'translation', 'language_packs'} <= self._finished:
            self._emitted = True
            self._on_ready()


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


def sync_capture_overlay_mask(worker, rect, legacy_geometry):
    profile = worker.capture_profile
    if profile is None:
        geometry = legacy_geometry
    elif profile.source_kind == 'desktop':
        context = worker.capture_context
        geometry = context.geometry if context is not None else None
    else:
        worker.set_overlay_rect(None)
        return
    worker.set_overlay_rect(subtitle_mask_rect(rect, geometry) if geometry is not None else (rect if profile is None else None))


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
    try:
        state = State()
    except ConfigError as error:
        choice = QMessageBox.warning(None, 'Nguồn chụp không hợp lệ',
            f'{error}\nKhôi phục nguồn màn hình cũ để chọn lại vùng OCR? Cấu hình chỉ thay đổi khi chọn Khôi phục.',
            QMessageBox.RestoreDefaults | QMessageBox.Cancel, QMessageBox.Cancel)
        if choice != QMessageBox.RestoreDefaults:
            return
        try:
            recover_legacy_capture_profile()
            state = State()
        except ConfigError as recovery_error:
            QMessageBox.warning(None, 'Không thể khôi phục', str(recovery_error))
            return
    region = load_region()
    from core.language_pack_catalog import load_pack_catalog
    from core.language_pack_store import PackStore
    from core.language_pack_manager import LanguagePackManager
    from core.paths import get_language_pack_root
    from engines.ocr import ocr_image
    resource_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'ocr'
    pack_store = PackStore(user_root=get_language_pack_root(), bundled_root=resource_root,
                           catalog=load_pack_catalog(resource_root / 'language-packs.json'))
    pack_manager = LanguagePackManager(pack_store, parent=app)

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
    worker = TranslationWorker(state=state, region=region, interval_ms=load_config()["interval_ms"],
                               ocr_reader=lambda image, lang: ocr_image(image, lang=lang, store=pack_store))
    geometry_provider = ScreenGeometryProvider(app)
    capture_geometry = None

    def sync_geometry():
        nonlocal capture_geometry
        if worker.capture_profile is not None:
            sync_mask(overlay.get_geometry_rect())
            return
        selected = load_region()
        capture_geometry = resolve_capture_geometry(selected, geometry_provider.snapshot(), (selected['width'], selected['height']))
        revision = worker.set_capture_geometry(capture_geometry)
        overlay.set_mode(state.overlay_mode, revision)
        sync_mask(overlay.get_geometry_rect())

    def sync_mask(rect):
        sync_capture_overlay_mask(worker, rect, capture_geometry)

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

    def finish_quit():
        overlay.close()
        app.quit()

    shutdown = ShutdownBarrier(finish_quit)
    pack_manager.shutdown_finished.connect(lambda: shutdown.finish('language_packs'))

    def on_quit():
        nonlocal quitting
        if quitting:
            return
        quitting = True
        shutdown.begin()
        if region_lifecycle is not None:
            capture_binding.stop()
            region_lifecycle.request_shutdown()
        if game_controls is not None:
            game_controls.shutdown()
        if controller is not None:
            controller.hide()
        overlay.clear()
        worker.stop_worker()
        pack_manager.shutdown()

    controller = ControllerWindow(
        worker=worker,
        state=state,
        on_select_region=lambda: region_lifecycle.start_selection() if region_lifecycle else None,
        on_quit=on_quit,
        overlay=overlay,
        pack_manager=pack_manager
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

    from ui.capture_binding import CaptureApplicationBinding
    capture_binding = CaptureApplicationBinding(controller, worker, overlay, geometry_provider, region_lifecycle, parent=app)
    controller.ocr_page.capture_settings.set_sources(geometry_provider.snapshot)
    capture_binding.initialize(load_capture_profile(geometry_provider.snapshot()))
    worker.capture_terminal_status.connect(region_lifecycle.on_capture_terminal, Qt.QueuedConnection)
    region_lifecycle.shutdown_finished.connect(lambda: shutdown.finish('translation'))

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
    game_controls.refresh_toolbar_visibility()
    pack_manager.refresh()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
