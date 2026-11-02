import os
from PyQt5.QtCore import (
    Qt, QSignalBlocker, pyqtSignal,
    QEasingCurve, QPropertyAnimation, QParallelAnimationGroup
)
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton, QButtonGroup,
    QGraphicsOpacityEffect, QBoxLayout
)

from ui.styles import TOKENS, set_style, apply_widget_theme
from ui.icons import set_theme_icon
from ui.widgets.toggle_switch import ToggleSwitch


def resolve_display_threads(auto: bool, custom_threads: int, total_cores: int) -> int:
    if not auto:
        return max(1, min(total_cores, custom_threads))
    return max(2, min(6, total_cores // 2))


class OcrPerformanceCard(QFrame):
    """
    Card cài đặt Hiệu năng OCR & Tài nguyên máy
    Thiết kế theo chuẩn Linear / Raycast Dark Theme
    """
    mode_changed = pyqtSignal(str)
    auto_threads_changed = pyqtSignal(bool)
    threads_changed = pyqtSignal(int)

    def __init__(self, performance_mode: str = "high", auto_threads: bool = True, threads: int = 4, parent=None):
        super().__init__(parent)
        self.setObjectName("ocrPerformanceCard")
        set_style(self, f"""
            QFrame#ocrPerformanceCard {{
                background-color: {TOKENS['surface']};
                border: 1px solid {TOKENS['border']};
                border-radius: 12px;
            }}
        """)

        self.total_cores = max(1, os.cpu_count() or 4)
        self.performance_mode = performance_mode if performance_mode in ("high", "eco") else "high"
        self.auto_threads = bool(auto_threads)
        self.threads = max(1, min(self.total_cores, threads))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 18)
        main_layout.setSpacing(14)

        # ===== 1. Header =====
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        header_texts = QVBoxLayout()
        header_texts.setSpacing(4)
        title_lbl = QLabel("Hiệu năng OCR & tài nguyên máy")
        set_style(title_lbl, f"font-size: 16px; font-weight: 600; color: {TOKENS['text']};")
        desc_lbl = QLabel("Điều chỉnh tốc độ nhận diện và mức sử dụng CPU/RAM")
        set_style(desc_lbl, f"font-size: 12px; color: {TOKENS['muted']};")
        title_lbl.setWordWrap(True)
        desc_lbl.setWordWrap(True)
        header_texts.addWidget(title_lbl)
        header_texts.addWidget(desc_lbl)
        header_row.addLayout(header_texts, 1)
        main_layout.addLayout(header_row)

        # Two mutually exclusive modes in one segmented control.
        mode_bar = QFrame()
        mode_bar.setObjectName('performanceModeBar')
        set_style(mode_bar, "QFrame#performanceModeBar {background:@raised@;border:0;border-radius:10px;}")
        mode_row = QHBoxLayout(mode_bar)
        mode_row.setContentsMargins(3, 3, 3, 3)
        mode_row.setSpacing(3)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.high_button = QPushButton('Hiệu năng cao')
        self.eco_button = QPushButton('Tiết kiệm RAM')
        for button, mode, tip in (
            (self.high_button, 'high', 'OCR nhanh, dùng nhiều tài nguyên hơn'),
            (self.eco_button, 'eco', 'OCR chậm hơn, sử dụng ít tài nguyên hơn'),
        ):
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tip)
            set_style(button, """
                QPushButton {background:transparent;color:@muted@;border:1px solid transparent;
                    border-radius:7px;font-size:12px;padding:4px 8px;}
                QPushButton:hover {color:@text@;}
                QPushButton:checked {background:@selection_bg@;color:@selection_text@;
                    border:1px solid @focus@;font-weight:600;}
                QPushButton:focus {border:1px solid @focus@;}
            """)
            self.mode_group.addButton(button)
            button.clicked.connect(lambda checked=False, selected=mode: self._select_mode(selected))
            mode_row.addWidget(button, 1)
        main_layout.addWidget(mode_bar)

        # ===== 3. Đường kẻ phân cách =====
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        set_style(divider, f"background-color: {TOKENS['border']}; max-height: 1px;")
        main_layout.addWidget(divider)

        # ===== 4. Khu vực Phân bổ CPU =====
        cpu_header = QHBoxLayout()
        cpu_header.setSpacing(8)
        cpu_icon = QLabel()
        set_theme_icon(cpu_icon, 'cpu', 'muted', 16)
        cpu_header.addWidget(cpu_icon)

        cpu_title = QLabel("Phân bổ CPU")
        set_style(cpu_title, f"font-size: 13.5px; font-weight: 700; color: {TOKENS['text']};")
        cpu_header.addWidget(cpu_title)
        cpu_header.addStretch()
        main_layout.addLayout(cpu_header)

        # Sub-container chứa checkbox và spinbox
        cpu_box = QFrame()
        set_style(cpu_box, f"""
            QFrame {{
                background-color: {TOKENS['sidebar']};
                border: 1px solid {TOKENS['border']};
                border-radius: 8px;
            }}
        """)
        cpu_box_layout = QVBoxLayout(cpu_box)
        cpu_box_layout.setContentsMargins(14, 12, 14, 14)
        cpu_box_layout.setSpacing(12)

        # Hàng 1: Checkbox tự động + Badge trạng thái
        row1 = QBoxLayout(QBoxLayout.LeftToRight)
        self.cpu_row = row1
        self.auto_checkbox = ToggleSwitch("Tự động tối ưu số luồng CPU")

        self.auto_checkbox.setChecked(self.auto_threads)
        self.auto_checkbox.toggled.connect(self._on_auto_toggled)
        row1.addWidget(self.auto_checkbox)
        row1.addStretch()

        self.threads_badge = QLabel()
        set_style(self.threads_badge, f"""
            background-color: {TOKENS['selection_bg']};
            color: {TOKENS['selection_text']};
            border-radius: 5px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 600;
        """)
        row1.addWidget(self.threads_badge)
        cpu_box_layout.addLayout(row1)

        # Container chứa phần chỉnh số luồng thủ công (ẩn/hiện mượt mà)
        self.custom_threads_container = QFrame()
        set_style(self.custom_threads_container, "background: transparent; border: none;")
        custom_layout = QVBoxLayout(self.custom_threads_container)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(10)

        # Divider mờ bên trong
        inner_divider = QFrame()
        inner_divider.setFrameShape(QFrame.HLine)
        set_style(inner_divider, f"background-color: {TOKENS['border']}; max-height: 1px;")
        custom_layout.addWidget(inner_divider)

        # Hàng chọn số luồng thủ công
        spin_ctrl_row = QHBoxLayout()
        spin_ctrl_row.setSpacing(12)

        spin_lbl = QLabel("Số luồng CPU")
        set_style(spin_lbl, f"font-size: 12.5px; color: {TOKENS['text']};")
        spin_ctrl_row.addWidget(spin_lbl)
        spin_ctrl_row.addStretch()

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, self.total_cores)
        self.threads_spin.setValue(self.threads)
        self.threads_spin.setFixedWidth(80)
        self.threads_spin.setFixedHeight(28)
        self.threads_spin.setAlignment(Qt.AlignCenter)
        self.threads_spin.setEnabled(not self.auto_threads)
        set_style(self.threads_spin, f"""
            QSpinBox {{
                background-color: {TOKENS['input']};
                color: {TOKENS['text']};
                border: 1px solid {TOKENS['border_control']};
                border-radius: 5px;
                padding: 2px 4px;
                font-size: 12px;
            }}
        """)
        self.threads_spin.valueChanged.connect(self._on_threads_changed)
        spin_ctrl_row.addWidget(self.threads_spin)

        max_lbl = QLabel(f"Tối đa: {self.total_cores} luồng")
        set_style(max_lbl, f"font-size: 11.5px; color: {TOKENS['muted']};")
        spin_ctrl_row.addWidget(max_lbl)
        custom_layout.addLayout(spin_ctrl_row)

        cpu_box_layout.addWidget(self.custom_threads_container)
        main_layout.addWidget(cpu_box)

        # Hiệu ứng chuyển động mượt 240ms
        self._opacity_effect = QGraphicsOpacityEffect(self.custom_threads_container)
        self.custom_threads_container.setGraphicsEffect(self._opacity_effect)

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_h = QPropertyAnimation(self.custom_threads_container, b"maximumHeight")
        self._anim_h.setDuration(240)
        self._anim_h.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim_o = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_o.setDuration(240)
        self._anim_o.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim_group.addAnimation(self._anim_h)
        self._anim_group.addAnimation(self._anim_o)
        self._anim_group.finished.connect(self._on_anim_finished)

        # Khởi tạo trạng thái ban đầu
        self._sync_mode_buttons()
        self._sync_badge()
        self._toggle_custom_threads(not self.auto_threads, animated=False)

    def set_compact(self, compact: bool):
        direction = QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight
        self.cpu_row.setDirection(direction)

    def _toggle_custom_threads(self, show: bool, animated: bool = True):
        self._anim_group.stop()
        target_h = self.custom_threads_container.sizeHint().height() or 50

        if not animated:
            self.custom_threads_container.setVisible(show)
            self.custom_threads_container.setMaximumHeight(16777215 if show else 0)
            self._opacity_effect.setOpacity(1.0 if show else 0.0)
            return

        if show:
            self.custom_threads_container.setVisible(True)
            self._anim_h.setStartValue(self.custom_threads_container.height())
            self._anim_h.setEndValue(target_h)
            self._anim_o.setStartValue(self._opacity_effect.opacity())
            self._anim_o.setEndValue(1.0)
            self._anim_group.start()
        else:
            self._anim_h.setStartValue(self.custom_threads_container.height())
            self._anim_h.setEndValue(0)
            self._anim_o.setStartValue(self._opacity_effect.opacity())
            self._anim_o.setEndValue(0.0)
            self._anim_group.start()

    def _on_anim_finished(self):
        if self.auto_threads:
            self.custom_threads_container.setVisible(False)
        else:
            self.custom_threads_container.setMaximumHeight(16777215)

    def _sync_mode_buttons(self):
        self.high_button.setChecked(self.performance_mode == "high")
        self.eco_button.setChecked(self.performance_mode == "eco")

    def _sync_badge(self):
        active_threads = resolve_display_threads(self.auto_threads, self.threads, self.total_cores)
        self.threads_badge.setText(f"Đang dùng: {active_threads} luồng")

    def _select_mode(self, mode: str):
        if mode != self.performance_mode:
            self.performance_mode = mode
            self._sync_mode_buttons()
            self.mode_changed.emit(mode)

    def _on_auto_toggled(self, checked: bool):
        self.auto_threads = checked
        self.threads_spin.setEnabled(not checked)
        self._toggle_custom_threads(not checked, animated=True)
        self._sync_badge()
        self.auto_threads_changed.emit(checked)

    def _on_threads_changed(self, value: int):
        self.threads = value
        self._sync_badge()
        self.threads_changed.emit(value)

    def set_state(self, performance_mode: str, auto_threads: bool, threads: int):
        blockers = [
            QSignalBlocker(self.auto_checkbox),
            QSignalBlocker(self.threads_spin)
        ]
        self.performance_mode = performance_mode if performance_mode in ("high", "eco") else "high"
        self.auto_threads = bool(auto_threads)
        self.threads = max(1, min(self.total_cores, threads))

        self.auto_checkbox.setChecked(self.auto_threads)
        self.threads_spin.setValue(self.threads)
        self.threads_spin.setEnabled(not self.auto_threads)
        self._toggle_custom_threads(not self.auto_threads, animated=False)
        self._sync_mode_buttons()
        self._sync_badge()
        del blockers

    def apply_theme(self, theme: str):
        apply_widget_theme(self, theme)
