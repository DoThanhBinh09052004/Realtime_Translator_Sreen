import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter, QPainterPath, QIcon
from PyQt5.QtCore import Qt

app = QApplication.instance() or QApplication(sys.argv)

logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "logo.png")
assert os.path.exists(logo_path), f"Logo not found at {logo_path}"

icon = QIcon(logo_path)
assert not icon.isNull(), "Logo QIcon is null"

print("[PASS] Logo file exists and loads successfully as QIcon")
