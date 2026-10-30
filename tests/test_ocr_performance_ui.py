import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from ui.widgets.ocr_performance_card import OcrPerformanceCard


def test_ocr_performance_card_initialization(qtbot):
    card = OcrPerformanceCard(performance_mode="high", auto_threads=True, threads=4)
    qtbot.addWidget(card)

    assert card.performance_mode == "high"
    assert card.auto_threads is True
    assert card.threads == 4

    # High card is selected, Eco card is not
    assert card.high_card.property("selected") is True
    assert card.eco_card.property("selected") is False
    assert card.high_card.radio_indicator._selected is True
    assert card.eco_card.radio_indicator._selected is False

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
    qtbot.mouseClick(card.eco_card, Qt.LeftButton)
    assert emitted_modes == ["eco"]
    assert card.performance_mode == "eco"
    assert card.high_card.property("selected") is False
    assert card.eco_card.property("selected") is True
    assert card.high_card.radio_indicator._selected is False
    assert card.eco_card.radio_indicator._selected is True

    # Click High card
    qtbot.mouseClick(card.high_card, Qt.LeftButton)
    assert emitted_modes == ["eco", "high"]
    assert card.performance_mode == "high"
    assert card.high_card.property("selected") is True
    assert card.eco_card.property("selected") is False
    assert card.high_card.radio_indicator._selected is True
    assert card.eco_card.radio_indicator._selected is False


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

