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
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebarFrame")
        self.sidebar_frame.setStyleSheet(SIDEBAR_STYLE)
        self.sidebar_frame.setFixedWidth(205)

        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(14, 16, 14, 16)
        sidebar_layout.setSpacing(6)

        # Brand Header với Logo mới
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        
        brand_icon_lbl = QLabel()
        if os.path.exists(logo_path):
            size = 28
            radius = 6
            src = QPixmap(logo_path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            rounded_pix = QPixmap(size, size)
            rounded_pix.fill(Qt.transparent)
            painter = QPainter(rounded_pix)
            painter.setRenderHint(QPainter.Antialiasing)
            clip_path = QPainterPath()
            clip_path.addRoundedRect(0, 0, size, size, radius, radius)
            painter.setClipPath(clip_path)
            painter.drawPixmap(0, 0, src)
            painter.end()
            brand_icon_lbl.setPixmap(rounded_pix)
        else:
            zap_icon = get_lucide_icon("zap", color=CYBER_PALETTE['neon_indigo'], size=20)
            brand_icon_lbl.setPixmap(zap_icon.pixmap(20, 20))
        brand_row.addWidget(brand_icon_lbl)

        brand_text_box = QVBoxLayout()
        brand_text_box.setSpacing(1)
        brand_title = QLabel("Translate HUD")
        brand_title.setStyleSheet("font-size: 13.5px; font-weight: 700; letter-spacing: 0.2px;")
        brand_sub = QLabel("Realtime Screen OCR")
        brand_sub.setStyleSheet(f"font-size: 10.5px; color: {CYBER_PALETTE['text_muted']};")
        brand_text_box.addWidget(brand_title)
        brand_text_box.addWidget(brand_sub)
        brand_row.addLayout(brand_text_box)
        sidebar_layout.addLayout(brand_row)

        sidebar_layout.addSpacing(14)

        # Navigation Buttons (Lucide Vector Icons, Không Emoji)
        self.nav_buttons = []
        self.nav_item_defs = [
            ("layout-dashboard", "Tổng quan", "Bảng điều khiển nhanh và trạng thái"),
            ("bot", "Cấu hình AI", "Quản lý Provider, Model và API Key"),
            ("languages", "Dịch thuật & OCR", "Ngôn ngữ nguồn, ngôn ngữ dịch và tần suất quét"),
            ("palette", "Giao diện Phụ đề", "Màu sắc, độ trong suốt và xem trước trực tiếp")
        ]

        for idx, (icon_name, label_text, tooltip_text) in enumerate(self.nav_item_defs):
            btn = QPushButton(f"  {label_text}")
            btn.setToolTip(tooltip_text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setIconSize(QSize(17, 17))
            
            icon_col = "#ffffff" if idx == 0 else CYBER_PALETTE['text_muted']
            btn.setIcon(get_lucide_icon(icon_name, color=icon_col, size=17))
            btn.setStyleSheet(NAV_BUTTON_ACTIVE if idx == 0 else NAV_BUTTON_NORMAL)
            btn.clicked.connect(lambda checked, i=idx: self._switch_to_page(i))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Sidebar Footer: Live Status indicator & Quit
        status_box = QFrame()
        status_box.setStyleSheet(f"""
            QFrame {{
                background-color: {CYBER_PALETTE['bg_main']};
                border: 1px solid {CYBER_PALETTE['border']};
                border-radius: 7px;
                padding: 6px;
            }}
        """)
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(8, 6, 8, 6)
        status_layout.setSpacing(3)

        sys_status_lbl = QLabel("TRẠNG THÁI HỆ THỐNG")
        sys_status_lbl.setStyleSheet(f"font-size: 9.5px; font-weight: 600; color: {CYBER_PALETTE['text_dim']};")
        status_layout.addWidget(sys_status_lbl)

        self.status = QLabel("Đã dừng")
        self.status.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['neon_rose']};")
        status_layout.addWidget(self.status)
        sidebar_layout.addWidget(status_box)

        sidebar_layout.addSpacing(4)

        quit_btn = QPushButton("  Thoát")
        quit_btn.setFixedHeight(32)
        quit_btn.setIcon(get_lucide_icon("log-out", color=CYBER_PALETTE['text_muted'], size=14))
        quit_btn.setIconSize(QSize(14, 14))
        quit_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.clicked.connect(self.on_quit_cb)
        sidebar_layout.addWidget(quit_btn)

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
        for i, btn in enumerate(self.nav_buttons):
            is_active = (i == index)
            btn.setStyleSheet(NAV_BUTTON_ACTIVE if is_active else NAV_BUTTON_NORMAL)
            icon_name = self.nav_item_defs[i][0]
            icon_col = "#ffffff" if is_active else CYBER_PALETTE['text_muted']
            btn.setIcon(get_lucide_icon(icon_name, color=icon_col, size=17))

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
    def _create_console_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(14)

        # Hero Action Card (Nút START & STOP chuẩn Lucide Icons)
        hero_card = ModernCard("Thao tác Điều khiển", "Khởi động hoặc dừng tiến trình quét và dịch màn hình")
        hero_row = QHBoxLayout()
        hero_row.setSpacing(12)

        self.start_btn = QPushButton("  Bắt đầu (Start)")
        self.start_btn.setFixedHeight(40)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setIcon(get_lucide_icon("play", color="#ffffff", size=15))
        self.start_btn.setIconSize(QSize(15, 15))
        self.start_btn.setStyleSheet(HERO_START_STYLE)
        self.start_btn.clicked.connect(self.start_ocr)

        self.stop_btn = QPushButton("  Dừng (Stop)")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setIcon(get_lucide_icon("square", color="#ffffff", size=14))
        self.stop_btn.setIconSize(QSize(14, 14))
        self.stop_btn.setStyleSheet(HERO_STOP_STYLE)
        self.stop_btn.clicked.connect(self.stop_ocr)

        hero_row.addWidget(self.start_btn)
        hero_row.addWidget(self.stop_btn)
        hero_card.layout.addLayout(hero_row)
        layout.addWidget(hero_card)

        # Status Metrics Grid (4 thẻ tóm tắt với Lucide Icons)
        metrics_card = ModernCard("Chỉ số Trực tiếp", "Tóm tắt cấu hình đang hoạt động")
        grid_row1 = QHBoxLayout()
        grid_row1.setSpacing(10)
        grid_row2 = QHBoxLayout()
        grid_row2.setSpacing(10)

        card_status = MetricCard("TRẠNG THÁI", "Đã dừng", icon_name="activity", icon_color=CYBER_PALETTE['neon_rose'])
        card_ai = MetricCard("AI MODEL", f"{load_active_provider()}", icon_name="cpu", icon_color=CYBER_PALETTE['neon_indigo'])
        card_lang = MetricCard("NGÔN NGỮ", f"{self.state.source} -> {self.state.target}", icon_name="languages", icon_color=CYBER_PALETTE['text_muted'])
        
        reg = load_region()
        reg_txt = f"{reg.get('width', 0)} x {reg.get('height', 0)} px" if reg else "Chưa chọn vùng"
        card_reg = MetricCard("VÙNG QUÉT OCR", reg_txt, icon_name="maximize-2", icon_color=CYBER_PALETTE['text_muted'])

        self.metric_cards["status"] = card_status
        self.metric_cards["ai"] = card_ai
        self.metric_cards["lang"] = card_lang
        self.metric_cards["region"] = card_reg

        grid_row1.addWidget(card_status)
        grid_row1.addWidget(card_ai)
        grid_row2.addWidget(card_lang)
        grid_row2.addWidget(card_reg)

        metrics_card.layout.addLayout(grid_row1)
        metrics_card.layout.addLayout(grid_row2)
        layout.addWidget(metrics_card)

        # Quick Actions Card
        quick_card = ModernCard("Thao tác Nhanh")
        q_row = QHBoxLayout()
        q_row.setSpacing(10)

        quick_select_btn = QPushButton("  Chọn lại vùng quét")
        quick_select_btn.setFixedHeight(32)
        quick_select_btn.setIcon(get_lucide_icon("scan", color=CYBER_PALETTE['text_muted'], size=14))
        quick_select_btn.setIconSize(QSize(14, 14))
        quick_select_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        quick_select_btn.setCursor(Qt.PointingHandCursor)
        quick_select_btn.clicked.connect(self._on_select_region_clicked)
        q_row.addWidget(quick_select_btn)

        quick_sub_btn = QPushButton("  Chỉnh phụ đề")
        quick_sub_btn.setFixedHeight(32)
        quick_sub_btn.setIcon(get_lucide_icon("sliders", color=CYBER_PALETTE['text_muted'], size=14))
        quick_sub_btn.setIconSize(QSize(14, 14))
        quick_sub_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        quick_sub_btn.setCursor(Qt.PointingHandCursor)
        quick_sub_btn.clicked.connect(lambda: self._switch_to_page(3))
        q_row.addWidget(quick_sub_btn)

        quick_card.layout.addLayout(q_row)
        layout.addWidget(quick_card)

        layout.addStretch()
        return widget

    # ========================================================
    # PAGE 2: AI ENGINE CONFIG
    # ========================================================
    def _create_ai_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(14)

        active_provider = load_active_provider()

        # Card 1: Provider & Model Selector
        prov_card = ModernCard("Nhà cung cấp & Mô hình AI", "Chọn Provider và Model thực hiện tác vụ dịch thuật")
        
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Provider col
        p_col = QVBoxLayout()
        p_col.setSpacing(4)
        p_lbl = QLabel("AI Provider")
        p_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(get_available_providers())
        self.provider_combo.setCurrentText(active_provider)
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        p_col.addWidget(p_lbl)
        p_col.addWidget(self.provider_combo)
        row1.addLayout(p_col)

        # Model col
        m_col = QVBoxLayout()
        m_col.setSpacing(4)
        m_lbl = QLabel("Mô hình (Model ID)")
        m_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self._populate_models_for_provider(active_provider)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        m_col.addWidget(m_lbl)
        m_col.addWidget(self.model_combo)
        row1.addLayout(m_col)

        prov_card.layout.addLayout(row1)
        layout.addWidget(prov_card)

        # Card 2: API Key Management
        self.key_card = ModernCard("Khóa API (API Key)", "Khóa được lưu cục bộ an toàn trong file .env")
        
        k_layout = QVBoxLayout()
        k_layout.setSpacing(6)
        
        k_input_row = QHBoxLayout()
        k_input_row.setSpacing(8)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText(PROVIDERS[active_provider]["placeholder"])
        self.api_key_input.setText(load_provider_api_key(active_provider))
        self.api_key_input.textChanged.connect(self._on_api_key_changed)
        k_input_row.addWidget(self.api_key_input)

        self.toggle_key_btn = QPushButton()
        self.toggle_key_btn.setFixedSize(36, 32)
        self.toggle_key_btn.setToolTip("Hiện / Ẩn API Key")
        self.toggle_key_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_key_btn.setIcon(get_lucide_icon("eye", color=CYBER_PALETTE['text_muted'], size=16))
        self.toggle_key_btn.setIconSize(QSize(16, 16))
        self.toggle_key_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.toggle_key_btn.clicked.connect(self._toggle_key_visibility)
        k_input_row.addWidget(self.toggle_key_btn)

        k_layout.addLayout(k_input_row)

        self.api_status_lbl = QLabel()
        self._update_api_status()
        k_layout.addWidget(self.api_status_lbl)

        self.key_card.layout.addLayout(k_layout)
        layout.addWidget(self.key_card)

        # Card 3: Guide Note
        note_card = ModernCard("Hướng dẫn lấy API Key")
        note_text = QLabel(
            "• Google Gemini: Truy cập Google AI Studio (aistudio.google.com)\n"
            "• OpenAI: Truy cập platform.openai.com/api-keys\n"
            "• OpenRouter: Truy cập openrouter.ai/keys để nhận key dùng nhiều model"
        )
        note_text.setStyleSheet(f"color: {CYBER_PALETTE['text_muted']}; font-size: 12px; line-height: 1.5;")
        note_card.layout.addWidget(note_text)
        layout.addWidget(note_card)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ========================================================
    # PAGE 3: DỊCH THUẬT & VÙNG QUÉT OCR
    # ========================================================
    def _create_ocr_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(14)

        # Card 1: Language selection
        lang_card = ModernCard("Ngôn ngữ Dịch thuật", "Lựa chọn ngôn ngữ nguồn hiển thị trong game và ngôn ngữ dịch sang")
        lang_row = QHBoxLayout()
        lang_row.setSpacing(12)

        src_col = QVBoxLayout()
        src_col.setSpacing(4)
        src_lbl = QLabel("Ngôn ngữ nguồn (Source)")
        src_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.src_combo = QComboBox()
        self.src_combo.addItems(list(SUPPORTED_LANGUAGES.keys()))
        self.src_combo.setCurrentText(self.state.source if self.state.source in SUPPORTED_LANGUAGES else "English")
        self.src_combo.currentTextChanged.connect(self._on_source_lang_changed)
        src_col.addWidget(src_lbl)
        src_col.addWidget(self.src_combo)
        lang_row.addLayout(src_col)

        arrow_lbl = QLabel("->")
        arrow_lbl.setAlignment(Qt.AlignCenter)
        arrow_lbl.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {CYBER_PALETTE['neon_indigo']}; margin-top: 18px;")
        lang_row.addWidget(arrow_lbl)

        tgt_col = QVBoxLayout()
        tgt_col.setSpacing(4)
        tgt_lbl = QLabel("Ngôn ngữ dịch (Target)")
        tgt_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.tgt_combo = QComboBox()
        self.tgt_combo.addItems(SUPPORTED_TARGETS)
        self.tgt_combo.setCurrentText(self.state.target if self.state.target in SUPPORTED_TARGETS else "Vietnamese")
        self.tgt_combo.currentTextChanged.connect(self._on_target_lang_changed)
        tgt_col.addWidget(tgt_lbl)
        tgt_col.addWidget(self.tgt_combo)
        lang_row.addLayout(tgt_col)

        lang_card.layout.addLayout(lang_row)
        layout.addWidget(lang_card)

        # Card 2: OCR Timing & Interval
        ocr_timing_card = ModernCard("Tần suất quét OCR (Interval)", "Thời gian chờ giữa mỗi lần chụp màn hình nhận diện chữ")
        timing_row = QHBoxLayout()
        timing_row.setSpacing(12)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 3000)
        self.interval_spin.setSingleStep(50)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setFixedWidth(130)

        saved_interval = load_config().get("interval_ms", 500)
        if self.worker is not None:
            saved_interval = load_config().get("interval_ms", self.worker.interval())
            self.worker.setInterval(saved_interval)
        self.interval_spin.setValue(saved_interval)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)

        timing_row.addWidget(self.interval_spin)

        timing_info = QLabel("Khuyến nghị: 500ms cho đối thoại game thông thường, 300ms cho game nhịp độ nhanh")
        timing_info.setStyleSheet(f"color: {CYBER_PALETTE['text_muted']}; font-size: 11.5px;")
        timing_info.setWordWrap(True)
        timing_row.addWidget(timing_info, stretch=1)

        ocr_timing_card.layout.addLayout(timing_row)
        layout.addWidget(ocr_timing_card)

        # Card 3: Region Inspector
        reg_card = ModernCard("Vùng màn hình theo dõi", "Tọa độ và kích thước khung hình camera OCR quét phụ đề")
        
        self.reg_info_lbl = QLabel()
        self._update_region_info_lbl()
        reg_card.layout.addWidget(self.reg_info_lbl)

        reg_btn = QPushButton("  Chọn lại vùng quét (Kéo chuột)")
        reg_btn.setFixedHeight(34)
        reg_btn.setIcon(get_lucide_icon("scan", color=CYBER_PALETTE['text_muted'], size=15))
        reg_btn.setIconSize(QSize(15, 15))
        reg_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        reg_btn.setCursor(Qt.PointingHandCursor)
        reg_btn.clicked.connect(self._on_select_region_clicked)
        reg_card.layout.addWidget(reg_btn)

        layout.addWidget(reg_card)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ========================================================
    # PAGE 4: TÙY BIẾN PHỤ ĐỀ (SUBTITLE & LIVE PREVIEW)
    # ========================================================
    def _create_subtitle_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(14)

        # Card 1: Colors & Typography
        style_card = ModernCard("Màu sắc & Kích thước Chữ", "Tùy biến diện mạo hộp phụ đề nổi trên game")
        
        color_row = QHBoxLayout()
        color_row.setSpacing(12)

        # BG Color Picker
        bg_col = QVBoxLayout()
        bg_col.setSpacing(4)
        bg_lbl = QLabel("Màu nền (Background)")
        bg_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setFixedHeight(34)
        self.bg_color_btn.setCursor(Qt.PointingHandCursor)
        self._update_color_btn_style(self.bg_color_btn, self.state.bg_color)
        self.bg_color_btn.clicked.connect(self._pick_bg_color)
        bg_col.addWidget(bg_lbl)
        bg_col.addWidget(self.bg_color_btn)
        color_row.addLayout(bg_col)

        # Text Color Picker
        txt_col = QVBoxLayout()
        txt_col.setSpacing(4)
        txt_lbl = QLabel("Màu chữ (Text)")
        txt_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.text_color_btn = QPushButton()
        self.text_color_btn.setFixedHeight(34)
        self.text_color_btn.setCursor(Qt.PointingHandCursor)
        self._update_color_btn_style(self.text_color_btn, self.state.text_color)
        self.text_color_btn.clicked.connect(self._pick_text_color)
        txt_col.addWidget(txt_lbl)
        txt_col.addWidget(self.text_color_btn)
        color_row.addLayout(txt_col)

        style_card.layout.addLayout(color_row)
        style_card.layout.addSpacing(6)

        # Font Size Slider
        font_header = QHBoxLayout()
        font_lbl = QLabel("Cỡ chữ phụ đề (Font Size)")
        font_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.font_size_val_lbl = QLabel(f"{self.state.font_size}px")
        self.font_size_val_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {CYBER_PALETTE['neon_indigo']};")
        font_header.addWidget(font_lbl)
        font_header.addStretch()
        font_header.addWidget(self.font_size_val_lbl)
        style_card.layout.addLayout(font_header)

        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(14, 36)
        self.font_size_slider.setValue(self.state.font_size)
        self.font_size_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 5px;
                background: {CYBER_PALETTE['bg_input']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {CYBER_PALETTE['neon_indigo']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {CYBER_PALETTE['text_primary']};
                border: 1px solid {CYBER_PALETTE['neon_indigo']};
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }}
        """)
        self.font_size_slider.valueChanged.connect(self._on_font_size_changed)
        style_card.layout.addWidget(self.font_size_slider)
        style_card.layout.addSpacing(6)

        # Opacity Slider
        opacity_header = QHBoxLayout()
        op_lbl = QLabel("Độ trong suốt nền (Background Opacity)")
        op_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.opacity_val_lbl = QLabel(f"{self.state.bg_opacity}%")
        self.opacity_val_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {CYBER_PALETTE['neon_indigo']};")
        opacity_header.addWidget(op_lbl)
        opacity_header.addStretch()
        opacity_header.addWidget(self.opacity_val_lbl)
        style_card.layout.addLayout(opacity_header)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(self.state.bg_opacity)
        self.opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 5px;
                background: {CYBER_PALETTE['bg_input']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {CYBER_PALETTE['neon_indigo']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {CYBER_PALETTE['text_primary']};
                border: 1px solid {CYBER_PALETTE['neon_indigo']};
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }}
        """)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        style_card.layout.addWidget(self.opacity_slider)

        layout.addWidget(style_card)

        # Card 2: Position & Drag Mode
        pos_card = ModernCard("Vị trí & Định vị Màn hình", "Chọn vị trí xuất hiện cố định hoặc tự do kéo thả phụ đề")
        
        pos_row = QHBoxLayout()
        pos_row.setSpacing(12)

        # Preset Dropdown
        preset_box = QVBoxLayout()
        preset_box.setSpacing(4)
        preset_lbl = QLabel("Vị trí hiển thị (Preset)")
        preset_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.preset_combo = QComboBox()
        self.preset_combo.setFixedHeight(34)
        self.preset_combo.addItem("Dưới giữa (Mặc định)", "bottom_center")
        self.preset_combo.addItem("Trên giữa (Top Center)", "top_center")
        self.preset_combo.addItem("Dưới trái (Bottom Left)", "bottom_left")
        self.preset_combo.addItem("Vị trí tùy chọn (Custom)", "custom")

        idx = self.preset_combo.findData(self.state.overlay_preset)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)

        preset_box.addWidget(preset_lbl)
        preset_box.addWidget(self.preset_combo)
        pos_row.addLayout(preset_box)

        pos_card.layout.addLayout(pos_row)
        pos_card.layout.addSpacing(8)

        # Drag Mode Action Button
        self.drag_toggle_btn = QPushButton()
        self.drag_toggle_btn.setCursor(Qt.PointingHandCursor)
        self._update_drag_btn_style(False)
        self.drag_toggle_btn.clicked.connect(self._toggle_drag_mode)
        pos_card.layout.addWidget(self.drag_toggle_btn)

        layout.addWidget(pos_card)

        # Card 3: LIVE PREVIEW BOX
        preview_card = ModernCard("Xem trước Thời gian thực", "Mô phỏng chính xác khung phụ đề nổi hiển thị trên màn hình game")
        
        sim_container = QFrame()
        sim_container.setStyleSheet(f"""
            QFrame {{
                background-color: #08090b;
                border: 1px dashed {CYBER_PALETTE['border_card']};
                border-radius: 8px;
                min-height: 120px;
            }}
        """)
        sim_layout = QVBoxLayout(sim_container)
        sim_layout.setAlignment(Qt.AlignCenter)
        sim_layout.setContentsMargins(16, 20, 16, 20)

        # Hộp phụ đề mẫu
        self.live_preview_box = QLabel("Đây là đoạn phụ đề xem trước thời gian thực...")
        self.live_preview_box.setAlignment(Qt.AlignCenter)
        self.live_preview_box.setWordWrap(True)
        self._update_live_preview_box()

        sim_layout.addWidget(self.live_preview_box)
        preview_card.layout.addWidget(sim_container)

        layout.addWidget(preview_card)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

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
        col = QColorDialog.getColor(QColor(self.state.bg_color), self, "Chọn màu nền phụ đề")
        if col.isValid():
            hex_str = col.name()
            if not self._commit_settings(lambda: self.state.update(bg_color=hex_str)):
                return
            self._update_color_btn_style(self.bg_color_btn, hex_str)
            self._update_live_preview_box()
            self._sync_overlay_style()

    def _pick_text_color(self):
        col = QColorDialog.getColor(QColor(self.state.text_color), self, "Chọn màu chữ phụ đề")
        if col.isValid():
            hex_str = col.name()
            if not self._commit_settings(lambda: self.state.update(text_color=hex_str)):
                return
            self._update_color_btn_style(self.text_color_btn, hex_str)
            self._update_live_preview_box()
            self._sync_overlay_style()

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

    def _populate_models_for_provider(self, provider: str):
        cfg = PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])
        saved_model = load_provider_model_id(provider)
        models = list(cfg["models"])
        if saved_model not in models:
            models.append(saved_model)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(models)
        self.model_combo.setCurrentText(saved_model)
        self.model_combo.blockSignals(False)

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
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_key_btn.setIcon(get_lucide_icon("eye-off", color=CYBER_PALETTE['neon_indigo'], size=16))
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.toggle_key_btn.setIcon(get_lucide_icon("eye", color=CYBER_PALETTE['text_muted'], size=16))

    def _update_api_status(self):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        if load_provider_api_key(provider).strip():
            self.api_status_lbl.setText(f"Trạng thái: {provider} sẵn sàng (.env)")
            self.api_status_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_green']}; font-size: 11.5px; font-weight: 500;")
        else:
            self.api_status_lbl.setText(f"Trạng thái: Chưa có API Key cho {provider}")
            self.api_status_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_amber']}; font-size: 11.5px; font-weight: 500;")

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
        reg = load_region()
        if reg:
            self.reg_info_lbl.setText(
                f"Tọa độ: X={reg.get('left', 0)}, Y={reg.get('top', 0)} | "
                f"Kích thước: {reg.get('width', 0)} x {reg.get('height', 0)} px"
            )
            self.reg_info_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_green']}; font-size: 12px; font-weight: 500;")
        else:
            self.reg_info_lbl.setText("Chưa chọn vùng quét màn hình. Bấm nút bên dưới để chọn.")
            self.reg_info_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_amber']}; font-size: 12px; font-weight: 500;")

    def _on_select_region_clicked(self):
        if callable(self.on_select_region_cb):
            self.on_select_region_cb()
        self._update_region_info_lbl()
        self._update_all_metric_cards()

    def _update_all_metric_cards(self):
        if not hasattr(self, "metric_cards") or not self.metric_cards:
            return
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        model = self.model_combo.currentText() if hasattr(self, "model_combo") else load_provider_model_id(provider)
        
        self.metric_cards["ai"].set_value(f"{provider}\n{model}")
        self.metric_cards["lang"].set_value(f"{self.state.source} -> {self.state.target}")
        
        reg = load_region()
        reg_txt = f"{reg.get('width', 0)} x {reg.get('height', 0)} px" if reg else "Chưa chọn vùng"
        self.metric_cards["region"].set_value(reg_txt)

    def start_ocr(self):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        if not load_provider_api_key(provider).strip():
            self.status.setText(f"Lỗi: Thiếu API Key ({provider})")
            self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 600;")
            
            # Chuyển người dùng sang tab AI Engine
            self._switch_to_page(1)
            
            # Cảnh báo viền thẻ API Key
            self.key_card.setStyleSheet(f"""
                QFrame#cardFrame {{
                    background-color: {CYBER_PALETTE['bg_card']};
                    border: 1px solid {CYBER_PALETTE['neon_rose']};
                    border-radius: 8px;
                }}
            """)
            QTimer.singleShot(2500, lambda: self.key_card.setStyleSheet(CARD_FRAME_STYLE))
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
