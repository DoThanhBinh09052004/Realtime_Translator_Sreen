"""Native Windows checkerboard capture test, no OCR, credentials or API calls.

Run from the repository: .venv/Scripts/python.exe docs/testing/block_overlay_smoke.py
Shows a temporary test window for about two seconds and prints JSON evidence.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.pop('QT_QPA_PLATFORM', None)
import numpy as np
import mss
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QApplication, QWidget
from core.blocks.models import Rect, CaptureGeometry, OverlayFrame, OverlayBlock
from core.blocks.geometry import qt_selection_to_physical
from ui.screen_geometry import ScreenGeometryProvider
from ui.block_overlay import BlockOverlay


def main():
    app = QApplication([])
    screens = ScreenGeometryProvider(app).snapshot()
    if not screens:
        print(json.dumps({'error': 'No matched Qt/Win32 monitor'}))
        return 1
    screen = screens[0]
    r = screen.logical_rect
    class Checkerboard(QWidget):
        def paintEvent(self, event):
            p = QPainter(self)
            for y in range(0, self.height(), 16):
                for x in range(0, self.width(), 16):
                    p.fillRect(x, y, 16, 16, QColor('#fafafa' if (x//16+y//16)%2 else '#163658'))
            p.setPen(QColor('#ff6000'))
            p.drawText(20, 35, 'ORIGINAL TEXT / capture must retain this pattern')
    window = Checkerboard()
    window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    window.setGeometry(int(r.x+80), int(r.y+80), 420, 180)
    window.show()
    region = qt_selection_to_physical(Rect(r.x+80, r.y+80, 420, 180), screen)
    geometry = CaptureGeometry(Rect(region['left'], region['top'], region['width'], region['height']), screen, (region['width'], region['height']))
    overlay = BlockOverlay()
    errors, evidence = [], {}
    overlay.block_error.connect(lambda err: errors.append(err.code))
    def capture():
        with mss.mss() as sct:
            return np.array(sct.grab(region))
    baseline = []
    def show_overlay():
        baseline.append(capture())
        overlay.apply_style(bg_hex='#cc0088', opacity_pct=100)
        overlay.set_frame(OverlayFrame(1, 1, geometry, (
            OverlayBlock(1, 'ORIGINAL', 'BẢN DỊCH PHỦ LÊN CHỮ', Rect(10, 10, 240, 40)),)))
        QTimer.singleShot(700, compare)
    def compare():
        after = capture()
        difference = np.abs(after.astype(int)-baseline[0].astype(int))
        evidence.update(screen=screen.name, scale=screen.physical_rect.width/screen.logical_rect.width,
                        overlay_visible=overlay.isVisible(), protected=overlay._protected,
                        click_through=bool(overlay.windowFlags() & Qt.WindowTransparentForInput),
                        errors=errors, mean_difference=float(difference.mean()),
                        exact_original_pixels=bool(np.array_equal(after, baseline[0])))
        print(json.dumps(evidence))
        overlay.close()
        window.close()
        app.quit()
    QTimer.singleShot(700, show_overlay)
    QTimer.singleShot(5000, app.quit)
    app.exec_()
    return 0 if evidence.get('exact_original_pixels') and evidence.get('overlay_visible') and evidence.get('protected') else 1


if __name__ == '__main__':
    raise SystemExit(main())
