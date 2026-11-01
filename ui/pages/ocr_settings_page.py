from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QPushButton, QSlider, QBoxLayout, QLayout
from PyQt5.QtCore import Qt, QSize, QSignalBlocker, pyqtSignal
from ui.widgets.capture_snapshot import CaptureSnapshotWidget
from ui.widgets.cards import ModernCard
from ui.widgets.ocr_performance_card import OcrPerformanceCard
from ui.styles import TOKENS, set_style, apply_widget_theme, button_style
from ui.icons import set_theme_icon
from ui.controller_state import LanguageChoice, OcrPageState


class OcrSettingsPage(QScrollArea):
    source_changed = pyqtSignal(str)
    target_changed = pyqtSignal(str)
    interval_changed = pyqtSignal(int)
    performance_mode_changed = pyqtSignal(str)
    auto_threads_changed = pyqtSignal(bool)
    threads_changed = pyqtSignal(int)
    select_region_requested = pyqtSignal()
    manage_packs_requested = pyqtSignal()
    preview_requested = pyqtSignal()

    def __init__(self, state: OcrPageState, source_languages: tuple[str, ...], target_languages: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SetMinAndMaxSize)

        self.columns = QBoxLayout(QBoxLayout.LeftToRight)
        layout.addLayout(self.columns)
        left = QWidget()
        controls = QVBoxLayout(left)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(14)
        controls.setSizeConstraint(QLayout.SetMinimumSize)
        self.columns.addWidget(left, 55)
        # Card 1: Language selection
        lang_card = ModernCard("Ngôn ngữ Dịch thuật", "Lựa chọn ngôn ngữ nguồn hiển thị trong game và ngôn ngữ dịch sang")
        lang_row = QHBoxLayout()
        lang_row.setSpacing(12)

        src_col = QVBoxLayout()
        src_col.setSpacing(4)
        src_lbl = QLabel("Ngôn ngữ nguồn (Source)")
        set_style(src_lbl, f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};")
        self.src_combo = QComboBox()
        self.src_combo.setPlaceholderText('Chọn ngôn ngữ đã cài')
        self._source_choices = tuple(LanguageChoice(name, name, name) for name in source_languages)
        self.update_source_choices(state.source_choices if state.source_choices is not None else self._source_choices, state.source)
        self.src_combo.currentIndexChanged.connect(self._source_index_changed)
        src_col.addWidget(src_lbl)
        src_col.addWidget(self.src_combo)
        lang_row.addLayout(src_col)

        arrow_lbl = QLabel("->")
        arrow_lbl.setAlignment(Qt.AlignCenter)
        set_style(arrow_lbl, f"font-size: 15px; font-weight: 600; color: {TOKENS['focus']}; margin-top: 18px;")
        lang_row.addWidget(arrow_lbl)

        tgt_col = QVBoxLayout()
        tgt_col.setSpacing(4)
        tgt_lbl = QLabel("Ngôn ngữ dịch (Target)")
        set_style(tgt_lbl, f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};")
        self.tgt_combo = QComboBox()
        self.tgt_combo.addItems(target_languages)
        self.tgt_combo.setCurrentText(state.target if state.target in target_languages else "Vietnamese")
        self.tgt_combo.currentTextChanged.connect(self.target_changed.emit)
        tgt_col.addWidget(tgt_lbl)
        tgt_col.addWidget(self.tgt_combo)
        lang_row.addLayout(tgt_col)

        lang_card.layout.addLayout(lang_row)
        self.source_notice_label = QLabel(state.source_notice)
        self.source_notice_label.setWordWrap(True)
        set_style(self.source_notice_label, f"color: {TOKENS['warning']}; font-size: 12px;")
        self.source_notice_label.setVisible(bool(state.source_notice))
        lang_card.layout.addWidget(self.source_notice_label)
        controls.addWidget(lang_card)

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
        self.interval_spin.valueChanged.connect(self._on_interval_spin_changed)

        self._confirmed_interval = saved_interval
        self.interval_slider = QSlider(Qt.Horizontal)
        self.interval_slider.setRange(100, 3000)
        self.interval_slider.setSingleStep(50)
        self.interval_slider.setValue(saved_interval)
        self.interval_slider.setAccessibleName('Chu kỳ quét OCR')
        self.interval_slider.valueChanged.connect(self._on_interval_slider_changed)
        self.interval_slider.sliderReleased.connect(self._commit_interval_slider)
        timing_row.addWidget(self.interval_slider, 1)
        timing_row.addWidget(self.interval_spin)

        timing_info = QLabel("Khuyến nghị: 500ms cho đối thoại game thông thường, 300ms cho game nhịp độ nhanh")
        set_style(timing_info, f"color: {TOKENS['muted']}; font-size: 12px;")
        timing_info.setWordWrap(True)
        timing_row.addWidget(timing_info, stretch=1)

        ocr_timing_card.layout.addLayout(timing_row)
        controls.addWidget(ocr_timing_card)

        # Card: OCR Performance & CPU/RAM Allocation
        self.performance_card = OcrPerformanceCard(
            performance_mode=state.performance_mode,
            auto_threads=state.auto_threads,
            threads=state.threads,
            parent=self
        )
        self.performance_card.mode_changed.connect(self.performance_mode_changed.emit)
        self.performance_card.auto_threads_changed.connect(self.auto_threads_changed.emit)
        self.performance_card.threads_changed.connect(self.threads_changed.emit)
        controls.addWidget(self.performance_card)
        controls.addStretch()

        # Card 3: Region Inspector
        reg_card = ModernCard("Vùng màn hình theo dõi", "Tọa độ và kích thước khung hình camera OCR quét phụ đề")
        
        self.reg_info_lbl = QLabel()
        self._render_region(state)
        reg_card.layout.addWidget(self.reg_info_lbl)
        from ui.capture_settings import CaptureSettings
        self.capture_settings = CaptureSettings(parent=self, compact=True)
        reg_card.layout.addWidget(self.capture_settings)

        reg_btn = QPushButton("  Quản lý vùng quét")
        reg_btn.setFixedHeight(34)
        set_theme_icon(reg_btn, "scan", 'muted', 15)
        reg_btn.setIconSize(QSize(15, 15))
        set_style(reg_btn, button_style('secondary', 'tokens'))
        reg_btn.setCursor(Qt.PointingHandCursor)
        reg_btn.clicked.connect(self.select_region_requested.emit)
        reg_card.layout.addWidget(reg_btn)

        self.snapshot_widget = CaptureSnapshotWidget()
        self.snapshot_widget.setMinimumHeight(240)
        self.preview_status_label = QLabel('Chọn nguồn, xác nhận rồi bấm Làm mới ảnh.')
        self.preview_status_label.setWordWrap(True)
        self.refresh_preview_btn = QPushButton('Làm mới ảnh')
        self.refresh_preview_btn.clicked.connect(self.preview_requested.emit)
        reg_card.layout.addWidget(self.snapshot_widget)
        reg_card.layout.addWidget(self.preview_status_label)
        reg_card.layout.addWidget(self.refresh_preview_btn)
        self.columns.addWidget(reg_card, 45)
        self.columns.setAlignment(reg_card, Qt.AlignTop)

        layout.addStretch()
        self.setWidget(content)
        self.select_region_btn = reg_btn

    def _on_interval_spin_changed(self, value):
        with QSignalBlocker(self.interval_slider):
            self.interval_slider.setValue(value)
        self.interval_changed.emit(value)

    def _on_interval_slider_changed(self, value):
        with QSignalBlocker(self.interval_spin):
            self.interval_spin.setValue(value)
        if not self.interval_slider.isSliderDown():
            self._commit_interval_slider()

    def _commit_interval_slider(self):
        value = self.interval_slider.value()
        if value != self._confirmed_interval:
            self.interval_changed.emit(value)

    def set_capture_snapshot(self, image, profile, context, *, captured_at=''):
        self.snapshot_widget.set_snapshot(image, profile, context)
        self.preview_status_label.setText('Ảnh nguồn • ' + captured_at)

    def clear_capture_snapshot(self, message=''):
        message = message or 'Chọn nguồn, xác nhận rồi bấm Làm mới ảnh.'
        self.snapshot_widget.clear_snapshot(message)
        self.preview_status_label.setText(message)

    def set_preview_state(self, enabled, message=''):
        self.refresh_preview_btn.setEnabled(enabled)
        self.refresh_preview_btn.setToolTip(message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_layout(self.viewport().width())

    def _reflow_layout(self, width):
        self.columns.setDirection(QBoxLayout.LeftToRight if width >= 800 else QBoxLayout.TopToBottom)
        self.performance_card.set_compact(width < 800)

    def _render_region(self, state):
        reg = state.region
        if reg:
            self.reg_info_lbl.setText(
                f"Tọa độ: X={reg[0]}, Y={reg[1]} | "
                f"Kích thước: {reg[2]} x {reg[3]} px"
            )
            set_style(self.reg_info_lbl, f"color: {TOKENS['positive']}; font-size: 12px; font-weight: 500;")
        else:
            self.reg_info_lbl.setText("Chưa chọn vùng quét màn hình. Bấm nút bên dưới để chọn.")
            set_style(self.reg_info_lbl, f"color: {TOKENS['warning']}; font-size: 12px; font-weight: 500;")

    def render(self, state: OcrPageState):
        blockers = [QSignalBlocker(widget) for widget in (self.src_combo, self.tgt_combo, self.interval_spin)]
        self.update_source_choices(state.source_choices if state.source_choices is not None else self._source_choices, state.source)
        self.source_notice_label.setText(state.source_notice)
        self.source_notice_label.setVisible(bool(state.source_notice))
        self.tgt_combo.setCurrentText(state.target)
        self.interval_spin.setValue(state.interval_ms)
        with QSignalBlocker(self.interval_slider):
            self.interval_slider.setValue(state.interval_ms)
        self._confirmed_interval = state.interval_ms
        self._render_region(state)
        self.performance_card.set_state(state.performance_mode, state.auto_threads, state.threads)
        del blockers

    def update_source_choices(self, choices: tuple[LanguageChoice, ...], selected_config_name: str) -> None:
        blocker = QSignalBlocker(self.src_combo)
        self._source_choices = choices
        self.src_combo.clear()
        index = -1
        for choice in choices:
            self.src_combo.addItem(choice.label, choice.id)
            if choice.config_name == selected_config_name:
                index = self.src_combo.count() - 1
        self.src_combo.insertSeparator(self.src_combo.count())
        self.src_combo.addItem('Quản lý gói ngôn ngữ…', '__manage_language_packs__')
        self.src_combo.setCurrentIndex(index)
        self._source_index = index
        del blocker

    def _source_index_changed(self, index: int) -> None:
        token = self.src_combo.itemData(index)
        if token == '__manage_language_packs__':
            blocker = QSignalBlocker(self.src_combo)
            self.src_combo.setCurrentIndex(self._source_index)
            del blocker
            self.manage_packs_requested.emit()
            return
        choice = next((choice for choice in self._source_choices if choice.id == token), None)
        if choice is not None:
            self._source_index = index
            self.source_changed.emit(choice.config_name)

    def apply_theme(self, theme: str):
        apply_widget_theme(self, theme)
