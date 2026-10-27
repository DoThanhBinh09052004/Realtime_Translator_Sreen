"""Subtitle placement in Qt logical, global work-area coordinates."""
from PyQt5.QtCore import QPoint, QRect, QSize


def preset_position(available: QRect, size: QSize, preset: str) -> QPoint | None:
    width, height = max(size.width(), 200), max(size.height(), 40)
    center_x = available.x() + (available.width() - width) // 2
    bottom_y = available.y() + available.height() - height - 80
    if preset == 'top_center':
        return QPoint(center_x, available.y() + 60)
    if preset == 'bottom_left':
        return QPoint(available.x() + 60, bottom_y)
    if preset == 'bottom_center':
        return QPoint(center_x, bottom_y)
    return None


def clamp_position(available: QRect, size: QSize, position: QPoint, margin: int = 10) -> QPoint:
    def clamp_axis(origin, extent, length, desired):
        if length > extent:
            return origin
        padding = margin if length + 2 * margin <= extent else 0
        return max(origin + padding, min(desired, origin + extent - length - padding))

    return QPoint(
        clamp_axis(available.x(), available.width(), size.width(), position.x()),
        clamp_axis(available.y(), available.height(), size.height(), position.y()),
    )
