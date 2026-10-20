import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal
from ui.controller import ControllerWindow
from ui.overlay import Overlay
from core.config import State, load_provider_api_key


class MockWorker(QObject):
    text_translated = pyqtSignal(str)
    text_unchanged = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._interval = 500

    def start_worker(self):
        self._running = True

    def stop_worker(self):
        self._running = False

    def is_running(self):
        return self._running

    def interval(self):
        return self._interval

    def setInterval(self, val):
        self._interval = val


def run_full_integration_test():
    app = QApplication.instance() or QApplication(sys.argv)
    state = State()
    overlay = Overlay()
    worker = MockWorker()

    quit_called = False
    region_called = False

    def on_quit():
        nonlocal quit_called
        quit_called = True

    def on_select_region():
        nonlocal region_called
        region_called = True

    controller = ControllerWindow(
        worker=worker,
        state=state,
        on_select_region=on_select_region,
        on_quit=on_quit,
        overlay=overlay
    )

    # 1. Test Tab Navigation
    assert controller.pages.currentIndex() == 0
    for page_idx in range(4):
        controller._switch_to_page(page_idx)
        assert controller.pages.currentIndex() == page_idx
    controller._switch_to_page(0)
    assert controller.pages.currentIndex() == 0

    # 2. Test AI Engine Page Controls
    controller._switch_to_page(1)
    # Check eye toggle
    controller._toggle_key_visibility()
    assert controller.toggle_key_btn.text() == "🔒"
    controller._toggle_key_visibility()
    assert controller.toggle_key_btn.text() == "👁"

    # 3. Test Subtitle Page & Live Preview Sync
    controller._switch_to_page(3)
    controller.opacity_slider.setValue(72)
    assert state.bg_opacity == 72
    assert "0.72" in controller.live_preview_box.styleSheet()

    # 4. Test OCR Page & Region Trigger
    controller._switch_to_page(2)
    controller.interval_spin.setValue(450)
    assert worker.interval() == 450
    controller._on_select_region_clicked()
    assert region_called is True

    # 5. Test Start / Stop with Validation
    controller._switch_to_page(0)
    active_prov = controller.provider_combo.currentText()
    key = load_provider_api_key(active_prov)
    
    if key.strip():
        controller.start_ocr()
        assert worker.is_running() is True
        assert "Active" in controller.status.text()
        controller.stop_ocr()
        assert worker.is_running() is False
        assert "Stopped" in controller.status.text()
    else:
        controller.start_ocr()
        # Should redirect to AI page
        assert controller.pages.currentIndex() == 1

    print("[PASS] Full UI integration test passed successfully!")


if __name__ == "__main__":
    run_full_integration_test()
