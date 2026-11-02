"""Image-based window selection with an explicit desktop-capture escape route."""
from PyQt5.QtCore import Qt, QPoint, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea
from ui.direct_region_selector import DirectRegionSelector
from ui.styles import button_style, set_style, apply_widget_theme, get_app_stylesheet


class ImageSelectionCanvas(DirectRegionSelector):
    def __init__(self, profile, image, context):
        super().__init__(profile, context)
        self.setWindowFlags(Qt.Widget)
        self.image = image
        self.error_label.hide()
        self.confirm_btn.hide()
        self.cancel_btn.hide()
        self.select_all_btn.hide()
        if image is not None and not image.isNull():
            self.resize(image.size().scaled(900, 480, Qt.KeepAspectRatio))
        else:
            self.resize(600, 300)
            self.setEnabled(False)

    def _selection_size(self):
        if self.image is None or self.image.isNull():
            return 600, 300
        return self.image.width(), self.image.height()

    def _point(self, pos):
        width, height = self._selection_size()
        return super()._point(QPoint(round(pos.x() * width / max(1, self.width())),
                                     round(pos.y() * height / max(1, self.height()))))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#141820'))
        if self.image is None or self.image.isNull():
            return
        painter.drawImage(self.rect(), self.image)
        width, height = self._selection_size()
        r = self.selection
        if not r.isEmpty():
            rect = QRectF(r.x() * self.width() / width, r.y() * self.height() / height,
                          r.width() * self.width() / width, r.height() * self.height() / height)
            painter.setPen(QPen(QColor('#36d6b0'), 2))
            painter.drawRect(rect)
            for corner in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
                painter.fillRect(QRectF(corner.x()-4, corner.y()-4, 8, 8), Qt.white)


class WindowRegionPicker(QDialog):
    profile_selected = pyqtSignal(object)
    cancelled = pyqtSignal()
    refresh_requested = pyqtSignal()
    screen_fallback_requested = pyqtSignal()

    def __init__(self, profile, image, context, parent=None):
        super().__init__(parent)
        set_style(self, get_app_stylesheet('tokens'))
        self.setWindowTitle('Khoanh vùng chữ trong cửa sổ')
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        heading = QLabel('Kéo khoanh phần chữ trên ảnh · Kéo bên trong để di chuyển · Kéo góc để chỉnh')
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.select_all_btn = QPushButton('Chọn toàn bộ cửa sổ')
        set_style(self.select_all_btn, button_style('secondary', 'tokens'))
        layout.addWidget(self.select_all_btn)
        self.canvas = ImageSelectionCanvas(profile, image, context)
        self.select_all_btn.clicked.connect(self.canvas.select_all)
        area = QScrollArea()
        area.setAlignment(Qt.AlignCenter)
        area.setWidget(self.canvas)
        layout.addWidget(area, 1)
        row = QHBoxLayout()
        for title, callback in (('Thu nhỏ −', lambda: self._zoom(.8)), ('Phóng to +', lambda: self._zoom(1.25)),
                                ('Vẽ lại vùng', self._reset), ('Chụp lại ảnh', self.refresh_requested.emit)):
            button = QPushButton(title)
            set_style(button, button_style('secondary', 'tokens'))
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        self.canvas.error_label.deleteLater()
        self.canvas.error_label = self.error_label
        missing = image is None or image.isNull()
        self.select_all_btn.setEnabled(not missing)
        self.error_label.setText('Không thấy video hoặc ảnh bị thiếu? Dùng cách khoanh trên màn hình bên dưới.' if missing else
                                f'Ảnh nguồn: {image.width()} × {image.height()} px. Nếu ảnh chỉ có thanh điều khiển, hãy khoanh trên màn hình.')
        self.fallback_btn = QPushButton('Không thấy hình video? Khoanh trên màn hình')
        set_style(self.fallback_btn, button_style('secondary', 'tokens'))
        self.fallback_btn.clicked.connect(self.screen_fallback_requested.emit)
        layout.addWidget(self.fallback_btn)
        notice = QLabel('Cách màn hình: video cần hiện và không bị che. Xác nhận xong sẽ đổi nguồn OCR sang màn hình; di chuyển video thì cần khoanh lại.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton('Hủy')
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.apply_btn = QPushButton('✓ Dùng vùng này')
        set_style(self.apply_btn, button_style('primary', 'tokens'))
        self.apply_btn.setMinimumHeight(40)
        self.apply_btn.setEnabled(not missing)
        self.apply_btn.clicked.connect(self.canvas._confirm)
        footer.addWidget(self.apply_btn)
        layout.addLayout(footer)
        self.canvas.profile_selected.connect(self.profile_selected.emit)
        self.canvas.cancelled.connect(self.reject)

    def apply_theme(self, theme):
        apply_widget_theme(self, theme)

    def _zoom(self, factor):
        width = max(160, min(6000, round(self.canvas.width() * factor)))
        source_width, source_height = self.canvas._selection_size()
        self.canvas.resize(width, max(1, round(width * source_height / source_width)))

    def _reset(self):
        from PyQt5.QtCore import QRect
        self.canvas.selection = QRect()
        self.canvas._selecting_all = False
        self.canvas.update()

    def update_context(self, context):
        self.canvas.update_context(context)
        if self.canvas._stale:
            self.apply_btn.setEnabled(False)
            self.select_all_btn.setEnabled(False)

    def invalidate_source(self):
        self.canvas.invalidate_source()
        self.apply_btn.setEnabled(False)
        self.select_all_btn.setEnabled(False)

    def reject(self):
        self.cancelled.emit()
        super().reject()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.canvas._confirm()
        else:
            super().keyPressEvent(event)
