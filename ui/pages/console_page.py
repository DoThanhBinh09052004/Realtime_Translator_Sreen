import math
import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QPlainTextEdit
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal
from ui.widgets.cards import ModernCard, MetricCard
from ui.styles import CYBER_PALETTE, HERO_START_STYLE, HERO_STOP_STYLE, SECONDARY_BUTTON_STYLE
from ui.icons import get_lucide_icon
from ui.controller_state import ControllerSnapshot


class ConsolePage(QWidget):
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    select_region_requested = pyqtSignal()
    subtitle_settings_requested = pyqtSignal()
    retry_translation_requested = pyqtSignal()

    def __init__(self, snapshot: ControllerSnapshot, parent=None):
        super().__init__(parent)
        self.metric_cards = {}
        self._translation_status = None
        self._countdown = QTimer(self)
        self._countdown.setInterval(500)
        self._countdown.timeout.connect(self._refresh_countdown)
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
        self.retry_translation_btn = QPushButton('Thử lại')
        self.retry_translation_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.retry_translation_btn.clicked.connect(self.retry_translation_requested.emit)
        self.retry_translation_btn.hide()
        hero_row.addWidget(self.retry_translation_btn)
        hero_card.layout.addLayout(hero_row)
        self.translation_message = QLabel()
        self.translation_message.setWordWrap(True)
        self.translation_message.hide()
        hero_card.layout.addWidget(self.translation_message)
        layout.addWidget(hero_card)

        # Status Metrics Grid (4 thẻ tóm tắt với Lucide Icons)
        metrics_card = ModernCard("Chỉ số Trực tiếp", "Tóm tắt cấu hình đang hoạt động")
        grid_row1 = QHBoxLayout()
        grid_row1.setSpacing(10)
        grid_row2 = QHBoxLayout()
        grid_row2.setSpacing(10)

        card_status = MetricCard("TRẠNG THÁI", "Đã dừng", icon_name="activity", icon_color=CYBER_PALETTE['neon_rose'])
        card_ai = MetricCard("CÔNG CỤ DỊCH", snapshot.ai.provider, icon_name="cpu", icon_color=CYBER_PALETTE['neon_indigo'])
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

        log_card = ModernCard('Nhật ký dịch', 'Hiển thị nội dung request và thời gian phản hồi')
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(300)
        self.log_view.setPlaceholderText('Nhật ký sẽ xuất hiện khi bắt đầu quét.')
        self.log_view.setMinimumHeight(120)
        self.log_view.setMaximumHeight(190)
        log_card.layout.addWidget(self.log_view)
        log_buttons = QHBoxLayout()
        log_buttons.addStretch()
        self.clear_log_btn = QPushButton('Xóa nhật ký')
        self.clear_log_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.clear_log_btn.clicked.connect(self.log_view.clear)
        log_buttons.addWidget(self.clear_log_btn)
        log_card.layout.addLayout(log_buttons)
        layout.addWidget(log_card)

        layout.addStretch()
        self.select_region_btn = quick_select_btn
        self.subtitle_settings_btn = quick_sub_btn
        self.render_summary(snapshot)

    def render_summary(self, snapshot: ControllerSnapshot):
        model = f'\n{snapshot.ai.model_id}' if snapshot.ai.supports_models else ''
        self.metric_cards['ai'].set_value(snapshot.ai.provider+model)
        self.metric_cards['lang'].set_value(f'{snapshot.ocr.source} -> {snapshot.ocr.target}')
        region = snapshot.ocr.region
        self.metric_cards['region'].set_value(f'{region[2]} x {region[3]} px' if region else 'Chưa chọn vùng')

    def set_run_status(self, text: str):
        self.metric_cards['status'].set_value(text)

    def append_log(self, line: str):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def clear_translation_status(self):
        self._translation_status = None
        self._countdown.stop()
        self.retry_translation_btn.hide()
        self.translation_message.hide()

    def _refresh_countdown(self):
        if self._translation_status is not None:
            self.render_translation_status(self._translation_status, now_s=time.monotonic())

    def render_translation_status(self, status, *, now_s):
        self._translation_status = status
        google = status.provider == 'Google Translate'
        paused = google and status.phase == 'paused'
        waiting = google and status.phase == 'retry_wait'
        self.retry_translation_btn.setVisible(paused)
        self.retry_translation_btn.setEnabled(paused)
        self.translation_message.setVisible(paused or waiting)
        if paused:
            self.translation_message.setText('Tạm dừng dịch Google. OCR vẫn đang quét. Bấm Thử lại để tiếp tục.')
            self.set_run_status('Tạm dừng dịch Google')
        elif waiting:
            remaining = max(0, math.ceil((status.retry_at_s or now_s)-now_s))
            self.translation_message.setText(f'Google Translate: chờ {remaining} giây trước khi thử lại (lượt {status.retries_issued}/3).')
            self.set_run_status('Chờ thử lại Google')
        elif status.phase == 'stopped':
            self.set_run_status('Đã dừng')
        else:
            self.set_run_status('Đang hoạt động')
        if waiting:
            self._countdown.start()
        else:
            self._countdown.stop()
