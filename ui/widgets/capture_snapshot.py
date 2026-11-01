"""Snapshot preview widget rendering letterboxed image and normalized regions."""
from typing import Any
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPainterPath, QImage
from PyQt5.QtWidgets import QWidget, QSizePolicy
from ui.styles import apply_widget_theme, palette_for, TEXT_SIZES


class CaptureSnapshotWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._image: QImage | None = None
        self._profile: Any | None = None
        self._context: Any | None = None
        self._placeholder_text: str = "Ban đầu: Chọn nguồn để xem trước"
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_snapshot(self, image: QImage | None, profile: Any | None, context: Any | None) -> None:
        self._image = image
        self._profile = profile
        self._context = context
        self.update()

    def apply_theme(self, theme):
        apply_widget_theme(self, theme)

    def clear_snapshot(self, placeholder_text: str = "Ban đầu: Chọn nguồn để xem trước") -> None:
        self._image = None
        self._profile = None
        self._context = None
        self._placeholder_text = placeholder_text
        self.update()

    def image_rect(self) -> QRectF:
        """One floating-point transform for both the source image and its regions."""
        if self._image is None or self._image.isNull() or self.width() <= 0 or self.height() <= 0:
            return QRectF()
        scale = min(self.width() / self._image.width(), self.height() / self._image.height())
        width, height = self._image.width() * scale, self._image.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def aligned_rectangles(self) -> list[tuple[str, QRectF, bool]]:
        """Return (label, QRectF, is_exclusion) scaled to match the letterboxed image."""
        if self._image is None or self._profile is None:
            return []
        image_rect = self.image_rect()
        if image_rect.isEmpty():
            return []
        draw_w, draw_h = image_rect.width(), image_rect.height()
        offset_x, offset_y = image_rect.x(), image_rect.y()

        rects: list[tuple[str, QRectF, bool]] = []
        for region in getattr(self._profile, 'regions', ()):
            if not getattr(region, 'enabled', True):
                continue
            r = region.rect
            rx = offset_x + r.x * draw_w
            ry = offset_y + r.y * draw_h
            rw = r.width * draw_w
            rh = r.height * draw_h
            rects.append((getattr(region, 'name', 'Vùng quét'), QRectF(rx, ry, rw, rh), False))

        for index, exclusion in enumerate(getattr(self._profile, 'exclusions', ())):
            rx = offset_x + exclusion.x * draw_w
            ry = offset_y + exclusion.y * draw_h
            rw = exclusion.width * draw_w
            rh = exclusion.height * draw_h
            rects.append((f"Loại trừ {index + 1}", QRectF(rx, ry, rw, rh), True))

        return rects

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 6, 6)
        bg_color = QColor(palette_for(self)['input'])
        border_color = QColor(palette_for(self)['border'])
        painter.fillPath(frame, bg_color)
        painter.save()
        painter.setClipPath(frame)

        if self._image is not None and not self._image.isNull():
            image_rect = self.image_rect()
            if not image_rect.isEmpty():
                painter.drawImage(image_rect, self._image)

                # Draw region outlines
                for label, rect, is_exclusion in self.aligned_rectangles():
                    pen_color = QColor('#ffb454' if is_exclusion else '#36d6b0')
                    painter.setPen(QPen(pen_color, 2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(rect)

                    # Text label
                    font = QFont(self.font())
                    font.setPixelSize(TEXT_SIZES['caption'])
                    font.setWeight(QFont.Medium)
                    painter.setFont(font)
                    painter.drawText(int(rect.x()) + 4, int(rect.y()) + 14, label)
        else:
            painter.setPen(QPen(QColor(palette_for(self)['muted'])))
            painter.setFont(self.font())
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder_text)
        painter.restore()
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(frame)
