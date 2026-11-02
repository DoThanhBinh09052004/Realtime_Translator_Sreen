import pytest
import subprocess
import sys
import textwrap
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from ui.widgets.ocr_performance_card import OcrPerformanceCard


@pytest.mark.parametrize('paint_module', ['toggle_switch'])
def test_paint_keeps_owning_window_alive_during_collection(paint_module):
    # A native crash must fail this test without terminating the test runner.
    script = textwrap.dedent('''
        import gc
        import importlib
        from PyQt5 import sip
        from PyQt5.QtWidgets import QApplication
        from ui.widgets.ocr_performance_card import OcrPerformanceCard

        app = QApplication([])
        gc.disable()
        module = importlib.import_module('ui.widgets.' + MODULE)
        original = module.palette_for
        painted = []

        def collect_during_paint(widget):
            gc.collect()
            assert not sip.isdeleted(widget), 'Owner collected during painting'
            painted.append(True)
            return original(widget)

        module.palette_for = collect_during_paint
        card = OcrPerformanceCard()
        card.show()
        del card
        app.processEvents()
        assert painted, 'Paint callback did not run'
    ''').replace('MODULE', repr(paint_module))
    result = subprocess.run(
        [sys.executable, '-c', script], capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ocr_performance_card_initialization(qtbot):
    card = OcrPerformanceCard(performance_mode="high", auto_threads=True, threads=4)
    qtbot.addWidget(card)

    assert card.performance_mode == "high"
    assert card.auto_threads is True
    assert card.threads == 4

    # High card is selected, Eco card is not
    assert card.high_button.isChecked() is True
    assert card.eco_button.isChecked() is False

    # Checkbox is checked, custom threads container is hidden, SpinBox is disabled
    assert card.auto_checkbox.isChecked() is True
    assert card.custom_threads_container.isVisible() is False
    assert card.threads_spin.isEnabled() is False


def test_ocr_performance_card_mode_click(qtbot):
    card = OcrPerformanceCard(performance_mode="high", auto_threads=True, threads=4)
    qtbot.addWidget(card)

    emitted_modes = []
    card.mode_changed.connect(emitted_modes.append)

    # Click Eco card
    qtbot.mouseClick(card.eco_button, Qt.LeftButton)
    assert emitted_modes == ["eco"]
    assert card.performance_mode == "eco"
    assert card.high_button.isChecked() is False
    assert card.eco_button.isChecked() is True

    # Click High card
    qtbot.mouseClick(card.high_button, Qt.LeftButton)
    assert emitted_modes == ["eco", "high"]
    assert card.performance_mode == "high"
    assert card.high_button.isChecked() is True
    assert card.eco_button.isChecked() is False


def test_ocr_performance_card_auto_threads_toggle(qtbot):
    card = OcrPerformanceCard(performance_mode="high", auto_threads=True, threads=4)
    qtbot.addWidget(card)
    card.show()

    auto_signals = []
    card.auto_threads_changed.connect(auto_signals.append)

    # Uncheck auto -> opens custom threads
    card.auto_checkbox.setChecked(False)
    assert auto_signals == [False]
    assert card.auto_threads is False
    assert card.threads_spin.isEnabled() is True
    assert not card.custom_threads_container.isHidden()
    assert card.threads == 4  # Preserves thread value

    # Re-check auto
    card.auto_checkbox.setChecked(True)
    assert auto_signals == [False, True]
    assert card.auto_threads is True
    assert card.threads_spin.isEnabled() is False
    assert card.threads == 4  # Still preserved


def test_ocr_performance_card_threads_spin(qtbot):
    card = OcrPerformanceCard(performance_mode="high", auto_threads=False, threads=4)
    qtbot.addWidget(card)

    thread_signals = []
    card.threads_changed.connect(thread_signals.append)

    card.threads_spin.setValue(6)
    assert thread_signals == [6]
    assert card.threads == 6

