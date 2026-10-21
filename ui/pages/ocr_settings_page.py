from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QPushButton
from PyQt5.QtCore import Qt, QSize, QSignalBlocker, pyqtSignal
from ui.widgets.cards import ModernCard
from ui.styles import CYBER_PALETTE, SECONDARY_BUTTON_STYLE
from ui.icons import get_lucide_icon
from ui.controller_state import OcrPageState


class OcrSettingsPage(QScrollArea):
    source_changed = pyqtSignal(str)
    target_changed = pyqtSignal(str)
    interval_changed = pyqtSignal(int)
    select_region_requested = pyqtSignal()

    def __init__(self, state: OcrPageState, source_languages: tuple[str, ...], target_languages: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

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
        self.src_combo.addItems(source_languages)
        self.src_combo.setCurrentText(state.source if state.source in source_languages else "English")
        self.src_combo.currentTextChanged.connect(self.source_changed.emit)
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
        self.tgt_combo.addItems(target_languages)
        self.tgt_combo.setCurrentText(state.target if state.target in target_languages else "Vietnamese")
        self.tgt_combo.currentTextChanged.connect(self.target_changed.emit)
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

        saved_interval = state.interval_ms
        self.interval_spin.setValue(saved_interval)
        self.interval_spin.valueChanged.connect(self.interval_changed.emit)

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
        self._render_region(state)
        reg_card.layout.addWidget(self.reg_info_lbl)

        reg_btn = QPushButton("  Chọn lại vùng quét (Kéo chuột)")
        reg_btn.setFixedHeight(34)
        reg_btn.setIcon(get_lucide_icon("scan", color=CYBER_PALETTE['text_muted'], size=15))
        reg_btn.setIconSize(QSize(15, 15))
        reg_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        reg_btn.setCursor(Qt.PointingHandCursor)
        reg_btn.clicked.connect(self.select_region_requested.emit)
        reg_card.layout.addWidget(reg_btn)

        layout.addWidget(reg_card)

        layout.addStretch()
        self.setWidget(content)
        self.select_region_btn = reg_btn

    def _render_region(self, state):
        reg = state.region
        if reg:
            self.reg_info_lbl.setText(
                f"Tọa độ: X={reg[0]}, Y={reg[1]} | "
                f"Kích thước: {reg[2]} x {reg[3]} px"
            )
            self.reg_info_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_green']}; font-size: 12px; font-weight: 500;")
        else:
            self.reg_info_lbl.setText("Chưa chọn vùng quét màn hình. Bấm nút bên dưới để chọn.")
            self.reg_info_lbl.setStyleSheet(f"color: {CYBER_PALETTE['neon_amber']}; font-size: 12px; font-weight: 500;")

    def render(self, state: OcrPageState):
        blockers = [QSignalBlocker(widget) for widget in (self.src_combo, self.tgt_combo, self.interval_spin)]
        self.src_combo.setCurrentText(state.source)
        self.tgt_combo.setCurrentText(state.target)
        self.interval_spin.setValue(state.interval_ms)
        self._render_region(state)
        del blockers
