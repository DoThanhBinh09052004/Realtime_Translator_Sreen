from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QCursor
from core.blocks.models import Rect
from core.blocks.geometry import qt_selection_to_physical
from ui.screen_geometry import ScreenGeometryProvider


class RegionSelector(QWidget):
    """
    Widget phủ toàn màn hình dùng để chọn vùng OCR bằng cách kéo chuột.
    Trả kết quả qua signal region_selected dạng dict.
    """

    region_selected = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, *, geometry_provider=None):
        super().__init__()
        self.geometry_provider = geometry_provider or ScreenGeometryProvider(self)
        cursor = QCursor.pos()
        self.mapping = next((s for s in self.geometry_provider.snapshot()
                             if s.logical_rect.x <= cursor.x() < s.logical_rect.right
                             and s.logical_rect.y <= cursor.y() < s.logical_rect.bottom), None)

        # Cửa sổ phủ toàn màn hình, không viền, luôn ở trên
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        if self.mapping is not None:
            r = self.mapping.logical_rect
            self.setGeometry(int(r.x), int(r.y), int(r.width), int(r.height))
        else:
            self.setWindowState(Qt.WindowFullScreen)

        # Nền trong suốt để vẽ overlay
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        self.start = None
        self.end = None
        self.dragging = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()

    def mousePressEvent(self, event):
        self.start = event.pos()
        self.end = self.start
        self.dragging = True
        self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.end = event.pos()
        if self.start and self.end:
            # Chuẩn hóa tọa độ (kéo ngược hoặc xuôi đều đúng)
            x1 = min(self.start.x(), self.end.x())
            y1 = min(self.start.y(), self.end.y())
            x2 = max(self.start.x(), self.end.x())
            y2 = max(self.start.y(), self.end.y())

            w = x2 - x1
            h = y2 - y1
            if w > 10 and h > 10:
                if self.mapping is not None:
                    r = self.mapping.logical_rect
                    region = qt_selection_to_physical(Rect(r.x+x1, r.y+y1, w, h), self.mapping)
                    self.region_selected.emit(region)
                else:
                    self.cancelled.emit()
            else:
                self.cancelled.emit()

        self.dragging = False
        self.close()


    def paintEvent(self, event):
        painter = QPainter(self)

        # Lớp phủ làm tối toàn màn hình
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.start and self.end and self.dragging:
            rect = QRect(self.start, self.end).normalized()

            # Tạo vùng trong suốt tại khung đang chọn
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)

            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Viền đỏ nổi bật
            painter.setPen(QPen(Qt.red, 2))
            painter.drawRect(rect)

            # Viền trắng nét đứt bên trong
            painter.setPen(QPen(Qt.white, 1, Qt.DashLine))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

            # Hiển thị thông số kích thước pixel
            info = f"{rect.width()} x {rect.height()}"
            painter.setFont(QFont("Arial", 12))
            painter.setPen(Qt.white)

            text_rect = painter.fontMetrics().boundingRect(info)
            painter.drawText(
                rect.right() - text_rect.width() - 8,
                rect.bottom() - 8,
                info
            )
