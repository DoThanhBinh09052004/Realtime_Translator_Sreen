"""Focused daily translation screen (Screen A)."""
import math
import time
from typing import Any
from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QLayout, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QPlainTextEdit, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, QTimer, QSignalBlocker, pyqtSignal

from ui.widgets.cards import ModernCard, MetricCard
from ui.widgets.capture_snapshot import CaptureSnapshotWidget
from ui.widgets.translation_output import TranslationOutputWidget
from ui.capture_settings import CaptureSettings
from ui.styles import (
    CYBER_PALETTE, HERO_START_STYLE, HERO_STOP_STYLE, HERO_STOPPING_STYLE,
    SECONDARY_BUTTON_STYLE
)
from ui.icons import get_lucide_icon
from ui.controller_state import ControllerSnapshot, DailyReadiness, DailyRunState, PresentedTranslation


SOURCE_LANGUAGE_LABELS = {
    'English': 'Tiếng Anh (English)',
    'Japanese': 'Tiếng Nhật (Japanese)',
    'Korean': 'Tiếng Hàn (Korean)',
    'Chinese': 'Tiếng Trung (Chinese)',
}

TARGET_LANGUAGE_LABELS = {
    'Vietnamese': 'Tiếng Việt (Vietnamese)',
    'English': 'Tiếng Anh (English)',
}


