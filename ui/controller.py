from ui.pages.subtitle_settings_page import SubtitleSettingsPage
from ui.pages.ocr_settings_page import OcrSettingsPage
from ui.pages.ai_settings_page import AiSettingsPage
from ui.pages.console_page import ConsolePage
from ui.widgets.sidebar import ControllerSidebar
from ui.widgets.cards import ModernCard, MetricCard
from ui.controller_state import AiPageState, OcrPageState, SubtitlePageState, ControllerSnapshot
from ui.presentation import subtitle_preview_style, color_button_presentation, drag_button_style
import os
from typing import Callable
from PyQt5.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QComboBox, QFrame, QSlider, QColorDialog,
    QLineEdit, QScrollArea, QStackedWidget
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QPainterPath

from core.config import (
    SUPPORTED_LANGUAGES, SUPPORTED_TARGETS, load_config, save_config,
    PROVIDERS, DEFAULT_PROVIDER, get_available_providers,
    load_active_provider, save_active_provider,
    load_provider_api_key, save_provider_api_key,
    load_provider_model_id, save_provider_model_id,
    load_region, ConfigError, load_runtime_settings
)
from ui.styles import (
    CYBER_PALETTE, get_app_stylesheet, SIDEBAR_STYLE,
    NAV_BUTTON_NORMAL, NAV_BUTTON_ACTIVE,
    HERO_START_STYLE, HERO_STOP_STYLE, SECONDARY_BUTTON_STYLE,
    CARD_FRAME_STYLE
)
from ui.icons import get_lucide_icon






