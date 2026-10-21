from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from ui.widgets.cards import ModernCard, MetricCard
from ui.styles import CYBER_PALETTE, HERO_START_STYLE, HERO_STOP_STYLE, SECONDARY_BUTTON_STYLE
from ui.icons import get_lucide_icon
from ui.controller_state import ControllerSnapshot


class ConsolePage(QWidget):
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    select_region_requested = pyqtSignal()
    subtitle_settings_requested = pyqtSignal()

    def __init__(self, snapshot: ControllerSnapshot, parent=None):
        super().__init__(parent)
        self.metric_cards = {}
        layout = QVBoxLayout(self)
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
        self.start_btn.clicked.connect(self.start_requested.emit)

        self.stop_btn = QPushButton("  Dừng (Stop)")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setIcon(get_lucide_icon("square", color="#ffffff", size=14))
        self.stop_btn.setIconSize(QSize(14, 14))
        self.stop_btn.setStyleSheet(HERO_STOP_STYLE)
        self.stop_btn.clicked.connect(self.stop_requested.emit)

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
        card_ai = MetricCard("AI MODEL", snapshot.ai.provider, icon_name="cpu", icon_color=CYBER_PALETTE['neon_indigo'])
        card_lang = MetricCard("NGÔN NGỮ", f"{snapshot.ocr.source} -> {snapshot.ocr.target}", icon_name="languages", icon_color=CYBER_PALETTE['text_muted'])
        
        reg = snapshot.ocr.region
        reg_txt = f"{reg[2]} x {reg[3]} px" if reg else "Chưa chọn vùng"
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
        quick_select_btn.clicked.connect(self.select_region_requested.emit)
        q_row.addWidget(quick_select_btn)

        quick_sub_btn = QPushButton("  Chỉnh phụ đề")
        quick_sub_btn.setFixedHeight(32)
        quick_sub_btn.setIcon(get_lucide_icon("sliders", color=CYBER_PALETTE['text_muted'], size=14))
        quick_sub_btn.setIconSize(QSize(14, 14))
        quick_sub_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        quick_sub_btn.setCursor(Qt.PointingHandCursor)
        quick_sub_btn.clicked.connect(self.subtitle_settings_requested.emit)
        q_row.addWidget(quick_sub_btn)

        quick_card.layout.addLayout(q_row)
        layout.addWidget(quick_card)

        layout.addStretch()
        self.select_region_btn = quick_select_btn
        self.subtitle_settings_btn = quick_sub_btn
        self.render_summary(snapshot)

    def render_summary(self, snapshot: ControllerSnapshot):
        self.metric_cards['ai'].set_value(f'{snapshot.ai.provider}\n{snapshot.ai.model_id}')
        self.metric_cards['lang'].set_value(f'{snapshot.ocr.source} -> {snapshot.ocr.target}')
        region = snapshot.ocr.region
        self.metric_cards['region'].set_value(f'{region[2]} x {region[3]} px' if region else 'Chưa chọn vùng')

    def set_run_status(self, text: str):
        self.metric_cards['status'].set_value(text)
