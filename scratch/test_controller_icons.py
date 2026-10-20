import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
c = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None)

def test_controller_icons():
    # 1. Nav buttons must have QIcons and clean text (no emojis)
    for btn in c.nav_buttons:
        assert not btn.icon().isNull(), f"Nav button {btn.text()} missing Lucide icon"
        has_emoji = any(ord(char) > 10000 for char in btn.text())
        assert not has_emoji, f"Emoji still found in nav button text: {btn.text()}"

    # 2. Hero buttons must have Lucide icons
    assert not c.start_btn.icon().isNull(), "start_btn missing Lucide icon"
    assert not c.stop_btn.icon().isNull(), "stop_btn missing Lucide icon"

    # 3. Eye toggle button must have Lucide icon
    assert not c.toggle_key_btn.icon().isNull(), "toggle_key_btn missing Lucide icon"

    print("[PASS] test_controller_icons passed")

if __name__ == "__main__":
    test_controller_icons()
