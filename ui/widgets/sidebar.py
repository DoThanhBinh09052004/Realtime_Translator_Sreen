"""Collapsible navigation shared by the controller pages."""
import os
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap
from ui.icons import set_theme_icon
from ui.styles import TOKENS, set_style, apply_widget_theme, sidebar_style, nav_button_style, theme_for


class ControllerSidebar(QFrame):
    page_requested = pyqtSignal(int)
    quit_requested = pyqtSignal()
    theme_toggle_requested = pyqtSignal()

    def __init__(self, nav_items, logo_path, parent=None):
        super().__init__(parent)
        self.setObjectName('sidebarFrame')
        self._collapsed = True
        self._active = 0
        self.nav_item_defs = nav_items
        set_style(self, sidebar_style('tokens'))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 12)
        layout.setSpacing(8)
        brand_row = QHBoxLayout()
        mark = QLabel()
        mark.setFixedSize(30, 30)
        if logo_path and os.path.isfile(logo_path):
            mark.setPixmap(QPixmap(logo_path).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            set_theme_icon(mark, 'scan', 'text', 28)
        self.brand_title = QLabel('Translate HUD')
        set_style(self.brand_title, 'font-weight:600;font-size:14px;')
        brand_row.addWidget(mark)
        brand_row.addWidget(self.brand_title)
        layout.addLayout(brand_row)
        self.collapse_button = QPushButton()
        self.collapse_button.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        layout.addWidget(self.collapse_button)
        self.back_button = QPushButton('Quay lại dịch')
        self.back_button.clicked.connect(lambda: self.page_requested.emit(0))
        layout.addWidget(self.back_button)
        self.nav_buttons = []
        for i, (icon, label, tooltip) in enumerate(nav_items):
            button = QPushButton()
            button.setFixedHeight(40)
            button.setIconSize(QSize(19, 19))
            button.setToolTip(f'{label} — {tooltip}')
            button.setAccessibleName(label)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, index=i: self.page_requested.emit(index))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.addStretch()
        self.theme_button = QPushButton()
        self.theme_button.clicked.connect(self.theme_toggle_requested.emit)
        layout.addWidget(self.theme_button)
        self.status = QLabel('Đã dừng')
        self.status.setWordWrap(True)
        self.status_dot = QLabel('●')
        self.status_dot.setAlignment(Qt.AlignCenter)
        set_style(self.status_dot, f'color:{TOKENS["positive"]};font-size:13px;')
        layout.addWidget(self.status)
        layout.addWidget(self.status_dot)
        self.quit_button = QPushButton()
        self.quit_button.setToolTip('Thoát ứng dụng')
        self.quit_button.setAccessibleName('Thoát ứng dụng')
        self.quit_button.clicked.connect(self.quit_requested.emit)
        layout.addWidget(self.quit_button)
        self.set_collapsed(True)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setFixedWidth(64 if collapsed else 212)
        self.brand_title.setVisible(not collapsed)
        self.back_button.setVisible(not collapsed)
        self.status.setVisible(not collapsed)
        self.status_dot.setVisible(collapsed)
        self.collapse_button.setToolTip('Mở rộng thanh bên' if collapsed else 'Thu gọn thanh bên')
        self.collapse_button.setAccessibleName(self.collapse_button.toolTip())
        self.collapse_button.setText('' if collapsed else 'Thu gọn')
        set_theme_icon(self.collapse_button, 'chevron-right' if collapsed else 'chevron-left')
        self.quit_button.setText('' if collapsed else 'Thoát')
        set_theme_icon(self.quit_button, 'log-out')
        self.set_active_page(self._active)
        self._update_theme_button()
        for button in (self.collapse_button, self.theme_button, self.quit_button):
            set_style(button, nav_button_style(False, collapsed, 'tokens'))
            button.setMinimumHeight(36)

    def set_active_page(self, index):
        self._active = index
        for i, button in enumerate(self.nav_buttons):
            icon, label, _ = self.nav_item_defs[i]
            button.setText('' if self._collapsed else f'  {label}')
            set_style(button, nav_button_style(i == index, self._collapsed, 'tokens'))
            set_theme_icon(button, icon, 'text' if i == index else 'muted', 19)

    def _update_theme_button(self):
        dark = theme_for(self) == 'dark'
        label = 'Chuyển sang giao diện sáng' if dark else 'Chuyển sang giao diện tối'
        self.theme_button.setToolTip(label)
        self.theme_button.setAccessibleName(label)
        self.theme_button.setText('' if self._collapsed else ('Giao diện sáng' if dark else 'Giao diện tối'))
        set_theme_icon(self.theme_button, 'sun' if dark else 'moon')

    def apply_theme(self, theme: str) -> None:
        apply_widget_theme(self, theme)
        self._update_theme_button()

    def set_status(self, text, style):
        self.status.setText(text)
        self.status_dot.setToolTip(text)
        set_style(self.status, style)
