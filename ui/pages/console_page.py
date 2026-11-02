"""Focused daily translation screen (Screen A)."""
import math
import time
from typing import Any
from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QPlainTextEdit, QFrame, QSizePolicy, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, QSignalBlocker, pyqtSignal, QSize

from ui.widgets.cards import ModernCard
from ui.widgets.capture_snapshot import CaptureSnapshotWidget
from ui.widgets.translation_output import TranslationOutputWidget
from ui.capture_settings import CaptureSettings
from ui.presentation import subtitle_preview_style
from ui.styles import (TOKENS, set_style, apply_widget_theme, button_style, text_style,
                       CONTROL_HEIGHT, CONTROL_HEADER_HEIGHT, palette_for)
from ui.icons import set_theme_icon, get_provider_icon
from ui.controller_state import ControllerSnapshot, DailyReadiness, DailyRunState, PresentedTranslation


SOURCE_LANGUAGE_LABELS = {
    'English': 'Tiếng Anh',
    'Japanese': 'Tiếng Nhật',
    'Korean': 'Tiếng Hàn',
    'Chinese': 'Tiếng Trung',
}

TARGET_LANGUAGE_LABELS = {
    'Vietnamese': 'Tiếng Việt',
    'English': 'Tiếng Anh',
}


class ConsolePage(QWidget):
    provider_changed = pyqtSignal(str)
    source_changed = pyqtSignal(str)
    target_changed = pyqtSignal(str)
    toggle_requested = pyqtSignal()
    preview_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    readiness_action_requested = pyqtSignal(str)
    select_region_requested = pyqtSignal()
    manage_regions_requested = pyqtSignal()
    subtitle_settings_requested = pyqtSignal()
    retry_translation_requested = pyqtSignal()

    def __init__(self, snapshot: ControllerSnapshot, parent=None):
        super().__init__(parent)
        self._translation_status = None
        self._current_readiness_action = None
        self._is_running_phase = False
        self._presentation = None
        self._subtitle_state = snapshot.subtitle
        self._wide_layout = None
        self._countdown = QTimer(self)
        self._countdown.setInterval(500)
        self._countdown.timeout.connect(self._refresh_countdown)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.settings_btn = QPushButton('Thiết lập')
        set_theme_icon(self.settings_btn, 'sliders', size=15)
        self.settings_btn.clicked.connect(self.settings_requested.emit)

        controls = ModernCard()
        self.top_grid = QGridLayout()
        self.top_grid.setSpacing(16)
        controls.layout.addLayout(self.top_grid)
        self.language_group = QWidget()
        languages = QVBoxLayout(self.language_group)
        languages.setContentsMargins(0, 0, 0, 0)
        language_label = QLabel('Ngôn ngữ')
        language_label.setFixedHeight(CONTROL_HEADER_HEIGHT)
        set_style(language_label, text_style('body'))
        languages.addWidget(language_label)
        language_row = QHBoxLayout()
        self.src_combo = QComboBox()
        self.src_combo.setFixedHeight(CONTROL_HEIGHT)
        self.src_combo.setAccessibleName('Ngôn ngữ nguồn')
        self.src_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._init_source_languages(snapshot)
        self.src_combo.currentIndexChanged.connect(self._on_source_combo_changed)
        self.tgt_combo = QComboBox()
        self.tgt_combo.setFixedHeight(CONTROL_HEIGHT)
        self.tgt_combo.setAccessibleName('Ngôn ngữ đích')
        self.tgt_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._init_target_languages(snapshot)
        self.tgt_combo.currentIndexChanged.connect(self._on_target_combo_changed)
        language_row.addWidget(self.src_combo, 1)
        language_row.addWidget(QLabel('→'))
        language_row.addWidget(self.tgt_combo, 1)
        languages.addLayout(language_row)
        languages.addStretch()
        self.source_group = QWidget()
        source_layout = QVBoxLayout(self.source_group)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.capture_settings = CaptureSettings(parent=self, compact=True)
        source_layout.addWidget(self.capture_settings)
        self.engine_group = QWidget()
        engine_layout = QVBoxLayout(self.engine_group)
        engine_layout.setContentsMargins(0, 0, 0, 0)
        engine_label = QLabel('Công cụ dịch')
        engine_label.setFixedHeight(CONTROL_HEADER_HEIGHT)
        set_style(engine_label, text_style('body'))
        engine_layout.addWidget(engine_label)
        self.provider_combo = QComboBox()
        self.provider_combo.setIconSize(QSize(20, 20))
        self.provider_combo.setFixedHeight(CONTROL_HEIGHT)
        self.provider_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.provider_combo.setAccessibleName('Công cụ dịch')
        self.provider_combo.addItem(self._provider_icon(snapshot.ai.provider), snapshot.ai.provider, snapshot.ai.provider)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        engine_layout.addWidget(self.provider_combo)
        engine_layout.addStretch()
        layout.addWidget(controls)

        self.body_grid = QGridLayout()
        self.body_grid.setSpacing(14)
        self.region_card = ModernCard()
        region_header = QHBoxLayout()
        region_title = QLabel('Vùng đọc chữ')
        set_style(region_title, text_style('section'))
        region_header.addWidget(region_title)
        self.region_info_lbl = QLabel()
        self.region_info_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        set_style(self.region_info_lbl, text_style('caption'))
        region_header.addWidget(self.region_info_lbl, 1)
        self.select_region_btn = QPushButton('Khoanh vùng')
        set_theme_icon(self.select_region_btn, 'scan', size=15)
        self.select_region_btn.clicked.connect(self.select_region_requested.emit)
        region_header.addWidget(self.select_region_btn)
        self.region_card.layout.addLayout(region_header)
        self.snapshot_widget = CaptureSnapshotWidget(self)
        self.snapshot_widget.setMinimumHeight(185)
        self.region_card.layout.addWidget(self.snapshot_widget, 1)
        preview_footer = QHBoxLayout()
        notice = QLabel('Ảnh chụp xem trước')
        self.snapshot_status_label = notice
        set_style(notice, text_style('caption'))
        preview_footer.addWidget(notice, 1)
        self.refresh_preview_btn = QPushButton('Làm mới ảnh')
        set_theme_icon(self.refresh_preview_btn, 'refresh-cw', size=14)
        self.refresh_preview_btn.clicked.connect(self.preview_requested.emit)
        preview_footer.addWidget(self.refresh_preview_btn)
        self.region_card.layout.addLayout(preview_footer)
        self.manage_regions_btn = QPushButton()
        self.manage_regions_btn.setToolTip('Quản lý vùng nâng cao')
        self.manage_regions_btn.setAccessibleName('Quản lý vùng nâng cao')
        set_theme_icon(self.manage_regions_btn, 'sliders', size=14)
        self.manage_regions_btn.clicked.connect(self.manage_regions_requested.emit)
        region_header.addWidget(self.manage_regions_btn)

        self.output_card = ModernCard('Bản dịch mới nhất')
        self.output_widget = TranslationOutputWidget(self)
        self.output_card.layout.addWidget(self.output_widget, 1)
        subtitle_header = QHBoxLayout()
        subtitle_label = QLabel('Xem trước phụ đề')
        set_style(subtitle_label, text_style('caption'))
        subtitle_header.addWidget(subtitle_label, 1)
        self.customize_btn = QPushButton('Tùy chỉnh')
        self.customize_btn.clicked.connect(self.subtitle_settings_requested.emit)
        self.subtitle_settings_btn = self.customize_btn
        subtitle_header.addWidget(self.customize_btn)
        self.output_card.layout.addLayout(subtitle_header)
        self.subtitle_preview_frame = QFrame()
        self.subtitle_preview_frame.setObjectName('subtitlePreviewFrame')
        preview_layout = QVBoxLayout(self.subtitle_preview_frame)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(0)
        self.subtitle_preview = QLabel('Chưa có bản dịch được hiển thị')
        self.subtitle_preview.setWordWrap(True)
        self.subtitle_preview.setTextFormat(Qt.PlainText)
        self.subtitle_preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.subtitle_preview.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.subtitle_preview)
        self.output_card.layout.addWidget(self.subtitle_preview_frame)
        layout.addLayout(self.body_grid, 1)

        self.details_toggle_btn = QPushButton('▸ Chi tiết phiên dịch')
        self.details_toggle_btn.clicked.connect(self._toggle_details)
        layout.addWidget(self.details_toggle_btn)
        self.details_container = QWidget()
        details = QVBoxLayout(self.details_container)
        details.setContentsMargins(0, 0, 0, 0)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(300)
        self.log_view.setMaximumHeight(150)
        self.log_view.setPlaceholderText('Nhật ký sẽ xuất hiện khi bắt đầu quét.')
        details.addWidget(self.log_view)
        self.clear_log_btn = QPushButton('Xóa nhật ký')
        self.clear_log_btn.clicked.connect(self.log_view.clear)
        details.addWidget(self.clear_log_btn, alignment=Qt.AlignRight)
        self.details_container.hide()
        layout.addWidget(self.details_container)
        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area, 1)

        footer = QFrame()
        set_style(footer, f'QFrame {{border-top:1px solid {TOKENS["border"]};}} QLabel {{border:0;}}')
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 12, 0, 0)
        row = QHBoxLayout()
        self.readiness_lbl = QLabel('Chưa sẵn sàng')
        self.readiness_lbl.setWordWrap(True)
        self.readiness_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.readiness_lbl, 1)
        self.readiness_action_btn = QPushButton('Khắc phục')
        self.readiness_action_btn.clicked.connect(self._on_readiness_action_clicked)
        self.readiness_action_btn.hide()
        row.addWidget(self.readiness_action_btn)
        self.primary_btn = QPushButton('Bắt đầu dịch')
        self.primary_btn.setMinimumHeight(42)
        self.primary_btn.setMinimumWidth(165)
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        set_style(self.primary_btn, button_style('primary', 'tokens'))
        row.addWidget(self.primary_btn)
        footer_layout.addLayout(row)
        self.session_info = QLabel()
        set_style(self.session_info, text_style('caption'))
        footer_layout.addWidget(self.session_info)
        recovery = QHBoxLayout()
        self.translation_message = QLabel()
        self.translation_message.setWordWrap(True)
        self.translation_message.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.translation_message.hide()
        recovery.addWidget(self.translation_message, 1)
        self.retry_translation_btn = QPushButton('Thử lại')
        self.retry_translation_btn.clicked.connect(self.retry_translation_requested.emit)
        self.retry_translation_btn.hide()
        recovery.addWidget(self.retry_translation_btn)
        footer_layout.addLayout(recovery)
        root.addWidget(footer)
        self._reflow_layout(self.width())
        self.render_summary(snapshot)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_layout(event.size().width())

    def _reflow_layout(self, content_width: int):
        wide = content_width >= 1000
        if wide == self._wide_layout:
            return
        self._wide_layout = wide
        for grid in (self.top_grid, self.body_grid):
            while grid.count():
                grid.takeAt(0)
            for column in range(3):
                grid.setColumnStretch(column, 0)
        for index, group in enumerate((self.language_group, self.source_group, self.engine_group)):
            self.top_grid.addWidget(group, 0 if wide else index, index if wide else 0, alignment=Qt.AlignTop)
        if wide:
            for index, stretch in enumerate((4, 5, 3)):
                self.top_grid.setColumnStretch(index, stretch)
            self.body_grid.addWidget(self.region_card, 0, 0)
            self.body_grid.addWidget(self.output_card, 0, 1)
            self.body_grid.setColumnStretch(0, 55)
            self.body_grid.setColumnStretch(1, 45)
        else:
            self.top_grid.setColumnStretch(0, 1)
            self.body_grid.addWidget(self.region_card, 0, 0)
            self.body_grid.addWidget(self.output_card, 1, 0)
            self.body_grid.setColumnStretch(0, 1)

    def _provider_icon(self, provider: str):
        return get_provider_icon(provider, palette_for(self)['text'], 20)

    def _update_provider_icons(self):
        for i in range(self.provider_combo.count()):
            provider = self.provider_combo.itemData(i)
            if provider:
                self.provider_combo.setItemIcon(i, self._provider_icon(provider))

    def apply_theme(self, theme):
        apply_widget_theme(self, theme)
        self._update_provider_icons()

    def set_provider_choices(self, providers):
        current = self.provider_combo.currentData()
        with QSignalBlocker(self.provider_combo):
            self.provider_combo.clear()
            for provider in providers:
                self.provider_combo.addItem(self._provider_icon(provider), provider, provider)
            self.provider_combo.setCurrentIndex(self.provider_combo.findData(current))

    def _on_provider_changed(self, index):
        provider = self.provider_combo.itemData(index)
        if provider:
            self.provider_changed.emit(provider)

    def _render_subtitle_preview(self):
        blocks = self._subtitle_state.overlay_mode == 'blocks'
        background = TOKENS['surface'] if blocks else TOKENS['preview']
        set_style(self.subtitle_preview_frame, f'QFrame#subtitlePreviewFrame {{background:{background};border:1px solid {TOKENS["border"]};border-radius:8px;}}')
        if self._subtitle_state.overlay_mode == 'blocks':
            self.subtitle_preview.setText('Đang dùng bản dịch tại vị trí chữ')
            set_style(self.subtitle_preview, text_style('caption') + 'padding:12px;background:transparent;')
        else:
            pairs = getattr(self._presentation, 'pairs', ())
            self.subtitle_preview.setText('\n'.join(pair.translated_text for pair in pairs) or 'Chưa có bản dịch được hiển thị')
            if pairs:
                set_style(self.subtitle_preview, subtitle_preview_style(self._subtitle_state, compact=True))
            else:
                set_style(self.subtitle_preview, text_style('body', color=TOKENS['preview_text']) + 'padding:12px;background:transparent;')

    def widget(self):
        return self.scroll_area.widget()

    def horizontalScrollBar(self):
        return self.scroll_area.horizontalScrollBar()

    def verticalScrollBar(self):
        return self.scroll_area.verticalScrollBar()

    def viewport(self):
        return self.scroll_area.viewport()

    def ensureWidgetVisible(self, childWidget, xMargin=50, yMargin=50):
        return self.scroll_area.ensureWidgetVisible(childWidget, xMargin, yMargin)

    def _init_source_languages(self, snapshot: ControllerSnapshot):
        blocker = QSignalBlocker(self.src_combo)
        self.src_combo.clear()
        choices = snapshot.ocr.source_choices
        if choices:
            for choice in choices:
                label = SOURCE_LANGUAGE_LABELS.get(choice.config_name, choice.label)
                self.src_combo.addItem(label, choice.config_name)
        else:
            for name in ('English', 'Japanese'):
                label = SOURCE_LANGUAGE_LABELS.get(name, name)
                self.src_combo.addItem(label, name)

        current = snapshot.ocr.source
        idx = self.src_combo.findData(current)
        if idx >= 0:
            self.src_combo.setCurrentIndex(idx)

    def _init_target_languages(self, snapshot: ControllerSnapshot):
        blocker = QSignalBlocker(self.tgt_combo)
        self.tgt_combo.clear()
        for name in ('Vietnamese', 'English'):
            label = TARGET_LANGUAGE_LABELS.get(name, name)
            self.tgt_combo.addItem(label, name)

        current = snapshot.ocr.target
        idx = self.tgt_combo.findData(current)
        if idx >= 0:
            self.tgt_combo.setCurrentIndex(idx)

    def _on_source_combo_changed(self, index: int):
        data = self.src_combo.itemData(index)
        if data:
            self.source_changed.emit(str(data))

    def _on_target_combo_changed(self, index: int):
        data = self.tgt_combo.itemData(index)
        if data:
            self.target_changed.emit(str(data))

    def _on_primary_clicked(self):
        self.toggle_requested.emit()

    def _on_readiness_action_clicked(self):
        if self._current_readiness_action:
            self.readiness_action_requested.emit(self._current_readiness_action)

    def _toggle_details(self):
        if self.details_container.isHidden():
            self.details_container.show()
            self.details_toggle_btn.setText("▾ Chi tiết")
        else:
            self.details_container.hide()
            self.details_toggle_btn.setText("▸ Chi tiết")

    def is_details_expanded(self) -> bool:
        return not self.details_container.isHidden()

    def render_daily(
        self,
        snapshot: ControllerSnapshot,
        readiness: DailyReadiness,
        run_state: DailyRunState
    ) -> None:
        self.render_summary(snapshot)

        # 4. Primary Button state
        phase = run_state.phase
        self._is_running_phase = phase in ('running', 'starting', 'waiting_source')

        if phase == 'stopped':
            self.primary_btn.setText("Bắt đầu dịch")
            set_theme_icon(self.primary_btn, 'play', 'primary_text', 16)
            set_style(self.primary_btn, button_style('primary', 'tokens'))
            self.primary_btn.setEnabled(readiness.ready and run_state.can_toggle)
        elif self._is_running_phase:
            self.primary_btn.setText("Dừng dịch")
            set_theme_icon(self.primary_btn, 'square', 'negative', 15)
            set_style(self.primary_btn, button_style('stop', 'tokens'))
            self.primary_btn.setEnabled(run_state.can_toggle)
        elif phase == 'stopping':
            self.primary_btn.setText("Đang dừng...")
            set_style(self.primary_btn, button_style('stopping', 'tokens'))
            self.primary_btn.setEnabled(False)

        # 5. Readiness Status Line
        color = TOKENS['positive'] if phase == 'running' else (
            TOKENS['warning'] if phase in ('starting', 'waiting_source') or not readiness.ready
            else TOKENS['muted']
        )
        msg = run_state.message or readiness.reason
        self.readiness_lbl.setText(f"● {msg}")
        set_style(self.readiness_lbl, f"font-size: 12px; color: {color};")

        # 6. Action button for readiness repair
        if not readiness.ready and readiness.action and phase == 'stopped':
            self._current_readiness_action = readiness.action
            action_labels = {
                'select_source': 'Chọn nguồn',
                'select_regions': 'Chọn vùng đọc',
                'manage_packs': 'Quản lý gói ngôn ngữ',
                'configure_provider': 'Cấu hình công cụ dịch',
            }
            self.readiness_action_btn.setText(action_labels.get(readiness.action, 'Khắc phục'))
            self.readiness_action_btn.show()
        else:
            self._current_readiness_action = None
            self.readiness_action_btn.hide()

        # 7. Preview refresh button availability
        self.refresh_preview_btn.setEnabled(run_state.preview_enabled)
        if not run_state.preview_enabled:
            self.refresh_preview_btn.setToolTip("Không thể làm mới ảnh khi đang dịch hoặc đang thao tác vùng")
        else:
            self.refresh_preview_btn.setToolTip("Chụp lại ảnh tĩnh từ nguồn hiện tại")


    def render_presented(
        self,
        presentation: PresentedTranslation | None,
        region_labels: dict[str, str] | None = None
    ) -> None:
        self._presentation = presentation
        self.output_widget.render(presentation, region_labels)
        self._render_subtitle_preview()

    def set_capture_snapshot(self, image: Any | None, profile: Any | None, context: Any | None, *, captured_at: str = '') -> None:
        self.snapshot_widget.set_snapshot(image, profile, context)
        self.snapshot_status_label.setText('Ảnh chụp xem trước' + (' • ' + captured_at if captured_at else ''))

    def clear_capture_snapshot(self, placeholder_text: str = "Ban đầu: Chọn nguồn để xem trước") -> None:
        self.snapshot_widget.clear_snapshot(placeholder_text)
        self.snapshot_status_label.setText('Ảnh chụp xem trước')

    def render_summary(self, snapshot: ControllerSnapshot):
        # 1. Update languages with signal blocker
        with QSignalBlocker(self.src_combo):
            if snapshot.ocr.source_choices:
                current_choices = [self.src_combo.itemData(i) for i in range(self.src_combo.count())]
                new_choices = [c.config_name for c in snapshot.ocr.source_choices]
                if current_choices != new_choices:
                    self.src_combo.clear()
                    for choice in snapshot.ocr.source_choices:
                        label = SOURCE_LANGUAGE_LABELS.get(choice.config_name, choice.label)
                        self.src_combo.addItem(label, choice.config_name)
            idx_src = self.src_combo.findData(snapshot.ocr.source)
            if idx_src >= 0 and self.src_combo.currentIndex() != idx_src:
                self.src_combo.setCurrentIndex(idx_src)

        with QSignalBlocker(self.tgt_combo):
            idx_tgt = self.tgt_combo.findData(snapshot.ocr.target)
            if idx_tgt >= 0 and self.tgt_combo.currentIndex() != idx_tgt:
                self.tgt_combo.setCurrentIndex(idx_tgt)

        # 2. Update region info label
        reg = snapshot.ocr.region
        if reg:
            self.region_info_lbl.setText(f"{reg[2]} × {reg[3]} px")
        else:
            self.region_info_lbl.setText("Chưa chọn vùng")

        # 3. Update provider / subtitle summary
        mode_text = "Phụ đề nổi" if snapshot.subtitle.overlay_mode == 'subtitle' else "Khối tại chỗ (Blocks)"
        self._subtitle_state = snapshot.subtitle
        self.session_info.setText(f'OCR trên máy · Chu kỳ quét {snapshot.ocr.interval_ms} ms · {mode_text}')
        with QSignalBlocker(self.provider_combo):
            self.provider_combo.setCurrentIndex(self.provider_combo.findData(snapshot.ai.provider))
        self._render_subtitle_preview()

    def set_run_status(self, text: str):
        self.readiness_lbl.setText(text)

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
        google = status.provider == "Google Translate"
        paused = google and status.phase == "paused"
        waiting = google and status.phase == "retry_wait"

        self.retry_translation_btn.setVisible(paused)
        self.retry_translation_btn.setEnabled(paused)
        self.translation_message.setVisible(paused or waiting)

        if paused:
            self.translation_message.setText("Tạm dừng dịch Google. OCR vẫn đang quét. Bấm Thử lại để tiếp tục.")
            self.set_run_status("Tạm dừng dịch Google")
        elif waiting:
            remaining = max(0, math.ceil((status.retry_at_s or now_s) - now_s))
            self.translation_message.setText(
                f"Google Translate: chờ {remaining} giây trước khi thử lại (lượt {status.retries_issued}/3)."
            )
            self.set_run_status("Chờ thử lại Google")
        elif status.phase == "stopped":
            self.set_run_status("Đã dừng")
        else:
            self.set_run_status("Đang hoạt động")

        if waiting:
            self._countdown.start()
        else:
            self._countdown.stop()
