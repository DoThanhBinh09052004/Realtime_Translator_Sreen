"""Snapshot preview widget rendering letterboxed image and normalized regions."""
from typing import Any
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPixmap, QImage
from PyQt5.QtWidgets import QWidget, QSizePolicy
from ui.styles import CYBER_PALETTE


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

    def clear_snapshot(self, placeholder_text: str = "Ban đầu: Chọn nguồn để xem trước") -> None:
        self._image = None
        self._profile = None
        self._context = None
        self._placeholder_text = placeholder_text
        self.update()

    def aligned_rectangles(self) -> list[tuple[str, QRectF, bool]]:
        """Return (label, QRectF, is_exclusion) scaled to match the letterboxed image."""
        if self._image is None or self._profile is None:
            return []
        img_w = self._image.width()
        img_h = self._image.height()
        if img_w <= 0 or img_h <= 0 or self.width() <= 0 or self.height() <= 0:
            return []

        scale = min(self.width() / img_w, self.height() / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        offset_x = (self.width() - draw_w) / 2.0
        offset_y = (self.height() - draw_h) / 2.0

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

        # Draw container background
        bg_color = QColor(CYBER_PALETTE['bg_card'])
        border_color = QColor(CYBER_PALETTE['border_card'])
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 6, 6)

        if self._image is not None and not self._image.isNull():
            img_w = self._image.width()
            img_h = self._image.height()
            if img_w > 0 and img_h > 0:
                scale = min(self.width() / img_w, self.height() / img_h)
                draw_w = int(img_w * scale)
                draw_h = int(img_h * scale)
                offset_x = int((self.width() - draw_w) / 2)
                offset_y = int((self.height() - draw_h) / 2)

                pixmap = QPixmap.fromImage(self._image).scaled(
                    draw_w, draw_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                painter.drawPixmap(offset_x, offset_y, pixmap)

                # Draw region outlines
                for label, rect, is_exclusion in self.aligned_rectangles():
                    pen_color = QColor('#ffb454' if is_exclusion else '#36d6b0')
                    painter.setPen(QPen(pen_color, 2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(rect)

                    # Text label
                    painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                    painter.drawText(int(rect.x()) + 4, int(rect.y()) + 14, label)
        else:
            painter.setPen(QPen(QColor(CYBER_PALETTE['text_muted'])))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder_text)
