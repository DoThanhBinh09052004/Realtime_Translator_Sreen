import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
c = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None)

# Verify Page 1 elements
assert hasattr(c, "start_btn"), "Missing start_btn"
assert hasattr(c, "stop_btn"), "Missing stop_btn"
assert hasattr(c, "metric_cards"), "Missing metric_cards"
assert "status" in c.metric_cards
assert "ai" in c.metric_cards
assert "lang" in c.metric_cards
assert "region" in c.metric_cards

# Verify Page 2 elements
assert hasattr(c, "provider_combo"), "Missing provider_combo"
assert hasattr(c, "model_combo"), "Missing model_combo"
assert hasattr(c, "api_key_input"), "Missing api_key_input"
assert hasattr(c, "toggle_key_btn"), "Missing toggle_key_btn"
assert hasattr(c, "key_card"), "Missing key_card"

# Test dynamic provider change
c.provider_combo.setCurrentText("OpenAI")
assert c.provider_combo.currentText() == "OpenAI"
assert c.model_combo.count() > 0

# Test start_ocr redirect when key is missing or checked
c.api_key_input.setText("")
c.start_ocr()
# Should redirect to Page index 1 (AI Engine)
assert c.pages.currentIndex() == 1
assert "Lỗi" in c.status.text() or "Thiếu" in c.status.text()

print("[PASS] test_pages_1_2 passed")
