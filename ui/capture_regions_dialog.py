"""Draft-only, keyboard accessible normalized region editor."""
from dataclasses import replace
from uuid import uuid4
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from core.capture.models import CaptureRegion, NormalizedRect
from core.capture.profile import parse_capture_profile, serialize_capture_profile


class _Preview(QLabel):
    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.image = image
        self.rectangles = ()
        self.setMinimumHeight(150)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.image is not None:
            pix = QPixmap.fromImage(self.image).scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x, y = (self.width()-pix.width())//2, (self.height()-pix.height())//2
            painter.drawPixmap(x, y, pix)
            width, height = pix.width(), pix.height()
        else:
            x = y = 0; width, height = self.width(), self.height()
        for label, rect, exclusion in self.rectangles:
            painter.setPen(QPen(QColor('#ffb454' if exclusion else '#36d6b0'), 2))
            left, top = x+rect.x*width, y+rect.y*height
            painter.drawRect(int(left), int(top), int(rect.width*width), int(rect.height*height))
            painter.drawText(int(left)+4, int(top)+16, label)


class CaptureRegionsDialog(QDialog):
    profile_selected = pyqtSignal(object)
    cancelled = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self, profile, image, context, parent=None):
        super().__init__(parent)
        self.profile, self.context = profile, context
        self._stale = False
        self.setWindowTitle('Quản lý vùng quét')
        self.resize(850, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Nhập X / Y / Rộng / Cao theo % ảnh nguồn. OCR: tối đa 8 vùng, loại trừ: tối đa 16.\nCác vùng OCR dùng chung ngôn ngữ và chia tổng 32 khối theo thứ tự.'))
        self.preview = _Preview(image); layout.addWidget(self.preview, 1)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(('Tên', 'Bật', 'Loại', 'X %', 'Y %', 'Rộng %', 'Cao %'))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        for region in profile.regions:
            self._append(region.name, region.enabled, 'OCR', region.rect, region.id)
        for index, rect in enumerate(profile.exclusions):
            self._append(f'Loại trừ {index+1}', True, 'Loại trừ', rect, None)
        row = QHBoxLayout()
        for title, callback in [('Thêm OCR', self.add_region), ('Thêm loại trừ', self.add_exclusion),
                                ('Xóa', lambda: self.remove_row(self.table.currentRow())),
                                ('Lên', lambda: self.move_row(-1)), ('Xuống', lambda: self.move_row(1)),
                                ('Cập nhật ảnh', self.refresh_requested.emit)]:
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        self.error_label = QLabel(); self.error_label.setWordWrap(True); layout.addWidget(self.error_label)
        buttons = QHBoxLayout(); buttons.addStretch()
        cancel = QPushButton('Hủy'); cancel.clicked.connect(self.reject); buttons.addWidget(cancel)
        self.apply_btn = QPushButton('Áp dụng'); self.apply_btn.clicked.connect(self._apply); buttons.addWidget(self.apply_btn)
        layout.addLayout(buttons)
        self.table.itemChanged.connect(self.validate_draft)
        self.validate_draft()

    def _append(self, name, enabled, kind, rect, region_id):
        row = self.table.rowCount(); self.table.insertRow(row)
        name_item = QTableWidgetItem(name); name_item.setData(Qt.UserRole, region_id)
        self.table.setItem(row, 0, name_item)
        checked = QTableWidgetItem(); checked.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
        self.table.setItem(row, 1, checked)
        kind_item = QTableWidgetItem(kind); kind_item.setFlags(kind_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 2, kind_item)
        for col, value in enumerate((rect.x, rect.y, rect.width, rect.height), 3):
            self.table.setItem(row, col, QTableWidgetItem(f'{value*100:.8g}'))

    def add_region(self):
        self.table.blockSignals(True)
        self._append(f'Vùng {self.table.rowCount()+1}', True, 'OCR', NormalizedRect(0, 0, 1, 1), str(uuid4()))
        self.table.blockSignals(False); self.validate_draft()

    def add_exclusion(self):
        self.table.blockSignals(True)
        self._append('Loại trừ', True, 'Loại trừ', NormalizedRect(0, 0, .1, .1), None)
        self.table.blockSignals(False); self.validate_draft()

    def remove_row(self, row):
        if row >= 0: self.table.removeRow(row)
        self.validate_draft()

    def move_row(self, delta):
        row = self.table.currentRow(); target = row+delta
        if row < 0 or not 0 <= target < self.table.rowCount(): return
        self.table.blockSignals(True)
        first = [self.table.takeItem(row, col) for col in range(7)]
        second = [self.table.takeItem(target, col) for col in range(7)]
        for col in range(7):
            self.table.setItem(row, col, second[col]); self.table.setItem(target, col, first[col])
        self.table.setCurrentCell(target, 0); self.table.blockSignals(False); self.validate_draft()

    def draft(self):
        regions, exclusions = [], []
        for row in range(self.table.rowCount()):
            rect = NormalizedRect(*(float(self.table.item(row, col).text())/100 for col in range(3, 7)))
            enabled = self.table.item(row, 1).checkState() == Qt.Checked
            if self.table.item(row, 2).text() == 'OCR':
                regions.append(CaptureRegion(self.table.item(row, 0).data(Qt.UserRole), self.table.item(row, 0).text(), rect, enabled))
            elif enabled:
                exclusions.append(rect)
        profile = replace(self.profile, regions=tuple(regions), exclusions=tuple(exclusions))
        return parse_capture_profile(serialize_capture_profile(profile))

    def validate_draft(self):
        try:
            if self._stale: raise ValueError('Kích thước nguồn đã đổi. Hãy cập nhật ảnh trước khi áp dụng.')
            profile = self.draft()
        except Exception:
            self.apply_btn.setEnabled(False)
            self.error_label.setText('Kích thước nguồn đã đổi. Hãy cập nhật ảnh.' if self._stale else 'Kiểm tra tọa độ %, tên, giới hạn 1–8 vùng OCR / 16 loại trừ, vùng OCR không chồng nhau và có ít nhất một vùng bật.')
            return False
        self.apply_btn.setEnabled(True); self.error_label.clear()
        self.preview.rectangles = tuple((region.name+' · OCR', region.rect, False) for region in profile.regions) + tuple((f'Loại trừ {i+1}', rect, True) for i, rect in enumerate(profile.exclusions))
        self.preview.update()
        return True

    def update_context(self, context):
        if (context.binding_epoch != self.context.binding_epoch
                or context.geometry.image_size_px != self.context.geometry.image_size_px):
            self._stale = True; self.validate_draft()

    def _apply(self):
        if self.validate_draft(): self.profile_selected.emit(self.draft())

    def reject(self):
        self.cancelled.emit(); super().reject()
