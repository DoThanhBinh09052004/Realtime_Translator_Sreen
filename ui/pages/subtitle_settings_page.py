from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSlider, QPushButton, QFrame, QColorDialog, QBoxLayout, QLayout
from PyQt5.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from ui.widgets.capture_snapshot import CaptureSnapshotWidget
from ui.widgets.cards import ModernCard
from ui.styles import TOKENS, set_style, apply_widget_theme
from ui.presentation import subtitle_preview_style, color_button_presentation, drag_button_style
from ui.controller_state import SubtitlePageState
from core.blocks.models import Rect, ScreenMapping, CaptureGeometry, OverlayFrame, OverlayBlock
from ui.block_layout import layout_blocks, paint_blocks


class SubtitleSettingsPage(QScrollArea):
    style_changed = pyqtSignal(dict)
    preset_changed = pyqtSignal(str)
    drag_toggle_requested = pyqtSignal()
    mode_changed = pyqtSignal(str)
    preview_requested = pyqtSignal()

    def __init__(self, state: SubtitlePageState, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self._presentation = None
        self._captured_at = ''
        self.columns = QBoxLayout(QBoxLayout.LeftToRight)
        layout.addLayout(self.columns)
        inspector = QWidget()
        controls = QVBoxLayout(inspector)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(14)
        controls.setSizeConstraint(QLayout.SetMinimumSize)
        self.columns.addWidget(inspector, 36)
        mode_card = ModernCard('Cách hiển thị bản dịch', 'Chọn phụ đề hoặc phủ bản dịch lên vị trí chữ gốc')
        self.mode_combo = QComboBox()
        self.mode_combo.addItem('Phụ đề nổi', 'subtitle')
        self.mode_combo.addItem('Theo vị trí chữ', 'blocks')
        self.mode_combo.currentIndexChanged.connect(lambda: self.mode_changed.emit(self.mode_combo.currentData()))
        mode_card.layout.addWidget(self.mode_combo)
        self.capture_warning = QLabel('Overlay theo vị trí chữ có thể không xuất hiện trong ảnh chụp hoặc bản ghi hình.')
        self.capture_warning.setWordWrap(True)
        mode_card.layout.addWidget(self.capture_warning)
        controls.addWidget(mode_card)

        # Card 1: Colors & Typography
        style_card = ModernCard("Màu sắc & Kích thước Chữ", "Tùy biến diện mạo hộp phụ đề nổi trên game")
        
        color_row = QHBoxLayout()
        color_row.setSpacing(12)

        # BG Color Picker
        bg_col = QVBoxLayout()
        bg_col.setSpacing(4)
        bg_lbl = QLabel("Màu nền (Background)")
        set_style(bg_lbl, f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};")
        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setFixedHeight(38)
        self.bg_color_btn.setCursor(Qt.PointingHandCursor)
        self._update_color_btn_style(self.bg_color_btn, state.bg_color)
        self.bg_color_btn.clicked.connect(self.pick_bg_color)
        bg_col.addWidget(bg_lbl)
        bg_col.addWidget(self.bg_color_btn)
        color_row.addLayout(bg_col)

        # Text Color Picker
        txt_col = QVBoxLayout()
        txt_col.setSpacing(4)
        txt_lbl = QLabel("Màu chữ (Text)")
        set_style(txt_lbl, f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};")
        self.text_color_btn = QPushButton()
        self.text_color_btn.setFixedHeight(38)
        self.text_color_btn.setCursor(Qt.PointingHandCursor)
        self._update_color_btn_style(self.text_color_btn, state.text_color)
        self.text_color_btn.clicked.connect(self.pick_text_color)
        txt_col.addWidget(txt_lbl)
        txt_col.addWidget(self.text_color_btn)
        color_row.addLayout(txt_col)

        style_card.layout.addLayout(color_row)
        style_card.layout.addSpacing(6)

        # Font Size Slider
        font_header = QHBoxLayout()
        font_lbl = QLabel("Cỡ chữ phụ đề (Font Size)")
        self.font_label = font_lbl
        set_style(font_lbl, f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};")
        self.font_size_val_lbl = QLabel(f"{state.font_size}px")
        set_style(self.font_size_val_lbl, f"font-size: 12px; font-weight: 600; color: {TOKENS['focus']};")
        font_header.addWidget(font_lbl)
        font_header.addStretch()
        font_header.addWidget(self.font_size_val_lbl)
        style_card.layout.addLayout(font_header)

        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(14, 36)
        self.font_size_slider.setValue(state.font_size)
        set_style(self.font_size_slider, f"""
            QSlider::groove:horizontal {{
                height: 5px;
                background: {TOKENS['input']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {TOKENS['focus']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {TOKENS['text']};
                border: 1px solid {TOKENS['focus']};
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }}
        """)
        self.font_size_slider.valueChanged.connect(lambda value: self.style_changed.emit({"font_size": value}))
        style_card.layout.addWidget(self.font_size_slider)
        style_card.layout.addSpacing(6)

        # Opacity Slider
        opacity_header = QHBoxLayout()
        op_lbl = QLabel("Độ trong suốt nền (Background Opacity)")
        set_style(op_lbl, f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};")
        self.opacity_val_lbl = QLabel(f"{state.bg_opacity}%")
        set_style(self.opacity_val_lbl, f"font-size: 12px; font-weight: 600; color: {TOKENS['focus']};")
        opacity_header.addWidget(op_lbl)
        opacity_header.addStretch()
        opacity_header.addWidget(self.opacity_val_lbl)
        style_card.layout.addLayout(opacity_header)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(state.bg_opacity)
        set_style(self.opacity_slider, f"""
            QSlider::groove:horizontal {{
                height: 5px;
                background: {TOKENS['input']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {TOKENS['focus']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {TOKENS['text']};
                border: 1px solid {TOKENS['focus']};
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }}
        """)
        self.opacity_slider.valueChanged.connect(lambda value: self.style_changed.emit({"bg_opacity": value}))
        style_card.layout.addWidget(self.opacity_slider)

        controls.addWidget(style_card)

        # Card 2: Position & Drag Mode
        pos_card = ModernCard("Vị trí & Định vị Màn hình", "Chọn vị trí xuất hiện cố định hoặc tự do kéo thả phụ đề")
        
        pos_row = QHBoxLayout()
        pos_row.setSpacing(12)

        # Preset Dropdown
        preset_box = QVBoxLayout()
        preset_box.setSpacing(4)
        preset_lbl = QLabel("Vị trí hiển thị (Preset)")
        set_style(preset_lbl, f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};")
        self.preset_combo = QComboBox()
        self.preset_combo.setFixedHeight(38)
        self.preset_combo.addItem("Dưới giữa (Mặc định)", "bottom_center")
        self.preset_combo.addItem("Trên giữa (Top Center)", "top_center")
        self.preset_combo.addItem("Dưới trái (Bottom Left)", "bottom_left")
        self.preset_combo.addItem("Vị trí tùy chọn (Custom)", "custom")

        idx = self.preset_combo.findData(state.preset)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.currentIndexChanged.connect(lambda: self.preset_changed.emit(self.preset_combo.currentData()))

        preset_box.addWidget(preset_lbl)
        preset_box.addWidget(self.preset_combo)
        pos_row.addLayout(preset_box)

        pos_card.layout.addLayout(pos_row)
        pos_card.layout.addSpacing(8)

        # Drag Mode Action Button
        self.drag_toggle_btn = QPushButton()
        self.drag_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.set_drag_mode(False)
        self.drag_toggle_btn.clicked.connect(self.drag_toggle_requested.emit)
        pos_card.layout.addWidget(self.drag_toggle_btn)

        controls.addWidget(pos_card)

        controls.addStretch()
        preview_card = ModernCard('Xem trước phụ đề', 'Ảnh chụp nguồn đang chọn • làm mới thủ công')
        self.snapshot_widget = CaptureSnapshotWidget(show_regions=False)
        self.snapshot_widget.setMinimumHeight(280)
        self.preview_status_label = QLabel()
        self.preview_status_label.setWordWrap(True)
        self.refresh_preview_btn = QPushButton('Làm mới ảnh')
        self.refresh_preview_btn.clicked.connect(self.preview_requested.emit)
        preview_card.layout.addWidget(self.snapshot_widget, 1)
        preview_card.layout.addWidget(self.preview_status_label)
        preview_card.layout.addWidget(self.refresh_preview_btn)
        self.columns.addWidget(preview_card, 64)
        self.clear_capture_snapshot()

        layout.addStretch()
        self.setWidget(content)
        self.render(state)

    def render(self, state: SubtitlePageState):
        self._state = state
        blockers = [QSignalBlocker(widget) for widget in (self.font_size_slider, self.opacity_slider, self.preset_combo, self.mode_combo)]
        blocks = state.overlay_mode == 'blocks'
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(state.overlay_mode))
        self.capture_warning.setVisible(blocks)
        self.preset_combo.setEnabled(not blocks)
        self.drag_toggle_btn.setEnabled(not blocks)
        self.font_label.setText('Cỡ chữ tối đa' if blocks else 'Cỡ chữ phụ đề (Font Size)')
        self.font_size_slider.setValue(state.font_size)
        self.opacity_slider.setValue(state.bg_opacity)
        self.font_size_val_lbl.setText(f'{state.font_size}px')
        self.opacity_val_lbl.setText(f'{state.bg_opacity}%')
        self.set_preset_display(state.preset)
        self._update_color_btn_style(self.bg_color_btn, state.bg_color)
        self._update_color_btn_style(self.text_color_btn, state.text_color)
        self._update_preview()
        del blockers

    def set_capture_snapshot(self, image, profile, context, *, captured_at=''):
        self._captured_at = captured_at
        self.snapshot_widget.set_snapshot(image, profile, context)
        self._update_preview()

    def clear_capture_snapshot(self, message=''):
        message = message or 'Chọn nguồn chụp ở Tổng quan, sau đó bấm Làm mới ảnh.'
        self.snapshot_widget.clear_snapshot(message)
        self.preview_status_label.setText(message)

    def set_preview_state(self, enabled, message=''):
        self.refresh_preview_btn.setEnabled(enabled)
        self.refresh_preview_btn.setToolTip(message)

    def render_presented(self, presentation, region_labels=None):
        self._presentation = presentation
        self._update_preview()

    def _update_preview(self):
        from ui.presentation import preview_position
        text = '\n'.join(pair.translated_text for pair in self._presentation.pairs) if self._presentation else ''
        position = preview_position(self._state, self.snapshot_widget._context)
        self.snapshot_widget.set_overlay_preview(self._state, text or 'Xin chào, nhà lữ hành!', normalized_position=position)
        if self.snapshot_widget._image is not None:
            label = 'Bản dịch gần nhất' if text else 'Văn bản mẫu'
            if self._state.overlay_mode == 'blocks':
                label = 'Minh họa bố cục khối'
            elif position is None:
                label += ' • Minh họa kiểu chữ, không mô phỏng vị trí'
            if self._state.overlay_mode != 'blocks' and position is not None:
                label += ' • Vị trí tương đối trên ảnh'
            self.preview_status_label.setText(label + ' • ' + self._captured_at)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_layout(self.viewport().width())

    def _reflow_layout(self, width):
        self.columns.setDirection(QBoxLayout.LeftToRight if width >= 800 else QBoxLayout.TopToBottom)

    def set_preset_display(self, preset: str):
        blocker = QSignalBlocker(self.preset_combo)
        index = self.preset_combo.findData(preset)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        del blocker

    def set_drag_mode(self, enabled: bool):
        self.drag_toggle_btn.setText('✓ Đã xong (Khóa vị trí phụ đề)' if enabled else '✥ Di chuyển phụ đề trên màn hình')
        set_style(self.drag_toggle_btn, drag_button_style(enabled))

    def _update_color_btn_style(self, button, color):
        text, style = color_button_presentation(color)
        button.setText(text)
        set_style(button, style)

    def pick_bg_color(self):
        color = QColorDialog.getColor(QColor(self._state.bg_color), self, 'Chọn màu nền phụ đề')
        if color.isValid():
            self.style_changed.emit({'bg_color': color.name()})

    def pick_text_color(self):
        color = QColorDialog.getColor(QColor(self._state.text_color), self, 'Chọn màu chữ phụ đề')
        if color.isValid():
            self.style_changed.emit({'text_color': color.name()})

    def apply_theme(self, theme: str):
        apply_widget_theme(self, theme)
