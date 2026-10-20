from PyQt5.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QComboBox, QFrame, QSlider, QColorDialog,
    QLineEdit, QScrollArea, QStackedWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont

from core.config import (
    SUPPORTED_LANGUAGES, SUPPORTED_TARGETS, load_config, save_config,
    PROVIDERS, DEFAULT_PROVIDER, get_available_providers,
    load_active_provider, save_active_provider,
    load_provider_api_key, save_provider_api_key,
    load_provider_model_id, save_provider_model_id,
    load_region
)
from engines.translator import reload_client
from ui.styles import (
    CYBER_PALETTE, get_app_stylesheet, SIDEBAR_STYLE,
    NAV_BUTTON_NORMAL, NAV_BUTTON_ACTIVE,
    HERO_START_STYLE, HERO_STOP_STYLE, SECONDARY_BUTTON_STYLE,
    CARD_FRAME_STYLE
)


class ModernCard(QFrame):
    """Thẻ container nội dung phong cách Cyber Card"""
    def __init__(self, title: str = "", subtitle: str = ""):
        super().__init__()
        self.setObjectName("cardFrame")
        self.setStyleSheet(CARD_FRAME_STYLE)
        
        self.box_layout = QVBoxLayout(self)
        self.box_layout.setContentsMargins(16, 14, 16, 16)
        self.box_layout.setSpacing(10)
        
        if title:
            header_layout = QVBoxLayout()
            header_layout.setSpacing(2)
            
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(f"""
                font-size: 13.5px;
                font-weight: 700;
                color: {CYBER_PALETTE['text_primary']};
            """)
            header_layout.addWidget(t_lbl)
            
            if subtitle:
                sub_lbl = QLabel(subtitle)
                sub_lbl.setStyleSheet(f"""
                    font-size: 11.5px;
                    color: {CYBER_PALETTE['text_muted']};
                """)
                header_layout.addWidget(sub_lbl)
                
            self.box_layout.addLayout(header_layout)

    @property
    def layout(self):
        return self.box_layout


