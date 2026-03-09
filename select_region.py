from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont


class RegionSelector(QWidget):
    """
    Widget dùng để chọn vùng OCR bằng cách kéo chuột
    Trả kết quả qua signal (KHÔNG dùng app.exec_)
    """

    # Signal trả về region dạng dict
    region_selected = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

        # Cửa sổ phủ toàn màn hình, không viền, luôn ở trên
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setWindowState(Qt.WindowFullScreen)

        # Nền trong suốt để vẽ overlay
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Con trỏ chuột dạng dấu cộng
        self.setCursor(Qt.CrossCursor)

        # Điểm bắt đầu và kết thúc khi kéo chuột
        self.start = None
        self.end = None
        self.dragging = False

    def mousePressEvent(self, event):
        """
        Bắt đầu kéo chuột
        """
        self.start = event.pos()
        self.end = self.start
        self.dragging = True
        self.update()

    def mouseMoveEvent(self, event):
        """
        Cập nhật vùng kéo khi di chuyển chuột
        """
        if self.dragging:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        """
        Kết thúc kéo chuột, emit vùng đã chọn
        """
        if self.start and self.end:
            # Chuẩn hóa tọa độ (kéo ngược vẫn đúng)
            x1 = min(self.start.x(), self.end.x())
            y1 = min(self.start.y(), self.end.y())
            x2 = max(self.start.x(), self.end.x())
            y2 = max(self.start.y(), self.end.y())

            # Tạo region dict đúng chuẩn mss
            region = {
                "top": y1,
                "left": x1,
                "width": x2 - x1,
                "height": y2 - y1
            }

            # Gửi region ra ngoài
            self.region_selected.emit(region)

        self.dragging = False
        self.close()

    def paintEvent(self, event):
        """
        Vẽ overlay và khung chọn
        """
        painter = QPainter(self)

        # Lớp phủ tối toàn màn hình
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.start and self.end and self.dragging:
            rect = QRect(self.start, self.end).normalized()

            # Tạo vùng trong suốt tại vùng chọn
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)

            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Vẽ viền đỏ
            painter.setPen(QPen(Qt.red, 2))
            painter.drawRect(rect)

            # Viền trắng nét đứt bên trong
            painter.setPen(QPen(Qt.white, 1, Qt.DashLine))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

            # Hiển thị kích thước vùng chọn
            info = f"{rect.width()} x {rect.height()}"
            painter.setFont(QFont("Arial", 12))
            painter.setPen(Qt.white)

            text_rect = painter.fontMetrics().boundingRect(info)
            painter.drawText(
                rect.right() - text_rect.width() - 8,
                rect.bottom() - 8,
                info
            )