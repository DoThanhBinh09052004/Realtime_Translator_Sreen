import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from ui.overlay import Overlay
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
overlay = Overlay()
c = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None, overlay=overlay)

# Verify Page 3 controls
assert hasattr(c, "src_combo"), "Missing src_combo"
assert hasattr(c, "tgt_combo"), "Missing tgt_combo"
assert hasattr(c, "interval_spin"), "Missing interval_spin"

# Verify Page 4 controls
assert hasattr(c, "bg_color_btn"), "Missing bg_color_btn"
assert hasattr(c, "text_color_btn"), "Missing text_color_btn"
assert hasattr(c, "opacity_slider"), "Missing opacity_slider"
assert hasattr(c, "opacity_val_lbl"), "Missing opacity_val_lbl"
assert hasattr(c, "live_preview_box"), "Missing live_preview_box"

# Test Opacity Slider change and sync
c.opacity_slider.setValue(45)
assert c.opacity_val_lbl.text() == "45%"
assert state.bg_opacity == 45
assert "0.45" in c.live_preview_box.styleSheet()

# Test Language Change sync
c.src_combo.setCurrentText("Japanese")
assert state.source == "Japanese"
assert "Japanese" in c.metric_cards["lang"].val_lbl.text()

c.tgt_combo.setCurrentText("English")
assert state.target == "English"
assert "English" in c.metric_cards["lang"].val_lbl.text()

# Test Interval Change
c.interval_spin.setValue(650)
assert c.interval_spin.value() == 650

print("[PASS] test_pages_3_4 passed")