class ConsolePage(QWidget):
    source_changed = pyqtSignal(str)
    target_changed = pyqtSignal(str)
    toggle_requested = pyqtSignal()
    preview_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    readiness_action_requested = pyqtSignal(str)
    select_region_requested = pyqtSignal()
    subtitle_settings_requested = pyqtSignal()
    retry_translation_requested = pyqtSignal()

    # Retained for legacy test / embedding compatibility
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, snapshot: ControllerSnapshot, parent=None):
        super().__init__(parent)

        self._translation_status = None
        self._current_readiness_action: str | None = None
        self._is_running_phase: bool = False
        self._metric_status_text: str = "Đã dừng"

        self._countdown = QTimer(self)
        self._countdown.setInterval(500)
        self._countdown.timeout.connect(self._refresh_countdown)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(12)

        # 1. Header Row
        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        title_lbl = QLabel("Translate HUD")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        desc_lbl = QLabel("Dịch chữ trong game")
        desc_lbl.setStyleSheet(f"font-size: 12px; color: {CYBER_PALETTE['text_muted']};")
        header_text.addWidget(title_lbl)
        header_text.addWidget(desc_lbl)
        header_row.addLayout(header_text)
        header_row.addStretch()

        self.settings_btn = QPushButton("Thiết lập")
        self.settings_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setIcon(get_lucide_icon("settings", color=CYBER_PALETTE['text_muted'], size=14))
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        header_row.addWidget(self.settings_btn)
        layout.addLayout(header_row)

        # 2. Languages Row
        lang_card = ModernCard("Ngôn ngữ", "Chọn ngôn ngữ hiển thị trong game và ngôn ngữ dịch sang")
        lang_row = QHBoxLayout()
        lang_row.setSpacing(12)

        src_box = QVBoxLayout()
        src_box.setSpacing(4)
        src_lbl = QLabel("Ngôn ngữ nguồn")
        src_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.src_combo = QComboBox()
        self.src_combo.setAccessibleName("Ngôn ngữ nguồn")
        self.src_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._init_source_languages(snapshot)
        self.src_combo.currentIndexChanged.connect(self._on_source_combo_changed)
        src_box.addWidget(src_lbl)
        src_box.addWidget(self.src_combo)
        lang_row.addLayout(src_box, stretch=1)

        arrow_lbl = QLabel("→")
        arrow_lbl.setAlignment(Qt.AlignCenter)
        arrow_lbl.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {CYBER_PALETTE['neon_indigo']}; margin-top: 16px;")
        lang_row.addWidget(arrow_lbl)

        tgt_box = QVBoxLayout()
        tgt_box.setSpacing(4)
        tgt_lbl = QLabel("Dịch sang")
        tgt_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.tgt_combo = QComboBox()
        self.tgt_combo.setAccessibleName("Dịch sang")
        self.tgt_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._init_target_languages(snapshot)
        self.tgt_combo.currentIndexChanged.connect(self._on_target_combo_changed)
        tgt_box.addWidget(tgt_lbl)
        tgt_box.addWidget(self.tgt_combo)
        lang_row.addLayout(tgt_box, stretch=1)

        lang_card.layout.addLayout(lang_row)
        layout.addWidget(lang_card)

        # 3. Capture Source Card
        source_card = ModernCard("Nguồn chụp", "Chọn màn hình hoặc cửa sổ game cần quét chữ")
        self.capture_settings = CaptureSettings(parent=self)
        source_card.layout.addWidget(self.capture_settings)
        layout.addWidget(source_card)

        # 4. OCR Region Card with Snapshot Preview
        region_card = ModernCard("Vùng đọc chữ", "Tọa độ và khung hình quét chữ OCR")
        reg_header_row = QHBoxLayout()
        self.region_info_lbl = QLabel("Vùng đọc chữ · Chưa chọn vùng")
        self.region_info_lbl.setStyleSheet("font-size: 12.5px; font-weight: 500;")
        self.region_info_lbl.setWordWrap(True)
        self.region_info_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        reg_header_row.addWidget(self.region_info_lbl)
        reg_header_row.addStretch()

        self.select_region_btn = QPushButton("Chọn vùng đọc")
        self.select_region_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.select_region_btn.setCursor(Qt.PointingHandCursor)
        self.select_region_btn.setIcon(get_lucide_icon("scan", color=CYBER_PALETTE['text_muted'], size=14))
        self.select_region_btn.clicked.connect(self.select_region_requested.emit)
        reg_header_row.addWidget(self.select_region_btn)
        region_card.layout.addLayout(reg_header_row)

        self.snapshot_widget = CaptureSnapshotWidget(self)
        region_card.layout.addWidget(self.snapshot_widget)

        preview_footer = QHBoxLayout()
        preview_notice = QLabel("Ảnh xem trước, không phải video"); preview_notice.setWordWrap(True); preview_notice.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        preview_notice.setStyleSheet(f"font-size: 11.5px; color: {CYBER_PALETTE['text_muted']};")
        preview_footer.addWidget(preview_notice)
        preview_footer.addStretch()

        self.refresh_preview_btn = QPushButton("Làm mới ảnh")
        self.refresh_preview_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.refresh_preview_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_preview_btn.setIcon(get_lucide_icon("refresh-cw", color=CYBER_PALETTE['text_muted'], size=13))
        self.refresh_preview_btn.clicked.connect(self.preview_requested.emit)
        preview_footer.addWidget(self.refresh_preview_btn)
        region_card.layout.addLayout(preview_footer)
        layout.addWidget(region_card)

        # 5. Translation Engine & Presentation Card
        engine_card = ModernCard("Hiển thị & Công cụ", "Công cụ AI và chế độ hiển thị phụ đề")
        eng_row = QHBoxLayout()
        self.provider_summary_lbl = QLabel(f"{snapshot.ai.provider} · {snapshot.subtitle.overlay_mode}")
        self.provider_summary_lbl.setStyleSheet("font-size: 12.5px; font-weight: 500;")
        self.provider_summary_lbl.setWordWrap(True)
        self.provider_summary_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        eng_row.addWidget(self.provider_summary_lbl)
        eng_row.addStretch()

        self.customize_btn = QPushButton("Tùy chỉnh")
        self.customize_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.customize_btn.setCursor(Qt.PointingHandCursor)
        self.customize_btn.setIcon(get_lucide_icon("sliders", color=CYBER_PALETTE['text_muted'], size=13))
        self.customize_btn.clicked.connect(self.subtitle_settings_requested.emit)
        eng_row.addWidget(self.customize_btn)
        self.subtitle_settings_btn = self.customize_btn
        engine_card.layout.addLayout(eng_row)
        layout.addWidget(engine_card)



        # 7. Translation Output Display
        output_card = ModernCard("Bản dịch Hiển thị", "Cặp chữ gốc và bản dịch mới nhất được hiển thị trên màn hình")
        self.output_widget = TranslationOutputWidget(self)
        output_card.layout.addWidget(self.output_widget)
        layout.addWidget(output_card)

        # 8. Collapsible Details Section (Bounded Log & Log Clear)
        self.details_toggle_btn = QPushButton("▸ Chi tiết")
        self.details_toggle_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {CYBER_PALETTE['text_muted']}; border: none; text-align: left; font-size: 12px; font-weight: 600; padding: 4px; }}"
            f"QPushButton:hover {{ color: {CYBER_PALETTE['text_primary']}; }}"
        )
        self.details_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.details_toggle_btn.clicked.connect(self._toggle_details)
        layout.addWidget(self.details_toggle_btn)

        self.details_container = QWidget()
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(6)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(300)
        self.log_view.setPlaceholderText("Nhật ký sẽ xuất hiện khi bắt đầu quét.")
        self.log_view.setMinimumHeight(100)
        self.log_view.setMaximumHeight(160)
        details_layout.addWidget(self.log_view)

        log_btn_row = QHBoxLayout()
        log_btn_row.addStretch()
        self.clear_log_btn = QPushButton("Xóa nhật ký")
        self.clear_log_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.clear_log_btn.setCursor(Qt.PointingHandCursor)
        self.clear_log_btn.clicked.connect(self.log_view.clear)
        log_btn_row.addWidget(self.clear_log_btn)
        details_layout.addLayout(log_btn_row)

        self.details_container.hide()
        layout.addWidget(self.details_container)

        # Retained compatibility metric_cards dict
        self.metric_cards = {
            "status": MetricCard("TRẠNG THÁI", "Đã dừng", icon_name="activity", icon_color=CYBER_PALETTE['neon_rose']),
            "ai": MetricCard("CÔNG CỤ DỊCH", snapshot.ai.provider, icon_name="cpu", icon_color=CYBER_PALETTE['neon_indigo']),
            "lang": MetricCard("NGÔN NGỮ", f"{snapshot.ocr.source} -> {snapshot.ocr.target}", icon_name="languages", icon_color=CYBER_PALETTE['text_muted']),
            "region": MetricCard("VÙNG QUÉT OCR", "Chưa chọn vùng", icon_name="maximize-2", icon_color=CYBER_PALETTE['text_muted'])
        }

        self.render_summary(snapshot)
        layout.addStretch()
        self.scroll_area.setWidget(content)
        root_layout.addWidget(self.scroll_area, stretch=1)

        # Fixed Footer: Primary Action & Readiness Controls
        hero_card = ModernCard("Điều khiển Dịch thuật", "Bật hoặc dừng tiến trình quét OCR và dịch màn hình")
        self.hero_card = hero_card
        self.primary_btn = QPushButton("▶ BẮT ĐẦU DỊCH")
        self.primary_btn.setFixedHeight(44)
        self.primary_btn.setCursor(Qt.PointingHandCursor)
        self.primary_btn.setStyleSheet(HERO_START_STYLE)
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        hero_card.layout.addWidget(self.primary_btn)

        # Backward compatibility buttons
        self.start_btn = self.primary_btn
        self.stop_btn = self.primary_btn

        readiness_row = QHBoxLayout()
        self.readiness_lbl = QLabel("● Chưa sẵn sàng")
        self.readiness_lbl.setStyleSheet(f"font-size: 12px; color: {CYBER_PALETTE['text_muted']};")
        self.readiness_lbl.setWordWrap(True)
        readiness_row.addWidget(self.readiness_lbl, stretch=1)

        self.readiness_action_btn = QPushButton("Khắc phục")
        self.readiness_action_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.readiness_action_btn.setCursor(Qt.PointingHandCursor)
        self.readiness_action_btn.clicked.connect(self._on_readiness_action_clicked)
        self.readiness_action_btn.hide()
        readiness_row.addWidget(self.readiness_action_btn)
        hero_card.layout.addLayout(readiness_row)

        # Translation recovery (Google Translate pause/wait) - outside Details
        recovery_row = QHBoxLayout()
        self.translation_message = QLabel()
        self.translation_message.setWordWrap(True)
        self.translation_message.hide()
        recovery_row.addWidget(self.translation_message, stretch=1)

        self.retry_translation_btn = QPushButton("Thử lại")
        self.retry_translation_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.retry_translation_btn.setCursor(Qt.PointingHandCursor)
        self.retry_translation_btn.clicked.connect(self.retry_translation_requested.emit)
        self.retry_translation_btn.hide()
        recovery_row.addWidget(self.retry_translation_btn)
        hero_card.layout.addLayout(recovery_row)

        root_layout.addWidget(hero_card, stretch=0)

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
            self.region_info_lbl.setText(f"Vùng đọc chữ · {reg[2]} × {reg[3]} px")
        else:
            self.region_info_lbl.setText("Vùng đọc chữ · Chưa chọn vùng")

        # 3. Update provider / subtitle summary
        mode_text = "Phụ đề nổi" if snapshot.subtitle.overlay_mode == 'subtitle' else "Khối tại chỗ (Blocks)"
        self.provider_summary_lbl.setText(f"{snapshot.ai.provider} · {mode_text}")

        # 4. Primary Button state
        phase = run_state.phase
        self._is_running_phase = phase in ('running', 'starting', 'waiting_source')

        if phase == 'stopped':
            self.primary_btn.setText("▶ BẮT ĐẦU DỊCH")
            self.primary_btn.setStyleSheet(HERO_START_STYLE)
            self.primary_btn.setEnabled(readiness.ready and run_state.can_toggle)
        elif self._is_running_phase:
            self.primary_btn.setText("■ DỪNG DỊCH")
            self.primary_btn.setStyleSheet(HERO_STOP_STYLE)
            self.primary_btn.setEnabled(run_state.can_toggle)
        elif phase == 'stopping':
            self.primary_btn.setText("Đang dừng...")
            self.primary_btn.setStyleSheet(HERO_STOPPING_STYLE)
            self.primary_btn.setEnabled(False)

        # 5. Readiness Status Line
        color = CYBER_PALETTE['neon_green'] if phase == 'running' else (
            CYBER_PALETTE['neon_amber'] if phase in ('starting', 'waiting_source') or not readiness.ready
            else CYBER_PALETTE['text_muted']
        )
        msg = run_state.message or readiness.reason
        self.readiness_lbl.setText(f"● {msg}")
        self.readiness_lbl.setStyleSheet(f"font-size: 12px; color: {color};")

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

        # Keep compatibility state in sync
        self.render_summary(snapshot)

    def render_presented(
        self,
        presentation: PresentedTranslation | None,
        region_labels: dict[str, str] | None = None
    ) -> None:
        self.output_widget.render(presentation, region_labels)

    def set_capture_snapshot(self, image: Any | None, profile: Any | None, context: Any | None) -> None:
        self.snapshot_widget.set_snapshot(image, profile, context)

    def clear_capture_snapshot(self, placeholder_text: str = "Ban đầu: Chọn nguồn để xem trước") -> None:
        self.snapshot_widget.clear_snapshot(placeholder_text)

    def render_summary(self, snapshot: ControllerSnapshot):
        model = f"\n{snapshot.ai.model_id}" if snapshot.ai.supports_models else ""
        if "ai" in self.metric_cards:
            self.metric_cards["ai"].set_value(snapshot.ai.provider + model)
        if "lang" in self.metric_cards:
            self.metric_cards["lang"].set_value(f"{snapshot.ocr.source} -> {snapshot.ocr.target}")
        region = snapshot.ocr.region
        if "region" in self.metric_cards:
            self.metric_cards["region"].set_value(f"{region[2]} x {region[3]} px" if region else "Chưa chọn vùng")
        if "status" in self.metric_cards:
            self.metric_cards["status"].set_value(self._metric_status_text)

    def set_run_status(self, text: str):
        self._metric_status_text = text
        if "status" in self.metric_cards:
            self.metric_cards["status"].set_value(text)

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
