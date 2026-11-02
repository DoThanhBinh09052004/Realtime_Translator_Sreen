"""Collapsible navigation shared by the controller pages."""
import os
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStylePainter, QStyleOptionButton, QStyle, QSizePolicy, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QSize, QRect, pyqtSignal, QPropertyAnimation, QEasingCurve, pyqtProperty, QVariantAnimation
from PyQt5.QtGui import QPixmap, QPainter, QIcon
from ui.icons import set_theme_icon
from ui.styles import TOKENS, set_style, apply_widget_theme, sidebar_style, nav_button_style, theme_for


class SidebarButton(QPushButton):
    """Keep the icon anchored while fading only the single-line label."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label_opacity = 0.0
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)

    def paintEvent(self, event):
        owner = self.window()
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        text, icon = option.text, QIcon(self.icon())
        option.text = ''
        option.icon = QIcon()
        painter.drawControl(QStyle.CE_PushButton, option)
        icon.paint(painter, QRect(12, (self.height() - 19) // 2, 19, 19))
        painter.setOpacity(self.label_opacity)
        painter.setPen(option.palette.buttonText().color())
        painter.drawText(QRect(44, 0, max(0, self.width() - 48), self.height()),
                         Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine, text.strip())


class ControllerSidebar(QFrame):
    page_requested = pyqtSignal(int)
    quit_requested = pyqtSignal()
    theme_toggle_requested = pyqtSignal()

    def __init__(self, nav_items, logo_path, parent=None):
        super().__init__(parent)
        self.setObjectName('sidebarFrame')
        self._collapsed = True
        self._active = 0
        self._expansion = 0.0
        self.nav_item_defs = nav_items
        set_style(self, sidebar_style('tokens'))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 12)
        layout.setSpacing(8)
        brand_row = QHBoxLayout()
        mark = QLabel()
        self.brand_mark = mark
        self._logo_path = logo_path
        mark.setFixedSize(30, 30)
        if logo_path and os.path.isfile(logo_path):
            mark.setPixmap(QPixmap(logo_path).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            set_theme_icon(mark, 'scan', 'text', 28)
        self.brand_title = QLabel('Translate HUD')
        set_style(self.brand_title, 'font-weight:600;font-size:14px;')
        brand_row.addWidget(mark)
        self.brand_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        brand_row.addWidget(self.brand_title, 1)
        layout.addLayout(brand_row)
        self.collapse_button = SidebarButton()
        self.collapse_button.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        layout.addWidget(self.collapse_button)
        self.nav_buttons = []
        for i, (icon, label, tooltip) in enumerate(nav_items):
            button = SidebarButton()
            button.setFixedHeight(40)
            button.setIconSize(QSize(19, 19))
            button.setToolTip(f'{label} — {tooltip}')
            button.setAccessibleName(label)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, index=i: self.page_requested.emit(index))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.addStretch()
        self.theme_button = SidebarButton()
        self.theme_button.clicked.connect(self.theme_toggle_requested.emit)
        layout.addWidget(self.theme_button)
        self.status = QLabel('Đã dừng')
        self.status.setWordWrap(False)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.status.setFixedHeight(24)
        self.status_dot = QLabel('●')
        self.status_dot.setAlignment(Qt.AlignCenter)
        set_style(self.status_dot, f'color:{TOKENS["positive"]};font-size:13px;')
        status_row = QFrame()
        status_row.setFixedHeight(24)
        self.status.setParent(status_row)
        self.status_dot.setParent(status_row)
        self.status.setGeometry(0, 0, 192, 24)
        self.status_dot.setGeometry(0, 0, 44, 24)
        layout.addWidget(status_row)
        self._label_effects = []
        for label in (self.brand_title, self.status):
            effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(effect)
            self._label_effects.append(effect)
        self._dot_effect = QGraphicsOpacityEffect(self.status_dot)
        self.status_dot.setGraphicsEffect(self._dot_effect)
        self.quit_button = SidebarButton()
        self.quit_button.setToolTip('Thoát ứng dụng')
        self.quit_button.setAccessibleName('Thoát ứng dụng')
        self.quit_button.clicked.connect(self.quit_requested.emit)
        layout.addWidget(self.quit_button)

        # One shared timeline drives width and label opacity.
        self._anim = QPropertyAnimation(self, b"expansion")
        self._anim.finished.connect(self._on_anim_finished)

        self.set_collapsed(True, animate=False)

    @pyqtProperty(float)
    def expansion(self):
        return self._expansion

    @expansion.setter
    def expansion(self, value):
        self._expansion = value
        self.setFixedWidth(round(64 + 148 * value))
        opacity = max(0.0, min(1.0, (value - 0.35) / 0.65))
        for button in (*self.nav_buttons, self.collapse_button, self.theme_button, self.quit_button):
            button.label_opacity = opacity
            button.update()
        for effect in self._label_effects:
            effect.setOpacity(opacity)
        self._dot_effect.setOpacity(1.0 - opacity)

    def _on_anim_finished(self):
        self._apply_collapsed_state(self._collapsed)

    def is_collapsed(self):
        return self._collapsed

    def _update_labels(self):
        collapsed = self._collapsed and self._expansion == 0.0
        self.collapse_button.setToolTip('Mở rộng thanh bên' if self._collapsed else 'Thu gọn thanh bên')
        self.collapse_button.setAccessibleName(self.collapse_button.toolTip())
        self.collapse_button.setText('' if collapsed else 'Thu gọn')
        set_theme_icon(self.collapse_button, 'chevron-right' if self._collapsed else 'chevron-left')
        self.quit_button.setText('' if collapsed else 'Thoát')
        set_theme_icon(self.quit_button, 'log-out')
        for i, button in enumerate(self.nav_buttons):
            button.setText('' if collapsed else self.nav_item_defs[i][1])
        self._update_theme_button()

    def _apply_collapsed_state(self, collapsed):
        self.expansion = 0.0 if collapsed else 1.0
        self._update_labels()
        self.set_active_page(self._active)
        for button in (self.collapse_button, self.theme_button, self.quit_button):
            set_style(button, nav_button_style(False, False, 'tokens'))
            button.setMinimumHeight(36)

    def set_collapsed(self, collapsed, animate=True):
        self._anim.stop()
        self._collapsed = collapsed
        target = 0.0 if collapsed else 1.0
        if not animate or not self.isVisible() or self._expansion == target:
            self._apply_collapsed_state(collapsed)
            return
        self._update_labels()
        # Expanding starts from an empty caption but never changes layout bounds.
        for i, button in enumerate(self.nav_buttons):
            button.setText(self.nav_item_defs[i][1])
        self.collapse_button.setText('Thu gọn')
        self.quit_button.setText('Thoát')
        self.theme_button.setText('Giao diện sáng' if theme_for(self) == 'dark' else 'Giao diện tối')
        self._anim.setDuration(max(1, round(300 * abs(target - self._expansion))))
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.setStartValue(self._expansion)
        self._anim.setEndValue(target)
        self._anim.start()

    def set_active_page(self, index: int) -> None:
        self._active = index
        for i, button in enumerate(self.nav_buttons):
            icon, label, _ = self.nav_item_defs[i]
            button.setText('' if self._collapsed and self._expansion == 0.0 else label)
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
        self.theme_button.setText('' if self._collapsed and self._expansion == 0.0 else ('Giao diện sáng' if dark else 'Giao diện tối'))
        set_theme_icon(self.theme_button, 'sun' if dark else 'moon')

    def apply_theme(self, theme: str) -> None:
        apply_widget_theme(self, theme)
        if self._logo_path:
            path = self._logo_path
            dark_path = os.path.splitext(path)[0] + "-dark.png"
            if theme == "dark" and os.path.isfile(dark_path):
                path = dark_path
            if os.path.isfile(path):
                self.brand_mark.setPixmap(QPixmap(path).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._update_theme_button()
        self.set_active_page(self._active)

    def set_status(self, text: str, style: str) -> None:
        self.status.setText(text)
        self.status_dot.setToolTip(text)
        set_style(self.status, style)
