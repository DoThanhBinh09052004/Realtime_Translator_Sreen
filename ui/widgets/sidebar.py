"""Collapsible navigation shared by the controller pages."""
import os
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve, pyqtProperty, QVariantAnimation
from PyQt5.QtGui import QPixmap, QPainter, QIcon
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

        # Animation for smooth 220ms sliding
        self._anim = QPropertyAnimation(self, b"sidebar_width")
        self._anim.finished.connect(self._on_anim_finished)

        self.set_collapsed(True, animate=False)

    @pyqtProperty(int)
    def sidebar_width(self) -> int:
        return self.width()

    @sidebar_width.setter
    def sidebar_width(self, w: int) -> None:
        self.setFixedWidth(w)
        self._update_width_step(w)

    def _on_anim_finished(self) -> None:
        self._apply_collapsed_state(self._collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def _update_width_step(self, w: int) -> None:
        has_space = w >= 190
        self.brand_title.setVisible(has_space and not self._collapsed)
        self.status.setVisible(has_space and not self._collapsed)
        self.status_dot.setVisible(w <= 85)
        self.collapse_button.setText('Thu gọn' if (has_space and not self._collapsed) else '')
        self.quit_button.setText('Thoát' if (has_space and not self._collapsed) else '')
        for i, button in enumerate(self.nav_buttons):
            _, label, _ = self.nav_item_defs[i]
            button.setText(f'  {label}' if has_space else '')

    def _apply_collapsed_state(self, collapsed: bool) -> None:
        self.setFixedWidth(64 if collapsed else 212)
        self.brand_title.setVisible(not collapsed)
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

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        self._collapsed = collapsed
        target_w = 64 if collapsed else 212

        if not animate or not self.isVisible():
            if hasattr(self, '_anim') and self._anim.state() == QPropertyAnimation.Running:
                self._anim.stop()
            self._apply_collapsed_state(collapsed)
            return

        if hasattr(self, '_anim') and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()

        start_w = self.width()
        if start_w == target_w:
            self._apply_collapsed_state(collapsed)
            return

        self.collapse_button.setToolTip('Mở rộng thanh bên' if collapsed else 'Thu gọn thanh bên')
        self.collapse_button.setAccessibleName(self.collapse_button.toolTip())
        set_theme_icon(self.collapse_button, 'chevron-right' if collapsed else 'chevron-left')
        # Keep icon alignment stable throughout the width transition.
        for button in self.nav_buttons:
            set_style(button, nav_button_style(button is self.nav_buttons[self._active], True, 'tokens'))
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.setStartValue(start_w)
        self._anim.setEndValue(target_w)
        self._anim.start()

    def set_active_page(self, index: int) -> None:
        self._active = index
        for i, button in enumerate(self.nav_buttons):
            icon, label, _ = self.nav_item_defs[i]
            button.setText('' if self._collapsed else f'  {label}')
            is_active = (i == index)
            old_icon = button.icon()
            was_active = getattr(button, '_selected', None)
            button._selected = is_active
            set_style(button, nav_button_style(is_active, self._collapsed, 'tokens'))
            set_theme_icon(button, icon, 'text' if is_active else 'muted', 19, filled=is_active)
            previous = getattr(button, '_icon_animation', None)
            if previous is not None:
                previous.stop()
                previous.deleteLater()
                button._icon_animation = None
            if was_active is not None and was_active != is_active and self.isVisible():
                target_icon = button.icon()
                animation = QVariantAnimation(button)
                animation.setDuration(180)
                animation.setStartValue(0.0)
                animation.setEndValue(1.0)
                animation.setEasingCurve(QEasingCurve.InOutCubic)
                def blend(value, b=button, old=old_icon, new=target_icon):
                    # Render at device scale so the transition remains sharp.
                    ratio = b.devicePixelRatioF()
                    pix = QPixmap(round(19 * ratio), round(19 * ratio))
                    pix.setDevicePixelRatio(ratio)
                    pix.fill(Qt.transparent)
                    painter = QPainter(pix)
                    old_pix = old.pixmap(pix.size())
                    new_pix = new.pixmap(pix.size())
                    old_pix.setDevicePixelRatio(ratio)
                    new_pix.setDevicePixelRatio(ratio)
                    painter.setOpacity(1.0 - value)
                    painter.drawPixmap(0, 0, old_pix)
                    painter.setOpacity(value)
                    painter.drawPixmap(0, 0, new_pix)
                    painter.end()
                    b.setIcon(QIcon(pix))
                animation.valueChanged.connect(blend)
                animation.finished.connect(lambda b=button, icon=target_icon: b.setIcon(icon))
                button._icon_animation = animation
                animation.start()

    def _update_theme_button(self) -> None:
        dark = theme_for(self) == 'dark'
        label = 'Chuyển sang giao diện sáng' if dark else 'Chuyển sang giao diện tối'
        self.theme_button.setToolTip(label)
        self.theme_button.setAccessibleName(label)
        self.theme_button.setText('' if self._collapsed else ('Giao diện sáng' if dark else 'Giao diện tối'))
        set_theme_icon(self.theme_button, 'sun' if dark else 'moon')

    def apply_theme(self, theme: str) -> None:
        apply_widget_theme(self, theme)
        self._update_theme_button()
        self.set_active_page(self._active)

    def set_status(self, text: str, style: str) -> None:
        self.status.setText(text)
        self.status_dot.setToolTip(text)
        set_style(self.status, style)
