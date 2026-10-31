"""Direct source-bounded selection; edits remain a draft until confirmation."""
from dataclasses import replace
from math import floor, ceil

from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import QDialog, QLabel, QPushButton

from core.blocks.geometry import overlay_window_rect
from core.capture.models import NormalizedRect
from core.capture.profile import parse_capture_profile, serialize_capture_profile
from core.config import ConfigError


class DirectRegionSelector(QDialog):
    profile_selected = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, profile, context):
        super().__init__()
        self.profile, self.context = profile, context
        self._stale = False
        self._selecting_all = False
        self.selection = QRect()
        self._anchor = None
        self._operation = None
        self._original = QRect()
        self._target = next((r for r in profile.regions if r.enabled), profile.regions[0])
        bounds = overlay_window_rect(context.geometry)
        self.setGeometry(floor(bounds.x), floor(bounds.y),
                         ceil(bounds.right) - floor(bounds.x), ceil(bounds.bottom) - floor(bounds.y))
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setWindowTitle('Chọn vùng đọc trực tiếp')
        self.error_label = QLabel(self)
        self.error_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('background: #161b24; color: white; padding: 10px; font-size: 14px;')
        self._help()
        self.confirm_btn = QPushButton('✓ Dùng vùng này', self)
        self.confirm_btn.setGeometry(max(0, self.width()-280), self.height()-58, 160, 42)
        self.confirm_btn.setStyleSheet('background: #07986f; color: white; font-weight: bold; border-radius: 6px;')
        self.confirm_btn.clicked.connect(self._confirm)
        self.cancel_btn = QPushButton('Hủy', self)
        self.cancel_btn.setGeometry(max(0, self.width()-110), self.height()-58, 96, 42)
        self.cancel_btn.clicked.connect(self.reject)
        self.select_all_btn = QPushButton('Chọn toàn màn hình' if profile.source_kind == 'desktop'
                                          else 'Chọn toàn bộ cửa sổ', self)
        self.select_all_btn.setGeometry(14, self.height()-58, 210, 42)
        self.select_all_btn.setStyleSheet('background: #242b38; color: white; border: 1px solid #7e90ad; border-radius: 6px;')
        self.select_all_btn.clicked.connect(self.select_all)

    def select_all(self):
        if self._stale:
            return
        width, height = self._selection_size()
        self.selection = QRect(0, 0, width, height)
        self._selecting_all = True
        self._anchor = None
        if len(self.profile.regions) > 1:
            self.error_label.setText('Xác nhận sẽ thay các vùng đọc hiện có bằng một vùng toàn nguồn; giữ các vùng loại trừ. Hủy để giữ nguyên.')
        self.update()

    def _help(self):
        self.error_label.setText('Kéo khoanh vùng chữ · Kéo bên trong để di chuyển · Kéo góc để chỉnh\n'
                                 'Enter: xác nhận · Esc: hủy · Chỉ thay vùng đọc đầu tiên đang bật')
        self.error_label.setGeometry(12, 12, max(80, self.width() - 24), 68)

    def _point(self, pos):
        return self._clamp_point(pos)

    def _clamp_point(self, pos):
        width, height = self._selection_size()
        return QPoint(max(0, min(width, pos.x())), max(0, min(height, pos.y())))

    def _selection_size(self):
        return self.width(), self.height()

    def _corner(self, pos):
        if self.selection.isEmpty():
            return None
        for name, corner in (('tl', self.selection.topLeft()), ('tr', self.selection.topRight()),
                             ('bl', self.selection.bottomLeft()), ('br', self.selection.bottomRight())):
            if (pos - corner).manhattanLength() <= 14:
                return name
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._stale:
            return
        self._anchor = self._point(event.pos())
        self._selecting_all = False
        self._original = QRect(self.selection)
        self._operation = self._corner(self._anchor)
        if self._operation is None:
            self._operation = 'move' if self.selection.contains(self._anchor) else 'draw'

    def _drag(self, pos):
        if self._anchor is None:
            return
        point = self._point(pos)
        delta = point - self._anchor
        r = self._original
        width, height = self._selection_size()
        if self._operation == 'move':
            self.selection.moveTo(max(0, min(width - r.width(), r.x() + delta.x())),
                                  max(0, min(height - r.height(), r.y() + delta.y())))
        else:
            if self._operation == 'draw':
                a, b = self._anchor, point
            else:
                left, top, right, bottom = r.x(), r.y(), r.x() + r.width(), r.y() + r.height()
                if 'l' in self._operation: left += delta.x()
                if 'r' in self._operation: right += delta.x()
                if 't' in self._operation: top += delta.y()
                if 'b' in self._operation: bottom += delta.y()
                a, b = self._clamp_point(QPoint(left, top)), self._clamp_point(QPoint(right, bottom))
            self.selection = QRect(min(a.x(), b.x()), min(a.y(), b.y()),
                                   abs(a.x() - b.x()), abs(a.y() - b.y()))
        self.update()

    def mouseMoveEvent(self, event):
        if self._anchor is not None:
            self._drag(event.pos())
        else:
            point = self._point(event.pos())
            corner = self._corner(point)
            cursor = (Qt.SizeFDiagCursor if corner in ('tl', 'br') else Qt.SizeBDiagCursor) if corner else (
                Qt.SizeAllCursor if self.selection.contains(point) else Qt.CrossCursor)
            self.setCursor(cursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag(event.pos())
            self._anchor = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm()
        else:
            super().keyPressEvent(event)

    def _confirm(self):
        if self._stale:
            return
        r = self.selection
        if min(r.width(), r.height()) <= 10:
            self.error_label.setText('Kéo chọn một vùng lớn hơn 10 × 10 px trước khi nhấn Enter.')
            return
        width, height = self._selection_size()
        rect = NormalizedRect(r.x() / width, r.y() / height,
                              r.width() / width, r.height() / height)
        regions = tuple(replace(region, rect=rect, enabled=True) if region.id == self._target.id else region
                        for region in self.profile.regions)
        if self._selecting_all:
            regions = tuple(region for region in regions if region.id == self._target.id)
        try:
            draft = replace(self.profile, regions=regions)
            draft = parse_capture_profile(serialize_capture_profile(draft))
        except (ValueError, ConfigError):
            self.error_label.setText('Vùng mới không hợp lệ hoặc chồng vùng khác. Chỉnh lại khung; dùng quản lý nâng cao để sửa nhiều vùng.')
            return
        self.profile_selected.emit(draft)

    def update_context(self, context):
        if context != self.context:
            self.invalidate_source()

    def invalidate_source(self):
        self._stale = True
        self.error_label.setText('Nguồn đã di chuyển, bị ẩn hoặc thay đổi. Nhấn Esc và chọn vùng lại.')

    def reject(self):
        self.cancelled.emit()
        super().reject()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 115))
        if not self.selection.isEmpty():
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.selection, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor('#36d6b0'), 2))
            painter.drawRect(self.selection)
            for p in (self.selection.topLeft(), self.selection.topRight(),
                      self.selection.bottomLeft(), self.selection.bottomRight()):
                painter.fillRect(QRect(p - QPoint(4, 4), p + QPoint(4, 4)), QColor('white'))
