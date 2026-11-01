from unittest.mock import Mock
import pytest
from PyQt5.QtGui import QCloseEvent

from core import config
from core.config import save_config_values
from ui.controller import ControllerWindow
from ui.game_controls import GameControls


def test_settings_returns_without_changing_run_intent(qtbot):
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    window.capture_run_requested = True

    # Navigate to advanced settings
    window.console_page.settings_btn.click()
    assert window.pages.currentIndex() == 1
    assert not window.sidebar.isHidden()

    # Return using back button
    window.back_btn.click()
    assert window.pages.currentIndex() == 0
    assert not window.sidebar.isHidden()
    assert window.capture_run_requested is True
    worker.start_worker.assert_not_called()
    worker.stop_worker.assert_not_called()


def test_customize_opens_subtitle_page(qtbot):
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    window.console_page.customize_btn.click()
    assert window.pages.currentIndex() == 3
    assert not window.sidebar.isHidden()


def test_advanced_api_key_save_and_delete_still_work(qtbot):
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    # Navigate to AI page
    window._switch_to_page(1)
    window.ai_page.provider_buttons["OpenAI"].click()
    provider = "OpenAI"

    # Save key
    window.ai_page.api_key_save_requested.emit("sk-test-advanced-key-999", True)
    assert config.load_provider_api_key(provider) == "sk-test-advanced-key-999"
    assert window.settings_coordinator.snapshot().ai.api_key == "sk-test-advanced-key-999"

    # Delete key
    window.ai_page.api_key_delete_requested.emit()
    assert config.load_provider_api_key(provider) == ""
    assert window.settings_coordinator.snapshot().ai.api_key == ""


def test_advanced_language_change_syncs_daily_without_second_save(qtbot, monkeypatch):
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    replace_mock = Mock(wraps=config.os.replace)
    monkeypatch.setattr(config.os, "replace", replace_mock)

    # Navigate to OCR page and change source language
    window._switch_to_page(2)
    window.ocr_page.src_combo.setCurrentText("Japanese")

    assert config.load_config()["source_lang"] == "Japanese"
    assert replace_mock.call_count == 1

    # Return to daily page
    window._switch_to_page(0)
    daily_src = window.console_page.src_combo.itemData(window.console_page.src_combo.currentIndex())
    assert daily_src == "Japanese"
    assert replace_mock.call_count == 1


def test_close_to_tray_and_explicit_quit_survive_new_shell(qtbot):
    worker = Mock()
    worker.interval.return_value = 500
    on_quit_cb = Mock()
    window = ControllerWindow(worker, config.State(), Mock(), on_quit_cb, overlay=None)
    qtbot.addWidget(window)

    fake_controls = Mock()
    fake_controls.tray_icon = Mock()
    window.set_game_controls(fake_controls)

    window.show()
    assert window.isVisible()

    # Close event hides window to tray
    close_event = QCloseEvent()
    window.closeEvent(close_event)
    assert not window.isVisible()
    on_quit_cb.assert_not_called()

    # Explicit quit from sidebar quit action
    window.sidebar.quit_requested.emit()
    on_quit_cb.assert_called_once()
