"""Compact toggle switch widget extending QCheckBox."""
try:
    import sip
except ImportError:
    from PyQt5 import sip

from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtCore import Qt, QRectF, QSize
from ui.styles import palette_for, theme_for


class ToggleSwitch(QCheckBox):
    """Accessible toggle switch with QCheckBox contract."""

    def __init__(self, text: str = '', parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self) -> QSize:
        try:
            if sip.isdeleted(self):
                return QSize(38, 24)
            fm = self.fontMetrics()
            text_w = fm.horizontalAdvance(self.text()) if hasattr(fm, 'horizontalAdvance') else fm.width(self.text())
            w = 38 + (8 + text_w if self.text() else 0)
            h = max(24, fm.height())
            return QSize(w, h)
        except RuntimeError:
            return QSize(38, 24)

    def hitButton(self, pos) -> bool:
        try:
            if sip.isdeleted(self):
                return False
            return self.rect().contains(pos)
        except RuntimeError:
            return False

    def paintEvent(self, event) -> None:
        try:
            if sip.isdeleted(self):
                return
            # Retain the owning window throughout painting, including cyclic GC.
            paint_owner = self.window()
            painter = QPainter(self)
            if not painter.isActive():
                return
            painter.setRenderHint(QPainter.Antialiasing)

            h = self.height()
            track_w, track_h = 36, 20
            track_y = (h - track_h) / 2
            track_rect = QRectF(0, track_y, track_w, track_h)

            checked = self.isChecked()
            enabled = self.isEnabled()
            p = palette_for(self)
            dark = theme_for(self) == 'dark'

            if checked:
                track_color = QColor(p.get('focus', '#3b82f6'))
            else:
                track_color = QColor('#475569') if dark else QColor('#cbd5e1')

            if not enabled:
                track_color.setAlpha(110)

            painter.setBrush(track_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(track_rect, 10, 10)

            # Thumb
            thumb_size = 16
            thumb_x = (track_w - thumb_size - 2) if checked else 2
            thumb_y = track_y + 2
            thumb_color = QColor('#ffffff') if enabled else QColor('#e2e8f0')
            painter.setBrush(thumb_color)
            painter.drawEllipse(QRectF(thumb_x, thumb_y, thumb_size, thumb_size))

            # Text label
            if self.text():
                text_color = QColor(p.get('text', '#111827'))
                if not enabled:
                    text_color.setAlpha(120)
                painter.setPen(text_color)
                painter.setFont(self.font())
                text_rect = QRectF(track_w + 8, 0, self.width() - track_w - 8, h)
                painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

            painter.end()
        except RuntimeError:
            return
