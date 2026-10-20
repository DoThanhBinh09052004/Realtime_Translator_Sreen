import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from ui.icons import get_lucide_icon, LUCIDE_ICONS

app = QApplication.instance() or QApplication(sys.argv)

def test_icons():
    assert len(LUCIDE_ICONS) >= 12
    required = [
        "zap", "layout-dashboard", "bot", "languages", "palette",
        "play", "square", "scan", "sliders", "eye", "eye-off",
        "check-circle", "alert-circle", "log-out", "activity", "maximize-2"
    ]
    for name in required:
        assert name in LUCIDE_ICONS, f"Missing icon {name} in LUCIDE_ICONS"
        icon = get_lucide_icon(name, color="#6366f1", size=20)
        assert not icon.isNull(), f"Icon {name} returned null QIcon"
    print("[PASS] test_lucide_icons passed")

if __name__ == "__main__":
    test_icons()