class ControllerWindow(QWidget):
    """Cửa sổ Dashboard điều khiển chính - Phong cách Linear / Raycast Pro & Lucide Icons"""

    def __init__(self, worker, state, on_select_region, on_quit, overlay=None):
        super().__init__()

        self.worker = worker
        self.state = state
        self.overlay = overlay
        self.on_select_region_cb = on_select_region
        self.on_quit_cb = on_quit

        # ===== Cấu hình Window =====
        # ===== Cấu hình Window =====
        self.setWindowTitle("Translate HUD - Realtime Screen Translator")
        self.resize(740, 560)
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
            ("bot", "Cấu hình AI", "Quản lý Provider, Model và API Key"),
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
        self.page_console = self._create_console_page()
        self.page_ai = self._create_ai_page()
        self.page_ocr = self._create_ocr_page()
        self.page_subtitle = self._create_subtitle_page()

        self.pages.addWidget(self.page_console)
        self.pages.addWidget(self.page_ai)
        self.pages.addWidget(self.page_ocr)
        self.pages.addWidget(self.page_subtitle)

        content_v_layout.addWidget(self.pages, stretch=1)
        main_h_layout.addWidget(content_container, stretch=1)

        # Kết nối sự kiện di chuyển overlay và khôi phục vị trí
        if self.overlay:
            self.overlay.position_changed.connect(self._on_overlay_position_changed)
            if self.state.overlay_preset != "custom":
                self.overlay.apply_preset(self.state.overlay_preset)
            elif self.state.overlay_x is not None and self.state.overlay_y is not None:
                self.overlay.move(self.state.overlay_x, self.state.overlay_y)

        # Đồng bộ ban đầu
        self._update_all_metric_cards()

    # ========================================================
    # NAVIGATION CHUYỂN TRANG
    # ========================================================
    def _switch_to_page(self, index: int):
        self.pages.setCurrentIndex(index)
        self.sidebar.set_active_page(index)

        titles = [
            ("Tổng quan", "Điều khiển tiến trình quét OCR và theo dõi thông số theo thời gian thực"),
            ("Cấu hình AI Engine", "Quản lý nhà cung cấp API, mô hình LLM và khóa bảo mật"),
            ("Dịch thuật & Vùng quét OCR", "Thiết lập ngôn ngữ dịch thuật và khu vực theo dõi màn hình"),
            ("Tùy biến Phụ đề", "Tùy chỉnh phong cách hiển thị và xem trước hộp phụ đề trực tiếp")
        ]
        if 0 <= index < len(titles):
            title, desc = titles[index]
            self.page_title_lbl.setText(title)
            self.page_desc_lbl.setText(desc)

    # ========================================================
    # PAGE 1: CONSOLE (TỔNG QUAN)
    # ========================================================
    def _create_console_page(self):
        self.console_page = ConsolePage(self._snapshot_for_pages(), self)
        self.start_btn = self.console_page.start_btn
        self.stop_btn = self.console_page.stop_btn
        self.metric_cards = self.console_page.metric_cards
        self.console_page.start_requested.connect(self.start_ocr)
        self.console_page.stop_requested.connect(self.stop_ocr)
        self.console_page.select_region_requested.connect(self._on_select_region_clicked)
        self.console_page.subtitle_settings_requested.connect(lambda: self._switch_to_page(3))
        return self.console_page

    # ========================================================
    # PAGE 2: AI ENGINE CONFIG
    # ========================================================
    def _create_ai_page(self):
        self.ai_page = AiSettingsPage(self._snapshot_for_pages().ai, tuple(get_available_providers()), self)
        self.provider_combo = self.ai_page.provider_combo
        self.model_combo = self.ai_page.model_combo
        self.api_key_input = self.ai_page.api_key_input
        self.toggle_key_btn = self.ai_page.toggle_key_btn
        self.api_status_lbl = self.ai_page.api_status_lbl
        self.key_card = self.ai_page.key_card
        self.ai_page.provider_changed.connect(self._on_provider_changed)
        self.ai_page.model_changed.connect(self._on_model_changed)
        self.ai_page.api_key_changed.connect(self._on_api_key_changed)
        return self.ai_page

    # ========================================================
    # PAGE 3: DỊCH THUẬT & VÙNG QUÉT OCR
    # ========================================================
    def _create_ocr_page(self):
        snapshot = self._snapshot_for_pages()
        if self.worker is not None:
            self.worker.setInterval(snapshot.ocr.interval_ms)
        self.ocr_page = OcrSettingsPage(snapshot.ocr, tuple(SUPPORTED_LANGUAGES), tuple(SUPPORTED_TARGETS), self)
        self.src_combo = self.ocr_page.src_combo
        self.tgt_combo = self.ocr_page.tgt_combo
        self.interval_spin = self.ocr_page.interval_spin
        self.reg_info_lbl = self.ocr_page.reg_info_lbl
        self.ocr_page.source_changed.connect(self._on_source_lang_changed)
        self.ocr_page.target_changed.connect(self._on_target_lang_changed)
        self.ocr_page.interval_changed.connect(self._on_interval_changed)
        self.ocr_page.select_region_requested.connect(self._on_select_region_clicked)
        return self.ocr_page

    # ========================================================
    # PAGE 4: TÙY BIẾN PHỤ ĐỀ (SUBTITLE & LIVE PREVIEW)
    # ========================================================
    def _create_subtitle_page(self):
        self.subtitle_page = SubtitleSettingsPage(self._snapshot_for_pages().subtitle, self)
        self.bg_color_btn = self.subtitle_page.bg_color_btn
        self.text_color_btn = self.subtitle_page.text_color_btn
        self.font_size_slider = self.subtitle_page.font_size_slider
        self.font_size_val_lbl = self.subtitle_page.font_size_val_lbl
        self.opacity_slider = self.subtitle_page.opacity_slider
        self.opacity_val_lbl = self.subtitle_page.opacity_val_lbl
        self.preset_combo = self.subtitle_page.preset_combo
        self.drag_toggle_btn = self.subtitle_page.drag_toggle_btn
        self.live_preview_box = self.subtitle_page.live_preview_box
        self.subtitle_page.style_changed.connect(self._on_subtitle_style_changed)
        self.subtitle_page.preset_changed.connect(lambda: self._on_preset_changed(0))
        self.subtitle_page.drag_toggle_requested.connect(self._toggle_drag_mode)
        return self.subtitle_page

    def _on_subtitle_style_changed(self, changes):
        if self._commit_settings(lambda: self.state.update(**changes)):
            self._sync_overlay_style()
            self.subtitle_page.render(self._snapshot_for_pages().subtitle)

    # ========================================================
    # LOGIC XỬ LÝ SỰ KIỆN & CẬP NHẬT
    # ========================================================
    def _configure_worker(self):
        if self.worker is not None:
            self.worker.configure(load_runtime_settings(self.state, load_config()["interval_ms"]))

    def _commit_settings(self, action: Callable[[], None]) -> bool:
        try:
            action()
        except ConfigError:
            self._restore_settings_widgets()
            self.status.setText("Không thể lưu thiết lập. Kiểm tra quyền ghi và dung lượng ổ đĩa.")
            self.status.setStyleSheet(
                f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 600;"
            )
            return False
        return True

    def _restore_settings_widgets(self):
        # Block signals during rollback to avoid another write from a Qt slot.
        provider = load_active_provider()
        controls = (
            (self.src_combo, self.src_combo.setCurrentText, self.state.source),
            (self.tgt_combo, self.tgt_combo.setCurrentText, self.state.target),
            (self.font_size_slider, self.font_size_slider.setValue, self.state.font_size),
            (self.opacity_slider, self.opacity_slider.setValue, self.state.bg_opacity),
            (self.provider_combo, self.provider_combo.setCurrentText, provider),
            (self.api_key_input, self.api_key_input.setText, load_provider_api_key(provider)),
            (self.interval_spin, self.interval_spin.setValue, load_config()["interval_ms"]),
        )
        for control, setter, value in controls:
            blocked = control.blockSignals(True)
            try:
                setter(value)
            finally:
                control.blockSignals(blocked)
        self.api_key_input.setPlaceholderText(PROVIDERS[provider]["placeholder"])
        self._populate_models_for_provider(provider)
        self.set_preset_display(self.state.overlay_preset)
        self.font_size_val_lbl.setText(f"{self.state.font_size}px")
        self.opacity_val_lbl.setText(f"{self.state.bg_opacity}%")
        self._update_color_btn_style(self.bg_color_btn, self.state.bg_color)
        self._update_color_btn_style(self.text_color_btn, self.state.text_color)
        self._update_live_preview_box()
        self._update_api_status()
        self._update_all_metric_cards()

    def _update_live_preview_box(self):
        self.live_preview_box.setStyleSheet(subtitle_preview_style(self._snapshot_for_pages().subtitle))

    def _update_color_btn_style(self, btn, hex_color):
        text, style = color_button_presentation(hex_color)
        btn.setText(text)
        btn.setStyleSheet(style)

    def _pick_bg_color(self):
        self.subtitle_page.pick_bg_color()

    def _pick_text_color(self):
        self.subtitle_page.pick_text_color()

    def _on_opacity_changed(self, val: int):
        if not self._commit_settings(lambda: self.state.update(bg_opacity=val)):
            return
        self.opacity_val_lbl.setText(f"{val}%")
        self._update_live_preview_box()
        self._sync_overlay_style()

    def _on_font_size_changed(self, val: int):
        if not self._commit_settings(lambda: self.state.update(font_size=val)):
            return
        self.font_size_val_lbl.setText(f"{val}px")
        self._update_live_preview_box()
        self._sync_overlay_style()

    def _on_preset_changed(self, index: int):
        preset = self.preset_combo.currentData()
        if preset:
            if not self._commit_settings(lambda: self.state.update(overlay_preset=preset)):
                return
            if self.overlay and preset != "custom":
                self.overlay.apply_preset(preset)

    def _toggle_drag_mode(self):
        if not self.overlay:
            return
        new_state = not self.overlay.is_drag_mode
        self.overlay.set_drag_mode(new_state)
        self._update_drag_btn_style(new_state)

    def _update_drag_btn_style(self, is_active):
        self.drag_toggle_btn.setText("✓ Đã xong (Khóa vị trí phụ đề)" if is_active else "✥ Di chuyển phụ đề trên màn hình")
        self.drag_toggle_btn.setStyleSheet(drag_button_style(is_active))

    def set_preset_display(self, preset: str):
        idx = self.preset_combo.findData(preset)
        if idx >= 0:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(idx)
            self.preset_combo.blockSignals(False)

    def _on_overlay_position_changed(self, x: int, y: int):
        if not self._commit_settings(
            lambda: self.state.update(overlay_x=x, overlay_y=y, overlay_preset="custom")
        ):
            if self.overlay:
                if (self.state.overlay_preset == "custom"
                        and self.state.overlay_x is not None and self.state.overlay_y is not None):
                    self.overlay.move(self.state.overlay_x, self.state.overlay_y)
                    self.overlay.current_preset = "custom"
                else:
                    self.overlay.apply_preset(self.state.overlay_preset)
            return
        self.set_preset_display("custom")

    def _sync_overlay_style(self):
        if self.overlay:
            self.overlay.apply_style(
                bg_hex=self.state.bg_color,
                opacity_pct=self.state.bg_opacity,
                text_hex=self.state.text_color,
                font_size=self.state.font_size
            )

    def _populate_models_for_provider(self, provider):
        self.ai_page.render(self._snapshot_for_pages().ai, changed_field="provider")

    def _on_provider_changed(self, provider: str):
        if provider not in PROVIDERS:
            return
        if not self._commit_settings(lambda: save_active_provider(provider)):
            return
        self.api_key_input.blockSignals(True)
        self.api_key_input.setText(load_provider_api_key(provider))
        self.api_key_input.setPlaceholderText(PROVIDERS[provider]["placeholder"])
        self.api_key_input.blockSignals(False)
        self._populate_models_for_provider(provider)
        self._update_api_status()
        self._update_all_metric_cards()
        self._configure_worker()

    def _on_api_key_changed(self, text: str = ""):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        key = self.api_key_input.text().strip()
        if not self._commit_settings(lambda: save_provider_api_key(provider, key)):
            return
        self._configure_worker()
        self._update_api_status()
        self._update_all_metric_cards()

    def _on_model_changed(self, model: str):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        if model.strip():
            if not self._commit_settings(lambda: save_provider_model_id(provider, model.strip())):
                return
            self._configure_worker()
            self._update_all_metric_cards()

    def _toggle_key_visibility(self):
        self.ai_page.toggle_key_visibility()

    def _update_api_status(self):
        self.ai_page.render(self._snapshot_for_pages().ai, changed_field="api_key")

    def _on_source_lang_changed(self, lang: str):
        if not self._commit_settings(lambda: self.state.update(source=lang)):
            return
        self._configure_worker()
        self._update_all_metric_cards()

    def _on_target_lang_changed(self, lang: str):
        if not self._commit_settings(lambda: self.state.update(target=lang)):
            return
        self._configure_worker()
        self._update_all_metric_cards()

    def _on_interval_changed(self, val: int):
        if not self._commit_settings(lambda: save_config("interval_ms", val)):
            return
        self._configure_worker()

    def _update_region_info_lbl(self):
        self.ocr_page.render(self._snapshot_for_pages().ocr)

    def _on_select_region_clicked(self):
        if callable(self.on_select_region_cb):
            self.on_select_region_cb()
        self._update_region_info_lbl()
        self._update_all_metric_cards()

    def _update_all_metric_cards(self):
        self.console_page.render_summary(self._snapshot_for_pages())

    def start_ocr(self):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        if not load_provider_api_key(provider).strip():
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
        if "status" in self.metric_cards:
            self.metric_cards["status"].set_value("Đang hoạt động")

    def stop_ocr(self):
        if self.worker:
            self.worker.stop_worker()
        self.status.setText("Đã dừng")
        self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 600;")
        if "status" in self.metric_cards:
            self.metric_cards["status"].set_value("Đã dừng")

    def _snapshot_for_pages(self) -> ControllerSnapshot:
        provider = load_active_provider()
        model = load_provider_model_id(provider)
        models = tuple(PROVIDERS[provider]['models'])
        if model not in models:
            models += (model,)
        region = load_region()
        return ControllerSnapshot(
            AiPageState(provider, model, models, load_provider_api_key(provider), PROVIDERS[provider]['placeholder']),
            OcrPageState(self.state.source, self.state.target, load_config()['interval_ms'],
                         tuple(region[key] for key in ('left', 'top', 'width', 'height')) if region else None),
            SubtitlePageState(self.state.bg_color, self.state.text_color, self.state.bg_opacity,
                              self.state.font_size, self.state.overlay_preset, self.state.overlay_x, self.state.overlay_y))
