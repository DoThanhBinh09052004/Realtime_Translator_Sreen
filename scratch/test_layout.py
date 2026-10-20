import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
controller = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None)

assert hasattr(controller, "pages"), "Missing pages QStackedWidget"
assert controller.pages.count() == 4, f"Expected 4 pages, got {controller.pages.count()}"
assert hasattr(controller, "sidebar_frame"), "Missing sidebar_frame"
assert hasattr(controller, "nav_buttons"), "Missing nav_buttons list"
assert len(controller.nav_buttons) == 4, f"Expected 4 nav buttons, got {len(controller.nav_buttons)}"

print("[PASS] test_layout passed")
