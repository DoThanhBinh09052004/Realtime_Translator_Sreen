"""Controller composition, navigation and application commands."""
import os
import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QColorDialog, QMessageBox
from PyQt5.QtCore import QObject
from PyQt5.QtGui import QIcon
from core.config import SUPPORTED_LANGUAGES, SUPPORTED_TARGETS, get_available_providers
from ui.pages.console_page import ConsolePage
from ui.pages.ai_settings_page import AiSettingsPage
from ui.pages.ocr_settings_page import OcrSettingsPage
from ui.pages.subtitle_settings_page import SubtitleSettingsPage
from ui.widgets.sidebar import ControllerSidebar
from ui.widgets.cards import ModernCard, MetricCard
from ui.settings_coordinator import SettingsCoordinator
from ui.styles import CYBER_PALETTE, get_app_stylesheet


class ControllerWindow(QWidget):
    """Compose the four views around one settings coordinator."""

    def closeEvent(self, event):
        # Keep widgets alive until the application has drained its worker threads.
        event.ignore()
        self.on_quit_cb()

    def __init__(self, worker, state, on_select_region, on_quit, overlay=None):
        super().__init__()

        self.worker = worker
        self.state = state
        self._overlay = None
        self.settings_coordinator = SettingsCoordinator(state, worker, overlay, self)
        self.on_select_region_cb = on_select_region
        self.on_quit_cb = on_quit
        self._retry_pending = False

        # Window and navigation shell
        self.setWindowTitle("Translate HUD - Realtime Screen Translator")
        self.resize(740, 720)
        self.setMinimumSize(660, 480)
        self.setStyleSheet(get_app_stylesheet())

        # Thiết lập Icon ứng dụng từ logo
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(__file__), "clever-negative-space-logo-design--minimalist-tech.png")

        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # Layout chính dạng ngang: [Sidebar 205px] + [Main Content Stack]
        main_h_layout = QHBoxLayout(self)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # ===== 1. LEFT SIDEBAR =====
        self.nav_item_defs = [
            ("layout-dashboard", "Tổng quan", "Bảng điều khiển nhanh và trạng thái"),
            ("languages", "Công cụ dịch", "Chọn Google Translate hoặc công cụ AI"),
            ("languages", "Dịch thuật & OCR", "Ngôn ngữ nguồn, ngôn ngữ dịch và tần suất quét"),
            ("palette", "Giao diện Phụ đề", "Màu sắc, độ trong suốt và xem trước trực tiếp")
        ]
        self.sidebar = ControllerSidebar(tuple(self.nav_item_defs), logo_path, self)
        self.sidebar_frame = self.sidebar
        self.nav_buttons = self.sidebar.nav_buttons
        self.nav_item_defs = self.sidebar.nav_item_defs
        self.status = self.sidebar.status
        self.sidebar.page_requested.connect(self._switch_to_page)
        self.sidebar.quit_requested.connect(self.on_quit_cb)

        main_h_layout.addWidget(self.sidebar_frame)

        # ===== 2. RIGHT MAIN CONTENT AREA =====
        content_container = QWidget()
        content_v_layout = QVBoxLayout(content_container)
        content_v_layout.setContentsMargins(20, 16, 20, 16)
        content_v_layout.setSpacing(12)

        # Page Header
        header_row = QHBoxLayout()
        header_text_box = QVBoxLayout()
        header_text_box.setSpacing(2)

        self.page_title_lbl = QLabel("Tổng quan")
        self.page_title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.page_desc_lbl = QLabel("Điều khiển tiến trình quét OCR và theo dõi thông số theo thời gian thực")
        self.page_desc_lbl.setStyleSheet(f"font-size: 12px; color: {CYBER_PALETTE['text_muted']};")
        header_text_box.addWidget(self.page_title_lbl)
        header_text_box.addWidget(self.page_desc_lbl)
        header_row.addLayout(header_text_box)
        header_row.addStretch()
        content_v_layout.addLayout(header_row)

        # QStackedWidget chứa 4 trang
        self.pages = QStackedWidget()
        self.metric_cards = {}

        # Khởi tạo 4 trang
        self.console_page = ConsolePage(self.settings_coordinator.snapshot(), self)
        self.start_btn = self.console_page.start_btn
        self.stop_btn = self.console_page.stop_btn
        self.metric_cards = self.console_page.metric_cards
        self.console_page.start_requested.connect(self.start_ocr)
        self.console_page.retry_translation_requested.connect(self.retry_translation)
        self.worker.log_updated.connect(self.console_page.append_log)
        self.console_page.stop_requested.connect(self.stop_ocr)
        self.console_page.select_region_requested.connect(self._on_select_region_clicked)
        self.console_page.subtitle_settings_requested.connect(lambda: self._switch_to_page(3))
        self.page_console = self.console_page
        self.ai_page = AiSettingsPage(self.settings_coordinator.snapshot().ai, tuple(get_available_providers()), self)
        self.provider_combo = self.ai_page.provider_combo
        self.model_combo = self.ai_page.model_combo
        self.api_key_input = self.ai_page.api_key_input
        self.toggle_key_btn = self.ai_page.toggle_key_btn
        self.api_status_lbl = self.ai_page.api_status_lbl
        self.key_card = self.ai_page.key_card
        self.ai_page.provider_changed.connect(self.settings_coordinator.set_provider)
        self.ai_page.model_changed.connect(self.settings_coordinator.set_model)
        self.ai_page.api_key_save_requested.connect(self.settings_coordinator.set_api_key)
        self.ai_page.api_key_delete_requested.connect(self.settings_coordinator.delete_api_key)
        self.ai_page.legacy_key_import_requested.connect(self._import_legacy_key)
        self.ai_page.base_url_changed.connect(self.settings_coordinator.set_custom_base_url)
        self.page_ai = self.ai_page
        snapshot = self.settings_coordinator.snapshot()
        self.settings_coordinator.initialize_worker_interval()
        self.ocr_page = OcrSettingsPage(snapshot.ocr, tuple(SUPPORTED_LANGUAGES), tuple(SUPPORTED_TARGETS), self)
        self.src_combo = self.ocr_page.src_combo
        self.tgt_combo = self.ocr_page.tgt_combo
        self.interval_spin = self.ocr_page.interval_spin
        self.reg_info_lbl = self.ocr_page.reg_info_lbl
        self.ocr_page.source_changed.connect(self.settings_coordinator.set_source)
        self.ocr_page.target_changed.connect(self.settings_coordinator.set_target)
        self.ocr_page.interval_changed.connect(self.settings_coordinator.set_interval)
        self.ocr_page.select_region_requested.connect(self._on_select_region_clicked)
        self.page_ocr = self.ocr_page
        self.subtitle_page = SubtitleSettingsPage(self.settings_coordinator.snapshot().subtitle, self)
        self.bg_color_btn = self.subtitle_page.bg_color_btn
        self.text_color_btn = self.subtitle_page.text_color_btn
        self.font_size_slider = self.subtitle_page.font_size_slider
        self.font_size_val_lbl = self.subtitle_page.font_size_val_lbl
        self.opacity_slider = self.subtitle_page.opacity_slider
        self.opacity_val_lbl = self.subtitle_page.opacity_val_lbl
        self.preset_combo = self.subtitle_page.preset_combo
        self.drag_toggle_btn = self.subtitle_page.drag_toggle_btn
        self.live_preview_box = self.subtitle_page.live_preview_box
        self.subtitle_page.style_changed.connect(self.settings_coordinator.set_subtitle_style)
        self.subtitle_page.mode_changed.connect(self.settings_coordinator.set_overlay_mode)
        self.subtitle_page.preset_changed.connect(self.settings_coordinator.set_overlay_preset)
        self.subtitle_page.drag_toggle_requested.connect(self.settings_coordinator.toggle_overlay_drag)
        self.page_subtitle = self.subtitle_page

        self.pages.addWidget(self.page_console)
        self.pages.addWidget(self.page_ai)
        self.pages.addWidget(self.page_ocr)
        self.pages.addWidget(self.page_subtitle)

        content_v_layout.addWidget(self.pages, stretch=1)
        main_h_layout.addWidget(content_container, stretch=1)

        # Kết nối sự kiện di chuyển overlay và khôi phục vị trí
        self.overlay = overlay
        if self.overlay:
            if self.state.overlay_preset != "custom":
                self.overlay.apply_preset(self.state.overlay_preset)
            elif self.state.overlay_x is not None and self.state.overlay_y is not None:
                self.overlay.move(self.state.overlay_x, self.state.overlay_y)

        # Đồng bộ ban đầu
        self.console_page.render_summary(self.settings_coordinator.snapshot())
        self.settings_coordinator.settings_changed.connect(self._render_snapshot)
        self.settings_coordinator.save_failed.connect(self._show_save_error)
        self.settings_coordinator.drag_mode_changed.connect(self.subtitle_page.set_drag_mode)

    def _switch_to_page(self, index: int):
        self.pages.setCurrentIndex(index)
        self.sidebar.set_active_page(index)

        titles = [
            ("Tổng quan", "Điều khiển tiến trình quét OCR và theo dõi thông số theo thời gian thực"),
            ("Công cụ dịch", "Chọn Google Translate hoặc cấu hình công cụ AI"),
            ("Dịch thuật & Vùng quét OCR", "Thiết lập ngôn ngữ dịch thuật và khu vực theo dõi màn hình"),
            ("Tùy biến Phụ đề", "Tùy chỉnh phong cách hiển thị và xem trước hộp phụ đề trực tiếp")
        ]
        if 0 <= index < len(titles):
            title, desc = titles[index]
            self.page_title_lbl.setText(title)
            self.page_desc_lbl.setText(desc)


    def _render_snapshot(self, snapshot, changed_field):
        if changed_field not in ('subtitle_style', 'preset', 'overlay_position', 'rollback'):
            self.clear_translation_status()
        if changed_field in ('provider', 'model', 'api_key', 'api_key_import', 'api_key_deleted', 'base_url', 'rollback'):
            self.ai_page.render(snapshot.ai, changed_field=changed_field)
        if changed_field in ('source', 'target', 'interval', 'region', 'rollback'):
            self.ocr_page.render(snapshot.ocr)
        if changed_field in ('subtitle_style', 'preset', 'overlay_position', 'overlay_mode', 'rollback'):
            self.subtitle_page.render(snapshot.subtitle)
        self.console_page.render_summary(snapshot)


    def _show_save_error(self, message):
        self.sidebar.set_status(message, f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 600;")

    def _import_legacy_key(self, persist):
        if not self.settings_coordinator.import_legacy_key(persist):
            return
        if persist and QMessageBox.question(
                self, 'Key cũ trong .env',
                'Đã lưu key bằng mã hóa Windows. Xóa các dòng key của công cụ này khỏi .env cũ? Các biến khác được giữ nguyên.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.settings_coordinator.remove_legacy_key()

    def show_overlay_error(self, error):
        self._show_save_error(error.user_message)
        self.status.setText(error.user_message)
        self.console_page.set_run_status(error.user_message)

    def clear_translation_status(self):
        self.console_page.clear_translation_status()

    def show_translation_status(self, status):
        if (self.worker is None or not self.worker.is_running()
                or status.provider != self.settings_coordinator.snapshot().ai.provider
                or status.revision != self.worker.revision
                or status.session_id != self.worker.translation_session_id):
            return
        self._retry_pending = False
        self.console_page.render_translation_status(status, now_s=time.monotonic())

    def retry_translation(self):
        if self._retry_pending or self.worker is None:
            return False
        self._retry_pending = True
        if not self.worker.retry_translation():
            self._retry_pending = False
            return False
        self.console_page.retry_translation_btn.setEnabled(False)
        return True


    def _on_overlay_position_changed(self, x: int, y: int):
        return self.settings_coordinator.save_overlay_position(x, y)


    def _pick_bg_color(self):
        self.subtitle_page.pick_bg_color()


    def _pick_text_color(self):
        self.subtitle_page.pick_text_color()


    def _toggle_key_visibility(self):
        self.ai_page.toggle_key_visibility()


    def set_preset_display(self, preset: str):
        self.subtitle_page.set_preset_display(preset)


    def start_ocr(self):
        if self.worker is not None and self.worker.is_running() is True:
            return
        ai = self.settings_coordinator.snapshot().ai
        provider = ai.provider
        if ai.requires_api_key and not ai.api_key.strip():
            self.status.setText(f"Lỗi: Thiếu API Key ({provider})")
            self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 600;")
            
            # Chuyển người dùng sang tab AI Engine
            self._switch_to_page(1)
            
            # Cảnh báo viền thẻ API Key
            self.ai_page.highlight_missing_key()
            return

        if self.worker:
            self.worker.start_worker()
        
        self.status.setText("Đang hoạt động")
        self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_green']}; font-size: 11.5px; font-weight: 600;")
        self.console_page.set_run_status("Đang hoạt động")


    def stop_ocr(self):
        self._retry_pending = False
        self.clear_translation_status()
        if self.worker:
            self.worker.stop_worker()
        if self.overlay is not None:
            self.overlay.clear()
        self.status.setText("Đã dừng")
        self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 600;")
        self.console_page.set_run_status("Đã dừng")

    @property
    def overlay(self):
        return self._overlay

    @overlay.setter
    def overlay(self, overlay):
        if overlay is self._overlay:
            return
        if isinstance(self._overlay, QObject):
            self._overlay.position_changed.disconnect(self._on_overlay_position_changed)
        self._overlay = overlay
        self.settings_coordinator.set_overlay(overlay)
        if isinstance(overlay, QObject):
            overlay.position_changed.connect(self._on_overlay_position_changed)

    def apply_region_selection(self, region: dict) -> bool:
        return self.settings_coordinator.apply_region_selection(region)

    def refresh_region(self) -> None:
        snapshot = self.settings_coordinator.snapshot()
        self.ocr_page.render(snapshot.ocr)
        self.console_page.render_summary(snapshot)

    def _on_select_region_clicked(self):
        if callable(self.on_select_region_cb):
            self.on_select_region_cb()
        self.refresh_region()
