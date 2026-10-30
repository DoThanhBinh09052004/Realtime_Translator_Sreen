import os
from PyQt5.QtCore import (
    Qt, QSize, QSignalBlocker, pyqtSignal, QRectF,
    QEasingCurve, QPropertyAnimation, QParallelAnimationGroup
)
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPen, QBrush
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox, QWidget,
    QGraphicsOpacityEffect
)

from ui.styles import CYBER_PALETTE
from ui.icons import get_lucide_icon


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
        self._color = QColor(CYBER_PALETTE["neon_indigo"])
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_state(self, selected: bool, color: str = None):
        self._selected = selected
        if color:
            self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Viền ngoài
        rect = QRectF(1.2, 1.2, self._size - 2.4, self._size - 2.4)

        if self._selected:
            # Đường tròn viền ngoài màu nhấn
            pen = QPen(self._color, 1.8)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect)

            # Chấm tròn đặc ở tâm (filled circle)
            inner_size = self._size * 0.44  # ~8px cho size 18
            inner_offset = (self._size - inner_size) / 2.0
            inner_rect = QRectF(inner_offset, inner_offset, inner_size, inner_size)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self._color))
            painter.drawEllipse(inner_rect)
        else:
            # Đường tròn rỗng mảnh
            dim_pen = QPen(QColor(CYBER_PALETTE["text_dim"]), 1.5)
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
        self._active_color = icon_color
        self._active_bg = "#23233a" if icon_color == CYBER_PALETTE["neon_indigo"] else "#172620"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Header row: [Icon] [Title] ... [Radio Indicator]
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        self.icon_lbl = QLabel()
        icon = get_lucide_icon(icon_name, color=icon_color, size=20)
        self.icon_lbl.setPixmap(icon.pixmap(20, 20))
        header_row.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"""
            font-size: 13.5px;
            font-weight: 700;
            color: {CYBER_PALETTE['text_primary']};
        """)
        header_row.addWidget(self.title_lbl)
        header_row.addStretch()

        self.radio_indicator = RadioIndicator(size=18, parent=self)
        header_row.addWidget(self.radio_indicator)
        layout.addLayout(header_row)

        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setStyleSheet(f"""
            font-size: 11.5px;
            color: {CYBER_PALETTE['text_muted']};
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
        self.radio_indicator.set_state(selected, self._active_color)
        if selected:
            self.setStyleSheet(f"""
                SelectableOptionCard {{
                    background-color: {self._active_bg};
                    border: 1.5px solid {self._active_color};
                    border-radius: 10px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                SelectableOptionCard {{
                    background-color: {CYBER_PALETTE['bg_card']};
                    border: 1px solid {CYBER_PALETTE['border_card']};
                    border-radius: 10px;
                }}
                SelectableOptionCard:hover {{
                    border: 1px solid {CYBER_PALETTE['border_light']};
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
        self.setStyleSheet(f"""
            QFrame#ocrPerformanceCard {{
                background-color: {CYBER_PALETTE['bg_card']};
                border: 1px solid {CYBER_PALETTE['border_card']};
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
        zap_icon = get_lucide_icon("zap", color=CYBER_PALETTE['neon_indigo'], size=20)
        header_icon.setPixmap(zap_icon.pixmap(20, 20))
        header_row.addWidget(header_icon, alignment=Qt.AlignTop)

        header_texts = QVBoxLayout()
        header_texts.setSpacing(2)
        title_lbl = QLabel("Hiệu năng OCR & Tài nguyên máy")
        title_lbl.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {CYBER_PALETTE['text_primary']};")
        desc_lbl = QLabel("Điều chỉnh tốc độ nhận diện và mức sử dụng CPU/RAM")
        desc_lbl.setStyleSheet(f"font-size: 12px; color: {CYBER_PALETTE['text_muted']};")
        header_texts.addWidget(title_lbl)
        header_texts.addWidget(desc_lbl)
        header_row.addLayout(header_texts)
        header_row.addStretch()
        main_layout.addLayout(header_row)

        # ===== 2. Hai thẻ lựa chọn (High vs Eco) =====
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        self.high_card = SelectableOptionCard(
            title="Hiệu năng cao",
            desc="OCR nhanh, dùng nhiều\ntài nguyên hơn",
            icon_name="zap",
            icon_color=CYBER_PALETTE["neon_indigo"],
            parent=self
        )
        self.high_card.clicked.connect(lambda: self._select_mode("high"))
        cards_row.addWidget(self.high_card)

        self.eco_card = SelectableOptionCard(
            title="Tiết kiệm RAM",
            desc="OCR chậm hơn, sử dụng\nít tài nguyên hơn",
            icon_name="leaf",
            icon_color=CYBER_PALETTE["neon_green"],
            parent=self
        )
        self.eco_card.clicked.connect(lambda: self._select_mode("eco"))
        cards_row.addWidget(self.eco_card)

        main_layout.addLayout(cards_row)

        # ===== 3. Đường kẻ phân cách =====
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {CYBER_PALETTE['border']}; max-height: 1px;")
        main_layout.addWidget(divider)

        # ===== 4. Khu vực Phân bổ CPU =====
        cpu_header = QHBoxLayout()
        cpu_header.setSpacing(8)
        cpu_icon = QLabel()
        chip_icon = get_lucide_icon("cpu", color=CYBER_PALETTE['text_muted'], size=16)
        cpu_icon.setPixmap(chip_icon.pixmap(16, 16))
        cpu_header.addWidget(cpu_icon)

        cpu_title = QLabel("Phân bổ CPU")
        cpu_title.setStyleSheet(f"font-size: 13.5px; font-weight: 700; color: {CYBER_PALETTE['text_primary']};")
        cpu_header.addWidget(cpu_title)
        cpu_header.addStretch()
        main_layout.addLayout(cpu_header)

        # Sub-container chứa checkbox và spinbox
        cpu_box = QFrame()
        cpu_box.setStyleSheet(f"""
            QFrame {{
                background-color: {CYBER_PALETTE['bg_sidebar']};
                border: 1px solid {CYBER_PALETTE['border']};
                border-radius: 8px;
            }}
        """)
        cpu_box_layout = QVBoxLayout(cpu_box)
        cpu_box_layout.setContentsMargins(14, 12, 14, 14)
        cpu_box_layout.setSpacing(12)

        # Hàng 1: Checkbox tự động + Badge trạng thái
        row1 = QHBoxLayout()
        self.auto_checkbox = QCheckBox("Tự động tối ưu số luồng CPU")
        self.auto_checkbox.setCursor(Qt.PointingHandCursor)
        self.auto_checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 12.5px;
                color: {CYBER_PALETTE['text_primary']};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 17px;
                height: 17px;
                border-radius: 4px;
                border: 1px solid {CYBER_PALETTE['border_light']};
                background-color: {CYBER_PALETTE['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {CYBER_PALETTE['neon_indigo']};
                border-color: {CYBER_PALETTE['neon_indigo']};
            }}
        """)
        self.auto_checkbox.setChecked(self.auto_threads)
        self.auto_checkbox.toggled.connect(self._on_auto_toggled)
        row1.addWidget(self.auto_checkbox)
        row1.addStretch()

        self.threads_badge = QLabel()
        self.threads_badge.setStyleSheet(f"""
            background-color: #23233a;
            color: #a5b4fc;
            border-radius: 5px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 600;
        """)
        row1.addWidget(self.threads_badge)
        cpu_box_layout.addLayout(row1)

        # Container chứa phần chỉnh số luồng thủ công (ẩn/hiện mượt mà)
        self.custom_threads_container = QFrame()
        self.custom_threads_container.setStyleSheet("background: transparent; border: none;")
        custom_layout = QVBoxLayout(self.custom_threads_container)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(10)

        # Divider mờ bên trong
        inner_divider = QFrame()
        inner_divider.setFrameShape(QFrame.HLine)
        inner_divider.setStyleSheet(f"background-color: {CYBER_PALETTE['border']}; max-height: 1px;")
        custom_layout.addWidget(inner_divider)

        # Hàng chọn số luồng thủ công
        spin_ctrl_row = QHBoxLayout()
        spin_ctrl_row.setSpacing(12)

        spin_lbl = QLabel("Số luồng CPU")
        spin_lbl.setStyleSheet(f"font-size: 12.5px; color: {CYBER_PALETTE['text_primary']};")
        spin_ctrl_row.addWidget(spin_lbl)
        spin_ctrl_row.addStretch()

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, self.total_cores)
        self.threads_spin.setValue(self.threads)
        self.threads_spin.setFixedWidth(80)
        self.threads_spin.setFixedHeight(28)
        self.threads_spin.setAlignment(Qt.AlignCenter)
        self.threads_spin.setEnabled(not self.auto_threads)
        self.threads_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {CYBER_PALETTE['bg_input']};
                color: {CYBER_PALETTE['text_primary']};
                border: 1px solid {CYBER_PALETTE['border_light']};
                border-radius: 5px;
                padding: 2px 4px;
                font-size: 12px;
            }}
        """)
        self.threads_spin.valueChanged.connect(self._on_threads_changed)
        spin_ctrl_row.addWidget(self.threads_spin)

        max_lbl = QLabel(f"Tối đa: {self.total_cores} luồng")
        max_lbl.setStyleSheet(f"font-size: 11.5px; color: {CYBER_PALETTE['text_muted']};")
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
