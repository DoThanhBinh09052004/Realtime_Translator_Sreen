from math import floor, ceil
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget
from core.blocks.geometry import overlay_window_rect
from ui.capture_exclusion import set_capture_excluded
from ui.block_layout import layout_blocks, paint_blocks


class BlockOverlay(QWidget):
    block_error = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Keep the Python facade alive during native paint callbacks. Qt parent
        # ownership alone does not retain its Python wrapper during cyclic GC.
        self._owner = parent
        self._protected = False
        self._checking = False
        self._frame = None
        self.placed_blocks = ()
        self.bg_hex, self.opacity_pct, self.text_hex, self.font_size = '#1e1e2e', 80, '#ffffff', 22
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def _protect(self):
        if self._checking:
            return False
        self._checking = True
        try:
            error = set_capture_excluded(int(self.winId()))
            self._protected = error is None
            if error:
                self.clear()
                self.block_error.emit(error)
            return self._protected
        finally:
            self._checking = False

    def event(self, event):
        if event.type() == QEvent.WinIdChange and hasattr(self, '_protected'):
            self._protected = False
            self.placed_blocks = ()
            if not self._checking and self._frame is not None and int(self.effectiveWinId()):
                self._protect()
            return True
        return super().event(event)

    def set_frame(self, frame):
        self._frame = frame
        if not frame.blocks:
            self.clear()
            return
        if not self._protected and not self._protect():
            return
        r = overlay_window_rect(frame.geometry)
        self.setGeometry(floor(r.x), floor(r.y), ceil(r.width), ceil(r.height))
        self.placed_blocks = layout_blocks(frame, max_font_px=self.font_size)
        self.show()
        self.update()

    def apply_style(self, bg_hex=None, opacity_pct=None, text_hex=None, font_size=None):
        for key, value in locals().copy().items():
            if key != 'self' and value is not None:
                setattr(self, key, value)
        if self._frame is not None:
            self.set_frame(self._frame)

    def clear(self):
        self._frame = None
        self.placed_blocks = ()
        self.hide()
        self.update()

    def closeEvent(self, event):
        self.clear()
        super().closeEvent(event)

    def paintEvent(self, event):
        if not self._protected:
            return
        bg = QColor(self.bg_hex)
        bg.setAlpha(round(255*self.opacity_pct/100))
        painter = QPainter(self)
        paint_blocks(painter, self.placed_blocks, bg_color=bg, text_color=QColor(self.text_hex))