class MetricCard(QFrame):
    """Thẻ tóm tắt thông số nhỏ trong Console"""
    def __init__(self, title: str, value: str = "--", icon: str = "⚡"):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {CYBER_PALETTE['bg_input']};
                border: 1px solid {CYBER_PALETTE['border']};
                border-radius: 8px;
                padding: 4px;
            }}
            QFrame:hover {{
                border: 1px solid {CYBER_PALETTE['border_light']};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        
        header_row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 14px;")
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
        header_row.addWidget(icon_lbl)
        header_row.addWidget(t_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)
        
        self.val_lbl = QLabel(value)
        self.val_lbl.setStyleSheet(f"""
            font-size: 12.5px;
            font-weight: 700;
            color: {CYBER_PALETTE['text_primary']};
        """)
        self.val_lbl.setWordWrap(True)
        layout.addWidget(self.val_lbl)
        
    def set_value(self, val: str):
        self.val_lbl.setText(val)


class ControllerWindow(QWidget):
    """Cửa sổ Dashboard điều khiển chính - Phong cách Modern Cyber Dark Split View"""

    def __init__(self, worker, state, on_select_region, on_quit, overlay=None):
        super().__init__()

        self.worker = worker
        self.state = state
        self.overlay = overlay
        self.on_select_region_cb = on_select_region
        self.on_quit_cb = on_quit

        # ===== Cấu hình Window =====
        self.setWindowTitle("Game Translator - Cyber HUD Dashboard")
        self.resize(740, 560)
        self.setMinimumSize(660, 480)
        self.setStyleSheet(get_app_stylesheet())

        # Layout chính dạng ngang: [Sidebar 200px] + [Main Content Stack]
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
        sidebar_layout.setSpacing(8)

        # Brand / Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        brand_icon = QLabel("⚡")
        brand_icon.setStyleSheet(f"font-size: 22px; color: {CYBER_PALETTE['neon_green']};")
        brand_row.addWidget(brand_icon)

        brand_text_box = QVBoxLayout()
        brand_text_box.setSpacing(1)
        brand_title = QLabel("TRANSLATE HUD")
        brand_title.setStyleSheet("font-size: 13.5px; font-weight: 800; letter-spacing: 0.5px;")
        brand_sub = QLabel("Realtime Screen OCR")
        brand_sub.setStyleSheet(f"font-size: 10.5px; color: {CYBER_PALETTE['text_muted']};")
        brand_text_box.addWidget(brand_title)
        brand_text_box.addWidget(brand_sub)
        brand_row.addLayout(brand_text_box)
        sidebar_layout.addLayout(brand_row)

        sidebar_layout.addSpacing(14)

        # Navigation Buttons
        self.nav_buttons = []
        nav_items = [
            ("🕹️  Tổng quan", "Bảng điều khiển nhanh & trạng thái"),
            ("🤖  AI Engine", "Cấu hình Provider, Model & API Key"),
            ("🌐  Dịch & OCR", "Ngôn ngữ nguồn/đích & tần suất quét"),
            ("🎨  Giao diện Phụ đề", "Màu sắc, độ mờ & xem trước trực tiếp")
        ]

        for idx, (label_text, tooltip_text) in enumerate(nav_items):
            btn = QPushButton(label_text)
            btn.setToolTip(tooltip_text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(38)
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
                border-radius: 8px;
                padding: 6px;
            }}
        """)
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(8, 6, 8, 6)
        status_layout.setSpacing(2)

        sys_status_lbl = QLabel("TRẠNG THÁI HỆ THỐNG")
        sys_status_lbl.setStyleSheet(f"font-size: 9.5px; font-weight: 700; color: {CYBER_PALETTE['text_dim']};")
        status_layout.addWidget(sys_status_lbl)

        self.status = QLabel("● Đã dừng (Stopped)")
        self.status.setStyleSheet(f"font-size: 11.5px; font-weight: 700; color: {CYBER_PALETTE['neon_rose']};")
        status_layout.addWidget(self.status)
        sidebar_layout.addWidget(status_box)

        sidebar_layout.addSpacing(4)

        quit_btn = QPushButton("Thoát (Quit)")
        quit_btn.setFixedHeight(32)
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

        self.page_title_lbl = QLabel("Tổng quan (Console)")
        self.page_title_lbl.setStyleSheet("font-size: 17px; font-weight: 800;")
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

        # Đồng bộ ban đầu
        self._update_all_metric_cards()

    # ========================================================
    # NAVIGATION CHUYỂN TRANG
    # ========================================================
    def _switch_to_page(self, index: int):
        self.pages.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setStyleSheet(NAV_BUTTON_ACTIVE if i == index else NAV_BUTTON_NORMAL)

        titles = [
            ("Tổng quan (Console)", "Điều khiển tiến trình quét OCR và theo dõi thông số theo thời gian thực"),
            ("Cấu hình AI Engine", "Quản lý nhà cung cấp API, mô hình LLM và khóa bảo mật"),
            ("Dịch thuật & Vùng quét OCR", "Thiết lập ngôn ngữ dịch thuật và khu vực theo dõi màn hình"),
            ("Tùy biến Phụ đề (Subtitle)", "Tùy chỉnh phong cách hiển thị và xem trước hộp phụ đề trực tiếp")
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

        # Hero Action Card (Nút START & STOP to bản)
        hero_card = ModernCard("Thao tác Điều khiển", "Khởi động hoặc dừng tiến trình quét và dịch màn hình")
        hero_row = QHBoxLayout()
        hero_row.setSpacing(12)

        self.start_btn = QPushButton("▶  BẮT ĐẦU (START)")
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet(HERO_START_STYLE)
        self.start_btn.clicked.connect(self.start_ocr)

        self.stop_btn = QPushButton("⏹  DỪNG (STOP)")
        self.stop_btn.setFixedHeight(44)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setStyleSheet(HERO_STOP_STYLE)
        self.stop_btn.clicked.connect(self.stop_ocr)

        hero_row.addWidget(self.start_btn)
        hero_row.addWidget(self.stop_btn)
        hero_card.layout.addLayout(hero_row)
        layout.addWidget(hero_card)

        # Status Metrics Grid (4 thẻ tóm tắt)
        metrics_card = ModernCard("Chỉ số Trực tiếp (Live Metrics)", "Tóm tắt cấu hình đang hoạt động")
        grid_row1 = QHBoxLayout()
        grid_row1.setSpacing(10)
        grid_row2 = QHBoxLayout()
        grid_row2.setSpacing(10)

        card_status = MetricCard("TRẠNG THÁI", "Đã dừng", "●")
        card_ai = MetricCard("AI MODEL", f"{load_active_provider()}", "🤖")
        card_lang = MetricCard("NGÔN NGỮ", f"{self.state.source} ➔ {self.state.target}", "🌐")
        
        reg = load_region()
        reg_txt = f"{reg.get('width', 0)} x {reg.get('height', 0)} px" if reg else "Chưa chọn vùng"
        card_reg = MetricCard("VÙNG QUÉT OCR", reg_txt, "📐")

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

        quick_select_btn = QPushButton("🎯 Chọn lại vùng quét màn hình")
        quick_select_btn.setFixedHeight(34)
        quick_select_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        quick_select_btn.setCursor(Qt.PointingHandCursor)
        quick_select_btn.clicked.connect(self._on_select_region_clicked)
        q_row.addWidget(quick_select_btn)

        quick_sub_btn = QPushButton("🎨 Chỉnh nhanh phụ đề")
        quick_sub_btn.setFixedHeight(34)
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
        p_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
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
        m_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
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

        self.toggle_key_btn = QPushButton("👁")
        self.toggle_key_btn.setFixedSize(38, 34)
        self.toggle_key_btn.setToolTip("Hiện / Ẩn API Key")
        self.toggle_key_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_key_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CYBER_PALETTE['bg_input']};
                border: 1px solid {CYBER_PALETTE['border']};
                border-radius: 7px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                border: 1px solid {CYBER_PALETTE['neon_indigo']};
            }}
        """)
        self.toggle_key_btn.clicked.connect(self._toggle_key_visibility)
        k_input_row.addWidget(self.toggle_key_btn)

        k_layout.addLayout(k_input_row)

        self.api_status_lbl = QLabel()
        self._update_api_status()
        k_layout.addWidget(self.api_status_lbl)

        self.key_card.layout.addLayout(k_layout)
        layout.addWidget(self.key_card)

        # Card 3: Guide Note
        note_card = ModernCard("💡 Hướng dẫn Lấy API Key")
        note_text = QLabel(
            "• Google Gemini: Truy cập Google AI Studio (aistudio.google.com)\n"
            "• OpenRouter: Truy cập openrouter.ai/keys để nhận key dùng hàng trăm model\n"
            "• Groq: Truy cập console.groq.com để nhận key tốc độ siêu cao miễn phí"
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
        src_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
        self.src_combo = QComboBox()
        self.src_combo.addItems(list(SUPPORTED_LANGUAGES.keys()))
        self.src_combo.setCurrentText(self.state.source if self.state.source in SUPPORTED_LANGUAGES else "English")
        self.src_combo.currentTextChanged.connect(self._on_source_lang_changed)
        src_col.addWidget(src_lbl)
        src_col.addWidget(self.src_combo)
        lang_row.addLayout(src_col)

        arrow_lbl = QLabel("➔")
        arrow_lbl.setAlignment(Qt.AlignCenter)
        arrow_lbl.setStyleSheet(f"font-size: 18px; color: {CYBER_PALETTE['neon_indigo']}; margin-top: 18px;")
        lang_row.addWidget(arrow_lbl)

        tgt_col = QVBoxLayout()
        tgt_col.setSpacing(4)
        tgt_lbl = QLabel("Ngôn ngữ dịch (Target)")
        tgt_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
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

        timing_info = QLabel("Khuyến nghị: 500ms cho đối thoại game thông thường, 300ms cho game hành động")
        timing_info.setStyleSheet(f"color: {CYBER_PALETTE['text_muted']}; font-size: 11.5px;")
        timing_info.setWordWrap(True)
        timing_row.addWidget(timing_info, stretch=1)

        ocr_timing_card.layout.addLayout(timing_row)
        layout.addWidget(ocr_timing_card)

        # Card 3: Region Inspector
        reg_card = ModernCard("Vùng màn hình đang theo dõi", "Tọa độ và kích thước khung hình camera OCR quét phụ đề")
        
        self.reg_info_lbl = QLabel()
        self._update_region_info_lbl()
        reg_card.layout.addWidget(self.reg_info_lbl)

        reg_btn = QPushButton("🎯 Chọn lại vùng quét màn hình (Kéo chuột)")
        reg_btn.setFixedHeight(36)
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

        # Card 1: Colors & Opacity
        style_card = ModernCard("Màu sắc & Độ trong suốt", "Tùy biến diện mạo hộp phụ đề nổi trên game")
        
        color_row = QHBoxLayout()
        color_row.setSpacing(12)

        # BG Color Picker
        bg_col = QVBoxLayout()
        bg_col.setSpacing(4)
        bg_lbl = QLabel("Màu nền (Background)")
        bg_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
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
        txt_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
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

        # Opacity Slider
        opacity_header = QHBoxLayout()
        op_lbl = QLabel("Độ trong suốt nền (Background Opacity)")
        op_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']};")
        self.opacity_val_lbl = QLabel(f"{self.state.bg_opacity}%")
        self.opacity_val_lbl.setStyleSheet(f"font-size: 12.5px; font-weight: 700; color: {CYBER_PALETTE['neon_indigo']};")
        opacity_header.addWidget(op_lbl)
        opacity_header.addStretch()
        opacity_header.addWidget(self.opacity_val_lbl)
        style_card.layout.addLayout(opacity_header)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(self.state.bg_opacity)
        self.opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: {CYBER_PALETTE['bg_input']};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {CYBER_PALETTE['neon_indigo']};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {CYBER_PALETTE['text_primary']};
                border: 2px solid {CYBER_PALETTE['neon_indigo']};
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }}
        """)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        style_card.layout.addWidget(self.opacity_slider)

        layout.addWidget(style_card)

        # Card 2: LIVE PREVIEW BOX
        preview_card = ModernCard("Xem trước Thời gian thực (Live Subtitle Preview)", "Mô phỏng chính xác khung phụ đề nổi hiển thị trên màn hình game")
        
        # Container giả lập game nền tối
        sim_container = QFrame()
        sim_container.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #121420, stop:1 #1e2235);
                border: 1px dashed {CYBER_PALETTE['border_light']};
                border-radius: 10px;
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
    def _update_live_preview_box(self):
        bg_col = QColor(self.state.bg_color)
        if not bg_col.isValid():
            bg_col = QColor("#1e1e2e")
        text_col = QColor(self.state.text_color)
        if not text_col.isValid():
            text_col = QColor("#ffffff")

        alpha = max(0.0, min(1.0, self.state.bg_opacity / 100.0))
        r, g, b = bg_col.red(), bg_col.green(), bg_col.blue()

        self.live_preview_box.setStyleSheet(f"""
            QLabel {{
                color: {text_col.name()};
                background-color: rgba({r}, {g}, {b}, {alpha:.2f});
                font-size: 16px;
                font-weight: 600;
                padding: 10px 18px;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 40);
                font-family: 'Segoe UI', 'Arial';
            }}
        """)

    def _update_color_btn_style(self, btn: QPushButton, hex_color: str):
        col = QColor(hex_color)
        if not col.isValid():
            col = QColor("#1e1e2e")
        text_col = "#000000" if (col.red() * 0.299 + col.green() * 0.587 + col.blue() * 0.114) > 150 else "#ffffff"
        btn.setText(f"  {col.name().upper()}")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {col.name()};
                color: {text_col};
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 7px;
                font-weight: 700;
                font-size: 12.5px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                border: 2px solid {CYBER_PALETTE['neon_indigo']};
            }}
        """)

    def _pick_bg_color(self):
        col = QColorDialog.getColor(QColor(self.state.bg_color), self, "Chọn màu nền phụ đề")
        if col.isValid():
            hex_str = col.name()
            self.state.update(bg_color=hex_str)
            self._update_color_btn_style(self.bg_color_btn, hex_str)
            self._update_live_preview_box()
            self._sync_overlay_style()

    def _pick_text_color(self):
        col = QColorDialog.getColor(QColor(self.state.text_color), self, "Chọn màu chữ phụ đề")
        if col.isValid():
            hex_str = col.name()
            self.state.update(text_color=hex_str)
            self._update_color_btn_style(self.text_color_btn, hex_str)
            self._update_live_preview_box()
            self._sync_overlay_style()

    def _on_opacity_changed(self, val: int):
        self.opacity_val_lbl.setText(f"{val}%")
        self.state.update(bg_opacity=val)
        self._update_live_preview_box()
        self._sync_overlay_style()

    def _sync_overlay_style(self):
        if self.overlay:
            self.overlay.apply_style(
                bg_hex=self.state.bg_color,
                opacity_pct=self.state.bg_opacity,
                text_hex=self.state.text_color
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
        save_active_provider(provider)
        self.api_key_input.blockSignals(True)
        self.api_key_input.setText(load_provider_api_key(provider))
        self.api_key_input.setPlaceholderText(PROVIDERS[provider]["placeholder"])
        self.api_key_input.blockSignals(False)
        self._populate_models_for_provider(provider)
        self._update_api_status()
        self._update_all_metric_cards()
        reload_client()

    def _on_api_key_changed(self, text: str = ""):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        key = self.api_key_input.text().strip()
        save_provider_api_key(provider, key)
        reload_client()
        self._update_api_status()
        self._update_all_metric_cards()

    def _on_model_changed(self, model: str):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        if model.strip():
            save_provider_model_id(provider, model.strip())
            reload_client()
            self._update_all_metric_cards()

    def _toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_key_btn.setText("🔒")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.toggle_key_btn.setText("👁")

    def _update_api_status(self):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        if load_provider_api_key(provider).strip():
            self.api_status_lbl.setText(f"Trạng thái: ✅ {provider} sẵn sàng (.env)")
            self.api_status_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_green']}; font-size: 11.5px; font-weight: 600;")
        else:
            self.api_status_lbl.setText(f"Trạng thái: ⚠️ Chưa có API Key cho {provider}")
            self.api_status_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_amber']}; font-size: 11.5px; font-weight: 600;")

    def _on_source_lang_changed(self, lang: str):
        self.state.update(source=lang)
        self._update_all_metric_cards()

    def _on_target_lang_changed(self, lang: str):
        self.state.update(target=lang)
        self._update_all_metric_cards()

    def _on_interval_changed(self, val: int):
        if self.worker is not None:
            self.worker.setInterval(val)
        save_config("interval_ms", val)

    def _update_region_info_lbl(self):
        reg = load_region()
        if reg:
            self.reg_info_lbl.setText(
                f"Tọa độ: X={reg.get('left', 0)}, Y={reg.get('top', 0)} | "
                f"Kích thước: {reg.get('width', 0)} x {reg.get('height', 0)} px"
            )
            self.reg_info_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_green']}; font-size: 12px; font-weight: 600;")
        else:
            self.reg_info_lbl.setText("Chưa chọn vùng quét màn hình. Vui lòng bấm nút bên dưới để chọn.")
            self.reg_info_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_amber']}; font-size: 12px; font-weight: 600;")

    def _on_select_region_clicked(self):
        if callable(self.on_select_region_cb):
            self.on_select_region_cb()
        # Cập nhật thông số sau khi chọn
        self._update_region_info_lbl()
        self._update_all_metric_cards()

    def _update_all_metric_cards(self):
        if not hasattr(self, "metric_cards") or not self.metric_cards:
            return
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        model = self.model_combo.currentText() if hasattr(self, "model_combo") else load_provider_model_id(provider)
        
        self.metric_cards["ai"].set_value(f"{provider}\n{model}")
        self.metric_cards["lang"].set_value(f"{self.state.source} ➔ {self.state.target}")
        
        reg = load_region()
        reg_txt = f"{reg.get('width', 0)} x {reg.get('height', 0)} px" if reg else "Chưa chọn vùng"
        self.metric_cards["region"].set_value(reg_txt)

    def start_ocr(self):
        provider = self.provider_combo.currentText() if hasattr(self, "provider_combo") else load_active_provider()
        if not load_provider_api_key(provider).strip():
            self.status.setText("● Lỗi: Thiếu API Key")
            self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 700;")
            
            # Tự động chuyển người dùng sang tab AI Engine
            self._switch_to_page(1)
            
            # Hiệu ứng viền cảnh báo ô nhập API Key
            self.key_card.setStyleSheet(f"""
                QFrame#cardFrame {{
                    background-color: {CYBER_PALETTE['bg_card']};
                    border: 2px solid {CYBER_PALETTE['neon_rose']};
                    border-radius: 10px;
                }}
            """)
            QTimer.singleShot(2500, lambda: self.key_card.setStyleSheet(CARD_FRAME_STYLE))
            return

        if self.worker:
            self.worker.start_worker()
        
        self.status.setText("● Đang chạy (Active)")
        self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_green']}; font-size: 11.5px; font-weight: 700;")
        if "status" in self.metric_cards:
            self.metric_cards["status"].set_value("Đang chạy (Active)")

    def stop_ocr(self):
        if self.worker:
            self.worker.stop_worker()
        self.status.setText("● Đã dừng (Stopped)")
        self.status.setStyleSheet(f"color: {CYBER_PALETTE['neon_rose']}; font-size: 11.5px; font-weight: 700;")
        if "status" in self.metric_cards:
            self.metric_cards["status"].set_value("Đã dừng")
