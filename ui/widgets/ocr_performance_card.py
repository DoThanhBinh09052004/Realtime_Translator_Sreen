import os
from PyQt5.QtCore import (
    Qt, QSize, QSignalBlocker, pyqtSignal, QRectF,
    QEasingCurve, QPropertyAnimation, QParallelAnimationGroup
)
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPen, QBrush
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox, QWidget,
    QGraphicsOpacityEffect, QBoxLayout
)

from ui.styles import TOKENS, set_style, apply_widget_theme, palette_for
from ui.icons import set_theme_icon
from ui.widgets.toggle_switch import ToggleSwitch


def resolve_display_threads(auto: bool, custom_threads: int, total_cores: int) -> int:
    if not auto:
        return max(1, min(total_cores, custom_threads))
    return max(2, min(6, total_cores // 2))


class RadioIndicator(QWidget):
    """
    Radio indicator vẽ sắc nét bằng QPainter:
    - Chưa chọn: Đường tròn rỗng mảnh (hollow circle / ring) màu xám trung tính.
    - Đã chọn: Đường tròn viền màu nhấn + chấm tròn đặc ở tâm (filled inner circle).
    """
    def __init__(self, size: int = 18, parent=None):
        super().__init__(parent)
        self._size = size
        self._selected = False
        self._role = 'focus'
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_state(self, selected: bool, role: str = 'focus'):
        self._selected = selected
        self._role = role
        self.update()

    def paintEvent(self, event):
        # Keep the owning window alive if Python GC runs inside a paint callback.
        owner = self.window()
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.Antialiasing)

        # Viền ngoài
        rect = QRectF(1.2, 1.2, self._size - 2.4, self._size - 2.4)

        if self._selected:
            # Đường tròn viền ngoài màu nhấn
            pen = QPen(QColor(palette_for(self)[self._role]), 1.8)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect)

            # Chấm tròn đặc ở tâm (filled circle)
            inner_size = self._size * 0.44  # ~8px cho size 18
            inner_offset = (self._size - inner_size) / 2.0
            inner_rect = QRectF(inner_offset, inner_offset, inner_size, inner_size)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(palette_for(self)[self._role])))
            painter.drawEllipse(inner_rect)
        else:
            # Đường tròn rỗng mảnh
            dim_pen = QPen(QColor(palette_for(self)['muted']), 1.5)
            painter.setPen(dim_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect)

        painter.end()


class SelectableOptionCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, title: str, desc: str, icon_name: str, icon_color: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._selected = False
        self.setProperty("selected", False)
        self._active_role = 'focus' if icon_color == TOKENS['focus'] else 'positive'
        self._active_color = TOKENS[self._active_role]
        self._active_bg = TOKENS['selection_bg'] if self._active_role == 'focus' else TOKENS['positive_bg']

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Header row: [Icon] [Title] ... [Radio Indicator]
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        self.icon_lbl = QLabel()
        set_theme_icon(self.icon_lbl, icon_name, self._active_role, 20)
        header_row.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(title)
        set_style(self.title_lbl, f"""
            font-size: 13.5px;
            font-weight: 700;
            color: {TOKENS['text']};
        """)
        header_row.addWidget(self.title_lbl)
        header_row.addStretch()

        self.radio_indicator = RadioIndicator(size=18, parent=self)
        header_row.addWidget(self.radio_indicator)
        layout.addLayout(header_row)

        self.desc_lbl = QLabel(desc)
        set_style(self.desc_lbl, f"""
            font-size: 11.5px;
            color: {TOKENS['muted']};
            line-height: 1.35;
        """)
        self.desc_lbl.setWordWrap(True)
        layout.addWidget(self.desc_lbl)

        self.update_selection(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def update_selection(self, selected: bool):
        self._selected = selected
        self.setProperty("selected", selected)
        self.radio_indicator.set_state(selected, self._active_role)
        if selected:
            set_style(self, f"""
                SelectableOptionCard {{
                    background-color: {self._active_bg};
                    border: 1.5px solid {self._active_color};
                    border-radius: 10px;
                }}
            """)
        else:
            set_style(self, f"""
                SelectableOptionCard {{
                    background-color: {TOKENS['surface']};
                    border: 1px solid {TOKENS['border']};
                    border-radius: 10px;
                }}
                SelectableOptionCard:hover {{
                    border: 1px solid {TOKENS['border_control']};
                }}
            """)


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

        header_icon = QLabel()
        set_theme_icon(header_icon, 'zap', 'focus', 20)
        header_row.addWidget(header_icon, alignment=Qt.AlignTop)

        header_texts = QVBoxLayout()
        header_texts.setSpacing(2)
        title_lbl = QLabel("Hiệu năng OCR & Tài nguyên máy")
        set_style(title_lbl, f"font-size: 15px; font-weight: 700; color: {TOKENS['text']};")
        desc_lbl = QLabel("Điều chỉnh tốc độ nhận diện và mức sử dụng CPU/RAM")
        set_style(desc_lbl, f"font-size: 12px; color: {TOKENS['muted']};")
        title_lbl.setWordWrap(True)
        desc_lbl.setWordWrap(True)
        header_texts.addWidget(title_lbl)
        header_texts.addWidget(desc_lbl)
        header_row.addLayout(header_texts)
        header_row.addStretch()
        main_layout.addLayout(header_row)

        # ===== 2. Hai thẻ lựa chọn (High vs Eco) =====
        cards_row = QBoxLayout(QBoxLayout.LeftToRight)
        self.cards_row = cards_row
        cards_row.setSpacing(16)

        self.high_card = SelectableOptionCard(
            title="Hiệu năng cao",
            desc="OCR nhanh, dùng nhiều\ntài nguyên hơn",
            icon_name="zap",
            icon_color=TOKENS['focus'],
            parent=self
        )
        self.high_card.clicked.connect(lambda: self._select_mode("high"))
        cards_row.addWidget(self.high_card)

        self.eco_card = SelectableOptionCard(
            title="Tiết kiệm RAM",
            desc="OCR chậm hơn, sử dụng\nít tài nguyên hơn",
            icon_name="leaf",
            icon_color=TOKENS['positive'],
            parent=self
        )
        self.eco_card.clicked.connect(lambda: self._select_mode("eco"))
        cards_row.addWidget(self.eco_card)

        main_layout.addLayout(cards_row)

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
        self._sync_cards()
        self._sync_badge()
        self._toggle_custom_threads(not self.auto_threads, animated=False)

    def set_compact(self, compact: bool):
        direction = QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight
        self.cards_row.setDirection(direction)
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

    def _sync_cards(self):
        self.high_card.update_selection(self.performance_mode == "high")
        self.eco_card.update_selection(self.performance_mode == "eco")

    def _sync_badge(self):
        active_threads = resolve_display_threads(self.auto_threads, self.threads, self.total_cores)
        self.threads_badge.setText(f"Đang dùng: {active_threads} luồng")

    def _select_mode(self, mode: str):
        if mode != self.performance_mode:
            self.performance_mode = mode
            self._sync_cards()
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
        self._sync_cards()
        self._sync_badge()
        del blockers

    def apply_theme(self, theme: str):
        apply_widget_theme(self, theme)
