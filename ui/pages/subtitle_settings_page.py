from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSlider, QPushButton, QFrame, QColorDialog
from PyQt5.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt5.QtGui import QColor
from ui.widgets.cards import ModernCard
from ui.styles import CYBER_PALETTE
from ui.presentation import subtitle_preview_style, color_button_presentation, drag_button_style
from ui.controller_state import SubtitlePageState


class SubtitleSettingsPage(QScrollArea):
    style_changed = pyqtSignal(dict)
    preset_changed = pyqtSignal(str)
    drag_toggle_requested = pyqtSignal()

    def __init__(self, state: SubtitlePageState, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

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
        self._update_color_btn_style(self.bg_color_btn, state.bg_color)
        self.bg_color_btn.clicked.connect(self.pick_bg_color)
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
        font_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.font_size_val_lbl = QLabel(f"{state.font_size}px")
        self.font_size_val_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {CYBER_PALETTE['neon_indigo']};")
        font_header.addWidget(font_lbl)
        font_header.addStretch()
        font_header.addWidget(self.font_size_val_lbl)
        style_card.layout.addLayout(font_header)

        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(14, 36)
        self.font_size_slider.setValue(state.font_size)
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
        self.font_size_slider.valueChanged.connect(lambda value: self.style_changed.emit({"font_size": value}))
        style_card.layout.addWidget(self.font_size_slider)
        style_card.layout.addSpacing(6)

        # Opacity Slider
        opacity_header = QHBoxLayout()
        op_lbl = QLabel("Độ trong suốt nền (Background Opacity)")
        op_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.opacity_val_lbl = QLabel(f"{state.bg_opacity}%")
        self.opacity_val_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {CYBER_PALETTE['neon_indigo']};")
        opacity_header.addWidget(op_lbl)
        opacity_header.addStretch()
        opacity_header.addWidget(self.opacity_val_lbl)
        style_card.layout.addLayout(opacity_header)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(state.bg_opacity)
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
        self.opacity_slider.valueChanged.connect(lambda value: self.style_changed.emit({"bg_opacity": value}))
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
        self.live_preview_box.setStyleSheet(subtitle_preview_style(state))

        sim_layout.addWidget(self.live_preview_box)
        preview_card.layout.addWidget(sim_container)

        layout.addWidget(preview_card)

        layout.addStretch()
        self.setWidget(content)
        self.render(state)

    def render(self, state: SubtitlePageState):
        self._state = state
        blockers = [QSignalBlocker(widget) for widget in (self.font_size_slider, self.opacity_slider, self.preset_combo)]
        self.font_size_slider.setValue(state.font_size)
        self.opacity_slider.setValue(state.bg_opacity)
        self.font_size_val_lbl.setText(f'{state.font_size}px')
        self.opacity_val_lbl.setText(f'{state.bg_opacity}%')
        self.set_preset_display(state.preset)
        self._update_color_btn_style(self.bg_color_btn, state.bg_color)
        self._update_color_btn_style(self.text_color_btn, state.text_color)
        self.live_preview_box.setStyleSheet(subtitle_preview_style(state))
        del blockers

    def set_preset_display(self, preset: str):
        blocker = QSignalBlocker(self.preset_combo)
        index = self.preset_combo.findData(preset)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        del blocker

    def set_drag_mode(self, enabled: bool):
        self.drag_toggle_btn.setText('✓ Đã xong (Khóa vị trí phụ đề)' if enabled else '✥ Di chuyển phụ đề trên màn hình')
        self.drag_toggle_btn.setStyleSheet(drag_button_style(enabled))

    def _update_color_btn_style(self, button, color):
        text, style = color_button_presentation(color)
        button.setText(text)
        button.setStyleSheet(style)

    def pick_bg_color(self):
        color = QColorDialog.getColor(QColor(self._state.bg_color), self, 'Chọn màu nền phụ đề')
        if color.isValid():
            self.style_changed.emit({'bg_color': color.name()})

    def pick_text_color(self):
        color = QColorDialog.getColor(QColor(self._state.text_color), self, 'Chọn màu chữ phụ đề')
        if color.isValid():
            self.style_changed.emit({'text_color': color.name()})
