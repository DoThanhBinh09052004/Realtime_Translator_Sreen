"""Explicit monitor/window selection; runtime identity never enters config."""
from dataclasses import replace
from uuid import uuid4
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QSizePolicy
from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect
from ui.styles import TOKENS, set_style, apply_widget_theme, button_style
from ui.icons import set_theme_icon


class CaptureSettings(QWidget):
    source_selected = pyqtSignal(object, object)

    def __init__(self, profile=None, *, screens=None, windows=None, parent=None, compact=False):
        super().__init__(parent)
        self.profile = profile
        self._bound = False
        self.compact = compact
        self._screens = screens or (lambda: ())
        self._windows = windows or self._enumerate_windows
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.summary_label = QLabel(); self.summary_label.setWordWrap(True)
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        set_style(self.summary_label, f'color:{TOKENS["positive"]};font-size:11px;')
        layout.addWidget(self.summary_label)
        self.change_btn = QPushButton('Đổi nguồn')
        set_style(self.change_btn, button_style('secondary', 'tokens'))
        self.change_btn.clicked.connect(self._edit_source)
        layout.addWidget(self.change_btn)
        self.summary_label.hide(); self.change_btn.hide()
        self.kind_combo = QComboBox(); self.kind_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); self.kind_combo.addItem('Màn hình', 'desktop'); self.kind_combo.addItem('Cửa sổ', 'window')
        self.kind_combo.setCurrentIndex(1 if profile and profile.source_kind == 'window' else 0)
        self.kind_buttons = []
        if compact:
            kinds = QHBoxLayout()
            kinds.addWidget(QLabel('Nguồn chụp'))
            for index, title in enumerate(('Màn hình', 'Cửa sổ')):
                button = QPushButton(title)
                button.setMaximumWidth(95)
                button.setCheckable(True)
                button.setAutoExclusive(True)
                button.clicked.connect(lambda checked=False, i=index: self.kind_combo.setCurrentIndex(i))
                kinds.addWidget(button)
                self.kind_buttons.append(button)
            layout.addLayout(kinds)
            self.kind_combo.hide()
        else:
            layout.addWidget(self.kind_combo)
        self.source_combo = QComboBox(); self.source_combo.setAccessibleName('Nguồn chụp'); self.source_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        row = QHBoxLayout(); self.refresh_btn = QPushButton('Cập nhật danh sách'); self.choose_btn = QPushButton('Chọn nguồn')
        if compact:
            row.addWidget(self.source_combo, 1)
            row.addWidget(self.choose_btn)
            self.refresh_btn.setText('')
            self.refresh_btn.setToolTip('Cập nhật danh sách màn hình và cửa sổ')
            self.refresh_btn.setAccessibleName('Cập nhật danh sách nguồn chụp')
            set_theme_icon(self.refresh_btn, 'refresh-cw', size=15)
            set_theme_icon(self.choose_btn, 'check', size=15)
            row.addWidget(self.refresh_btn)
        else:
            layout.addWidget(self.source_combo)
            row.addWidget(self.refresh_btn)
            row.addWidget(self.choose_btn)
        layout.addLayout(row)
        set_style(self.choose_btn, button_style('secondary' if compact else 'primary', 'tokens'))
        set_style(self.refresh_btn, button_style('secondary', 'tokens'))
        self.status_label = QLabel('Chọn nguồn để xem trước và chỉnh vùng OCR.'); self.status_label.setWordWrap(True); layout.addWidget(self.status_label)
        if compact:
            layout.removeWidget(self.summary_label)
            layout.addWidget(self.summary_label)
        self.refresh_btn.clicked.connect(self.refresh_sources); self.kind_combo.currentIndexChanged.connect(self.refresh_sources)
        self.choose_btn.clicked.connect(self.choose_source)
        self.source_combo.currentIndexChanged.connect(self._pending_source)
        self.refresh_sources()

    def apply_theme(self, theme):
        apply_widget_theme(self, theme)

    @staticmethod
    def _enumerate_windows():
        from core.capture.windows import enumerate_capture_windows
        return enumerate_capture_windows()

    def set_sources(self, screens):
        self._screens = screens; self.refresh_sources()

    def set_profile(self, profile, *, bound=False):
        previous_profile = self.profile
        self.profile = profile
        if profile is not None:
            if not self.compact or previous_profile != profile or not self._bound:
                self.kind_combo.setCurrentIndex(1 if profile.source_kind == 'window' else 0)
            name = profile.window_hint if profile.source_kind == 'window' else profile.monitor_name
            self.status_label.setText(f'{name or "Cửa sổ"} · {len(profile.regions)} vùng OCR' + ('' if bound else ' · Hãy chọn lại nguồn.'))
            if bound:
                kind = 'Cửa sổ' if profile.source_kind == 'window' else 'Màn hình'
                self.summary_label.setText(f'✓ Nguồn đang dùng: {kind} · {name or "Cửa sổ"}')
                self.summary_label.show()
                self.summary_label.setToolTip(self.summary_label.text())
                self.change_btn.setVisible(not self.compact)
                self._show_picker(self.compact)
                self.status_label.setText('Nguồn đã sẵn sàng. Bước tiếp theo: Khoanh vùng đọc.')
                self.status_label.setVisible(not self.compact)
                set_style(self.status_label, f'color:{TOKENS["positive"]};font-size:11px;')
            else:
                self.summary_label.hide()
                self.change_btn.hide()
                self._show_picker(True)
                self.status_label.show()
                set_style(self.status_label, f'color:{TOKENS["warning"]};font-size:11px;')
        self._bound = bound

    def _show_picker(self, visible):
        for widget in (self.kind_combo, self.source_combo, self.refresh_btn, self.choose_btn):
            widget.setVisible(visible and not (self.compact and widget is self.kind_combo))

    def _edit_source(self):
        self._show_picker(True)
        self.change_btn.hide()
        self._pending_source()
        self.source_combo.setFocus()

    def _pending_source(self, *args):
        self.status_label.show()
        self.source_combo.setToolTip(self.source_combo.currentText())
        window = self.kind_combo.currentData() == 'window'
        self.choose_btn.setText('Xác nhận' if self.compact else ('Dùng cửa sổ này' if window else 'Dùng màn hình này'))
        for index, button in enumerate(self.kind_buttons):
            button.setChecked(index == self.kind_combo.currentIndex())
            set_style(button, button_style('secondary', 'tokens') + f'QPushButton:checked {{background:{TOKENS["raised"]};font-weight:600;}}')
        self.status_label.setText('Chưa áp dụng · Bấm nút bên trên để xác nhận nguồn cần dịch.')
        set_style(self.status_label, f'color:{TOKENS["warning"]};font-size:11px;')

    def refresh_sources(self, *args):
        self._pending_source()
        self.source_combo.clear()
        try:
            if self.kind_combo.currentData() == 'desktop':
                for screen in self._screens(): self.source_combo.addItem(screen.name, screen)
            else:
                available_windows = [w for w in self._windows() if getattr(w, 'available', True)]
                from collections import Counter
                counts = Counter((w.title, getattr(w, 'process_name', '')) for w in available_windows)
                seen = Counter()
                for window in available_windows:
                    key = (window.title, getattr(window, 'process_name', ''))
                    seen[key] += 1
                    proc = f" · {window.process_name}" if getattr(window, 'process_name', '') else ""
                    idx = f" (#{seen[key]})" if counts[key] > 1 else ""
                    self.source_combo.addItem(f"{window.title}{proc}{idx}", window)
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
