"""Explicit monitor/window selection; runtime identity never enters config."""
from dataclasses import replace
from uuid import uuid4
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel
from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect


class CaptureSettings(QWidget):
    source_selected = pyqtSignal(object, object)

    def __init__(self, profile=None, *, screens=None, windows=None, parent=None):
        super().__init__(parent)
        self.profile = profile
        self._screens = screens or (lambda: ())
        self._windows = windows or self._enumerate_windows
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.kind_combo = QComboBox(); self.kind_combo.addItem('Màn hình', 'desktop'); self.kind_combo.addItem('Cửa sổ', 'window')
        self.kind_combo.setCurrentIndex(1 if profile and profile.source_kind == 'window' else 0)
        layout.addWidget(self.kind_combo)
        self.source_combo = QComboBox(); self.source_combo.setAccessibleName('Nguồn chụp')
        layout.addWidget(self.source_combo)
        row = QHBoxLayout(); self.refresh_btn = QPushButton('Cập nhật danh sách'); self.choose_btn = QPushButton('Chọn nguồn')
        row.addWidget(self.refresh_btn); row.addWidget(self.choose_btn); layout.addLayout(row)
        self.status_label = QLabel('Chọn nguồn để xem trước và chỉnh vùng OCR.'); self.status_label.setWordWrap(True); layout.addWidget(self.status_label)
        self.refresh_btn.clicked.connect(self.refresh_sources); self.kind_combo.currentIndexChanged.connect(self.refresh_sources)
        self.choose_btn.clicked.connect(self.choose_source)
        self.refresh_sources()

    @staticmethod
    def _enumerate_windows():
        from core.capture.windows import enumerate_capture_windows
        return enumerate_capture_windows()

    def set_sources(self, screens):
        self._screens = screens; self.refresh_sources()

    def set_profile(self, profile, *, bound=False):
        self.profile = profile
        if profile is not None:
            self.kind_combo.setCurrentIndex(1 if profile.source_kind == 'window' else 0)
            name = profile.window_hint if profile.source_kind == 'window' else profile.monitor_name
            self.status_label.setText(f'{name or "Cửa sổ"} · {len(profile.regions)} vùng OCR' + ('' if bound else ' · Hãy chọn lại nguồn.'))

    def refresh_sources(self, *args):
        self.source_combo.clear()
        try:
            if self.kind_combo.currentData() == 'desktop':
                for screen in self._screens(): self.source_combo.addItem(screen.name, screen)
            else:
                for window in self._windows():
                    if window.available:
                        self.source_combo.addItem(f'{window.title} · {window.process_name} · HWND {window.identity.hwnd}', window)
            self.choose_btn.setEnabled(self.source_combo.count() > 0)
            if not self.source_combo.count(): self.status_label.setText('Không có nguồn phù hợp. Mở cửa sổ rồi cập nhật danh sách.')
        except Exception:
            self.choose_btn.setEnabled(False); self.status_label.setText('Không thể liệt kê nguồn. Kiểm tra quyền ứng dụng rồi thử lại.')

    def choose_source(self):
        selected = self.source_combo.currentData()
        if selected is None: return
        kind = self.kind_combo.currentData()
        base = self.profile or CaptureProfile(1, 'desktop', 'temporary', None,
            (CaptureRegion(str(uuid4()), 'Vùng 1', NormalizedRect(0, 0, 1, 1), True),), ())
        profile = replace(base, source_kind=kind, monitor_name=selected.name if kind == 'desktop' else None,
                          window_hint=selected.title if kind == 'window' else None)
        self.source_selected.emit(profile, selected.identity if kind == 'window' else None)
