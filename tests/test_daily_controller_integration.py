from uuid import uuid4
from unittest.mock import Mock
import pytest
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtTest import QSignalSpy

from core import config
from core.config import save_config_values, load_config, load_active_provider, save_capture_profile, save_active_provider
from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect
from ui.controller import ControllerWindow
from ui.game_controls import GameControls
from ui.controller_state import (
    DailyReadiness,
    DailyRunState,
    PresentedPair,
    PresentedTranslation,
)


@pytest.fixture
def bound_daily_window(qtbot, capture_geometry):
    """Use production source binding, not the standalone-controller fallback."""
    from types import SimpleNamespace
    from test_capture_binding import Screens, Provider
    from ui.capture_binding import CaptureApplicationBinding

    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    worker.isRunning.return_value = False
    worker.is_drained = True
    worker.restart_pending = False
    worker.capture_context = None
    worker.configure_capture.side_effect = lambda profile, context: setattr(worker, 'capture_context', context)
    worker.start_worker.side_effect = lambda **kwargs: setattr(worker.is_running, 'return_value', True)
    worker.stop_worker.side_effect = lambda **kwargs: setattr(worker.is_running, 'return_value', False)
    window = ControllerWindow(worker, config.State(), Mock(), Mock())
    qtbot.addWidget(window)
    region = CaptureRegion(str(uuid4()), 'Vùng 1', NormalizedRect(.1, .1, .5, .5), True)
    profile = CaptureProfile(1, 'desktop', capture_geometry.screen.name, None, (region,), ())
    save_capture_profile(profile, setup_complete=True)
    save_active_provider('Google Translate')
    lifecycle = SimpleNamespace(is_active=False, preview_is_drained=True,
                                cancel_dashboard_preview=lambda: None,
                                update_capture_context=lambda context: None,
                                on_capture_terminal=lambda status: None)
    binding = CaptureApplicationBinding(window, worker, Mock(), Screens([capture_geometry.screen]),
                                        lifecycle, window_provider=Provider())
    window.daily_coordinator.attach_capture(binding, lifecycle)
    binding.initialize(profile)
    yield window, worker, binding
    binding.stop()


@pytest.mark.parametrize('entry', ['direct', 'button', 'game_controls'])
def test_start_with_production_capture_binding_reaches_worker(bound_daily_window, entry):
    window, worker, binding = bound_daily_window
    assert binding.is_bound
    assert window.console_page.primary_btn.isEnabled()
    if entry == 'direct':
        window.start_ocr()
    elif entry == 'button':
        window.console_page.primary_btn.click()
    else:
        GameControls(window, worker).toggle_translation()
    worker.start_worker.assert_called_once_with()
    assert window.capture_run_requested is True


def test_restart_revalidates_source_after_stop(bound_daily_window):
    window, worker, binding = bound_daily_window
    window.start_ocr()
    window.stop_ocr()
    worker.start_worker.reset_mock()
    binding.screens.mappings = []
    window.console_page.primary_btn.click()
    worker.start_worker.assert_not_called()
    assert binding.is_bound is False
    assert window.capture_run_requested is False


def test_daily_button_can_restart_after_stop_with_capture_binding(bound_daily_window):
    window, worker, binding = bound_daily_window
    # Isolate the stop/restart path from first-start validation.
    window.capture_run_requested = True
    worker.is_running.return_value = True
    window.daily_state_changed.emit()
    window.console_page.primary_btn.click()
    assert window.capture_run_requested is False
    assert window.console_page.primary_btn.isEnabled()
    window.console_page.primary_btn.click()
    worker.start_worker.assert_called_once_with()


def _setup_bound_ready_state(window, tmp_path):
    region_id = str(uuid4())
    region = CaptureRegion(region_id, "Vùng 1", NormalizedRect(0.1, 0.1, 0.5, 0.5), enabled=True)
    profile = CaptureProfile(1, "desktop", "Primary", None, (region,), ())
    save_capture_profile(profile, setup_complete=True)
    window.set_capture_profile_state(profile, bound=True)
    window._capture_bound = True
    save_config_values({"source_lang": "English", "target_lang": "Vietnamese", "current_provider": "Google Translate"})


def test_language_edit_saves_once_and_syncs_advanced_view(qtbot, tmp_path, monkeypatch):
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    replace_mock = Mock(wraps=config.os.replace)
    monkeypatch.setattr(config.os, "replace", replace_mock)

    window.console_page.source_changed.emit("Japanese")

    assert config.load_config()["source_lang"] == "Japanese"
    assert replace_mock.call_count == 1

    # Verify synchronization with advanced ocr view
    assert window.ocr_page.src_combo.currentText() == "Japanese"

    # Verify daily view combo is in sync without second save
    daily_src = window.console_page.src_combo.itemData(window.console_page.src_combo.currentIndex())
    assert daily_src == "Japanese"
    assert replace_mock.call_count == 1


def test_daily_select_regions_uses_existing_lifecycle(qtbot):
    on_select_region = Mock()
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), on_select_region, Mock(), overlay=None)
    qtbot.addWidget(window)

    window.console_page.select_region_btn.click()
    on_select_region.assert_called_once()


def test_button_tray_hotkey_share_guards(qtbot, tmp_path):
    # Fresh state without complete region setup
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    game_controls = GameControls(window, worker)

    # 1. Primary button click
    window.console_page.primary_btn.click()
    worker.start_worker.assert_not_called()

    # 2. Tray action toggle
    game_controls.toggle_translation()
    worker.start_worker.assert_not_called()

    # 3. Direct toggle_daily_translation
    window.toggle_daily_translation()
    worker.start_worker.assert_not_called()


def test_stop_then_start_does_not_resurrect_old_presentation(qtbot, tmp_path):
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = True
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)
    _setup_bound_ready_state(window, tmp_path)

    # Simulate presented translation
    pair = PresentedPair("Where are you going?", "Bạn đang đi đâu?")
    presentation = PresentedTranslation(revision=1, mode="subtitle", sequence=1, pairs=(pair,))
    window.console_page.render_presented(presentation)
    assert window.console_page.output_widget.source_edit.toPlainText() == "Where are you going?"

    # Stop translation
    window.stop_ocr()
    assert window.console_page.output_widget.source_edit.toPlainText() == ""
    assert not window.console_page.output_widget.placeholder_lbl.isHidden()

    # Worker finishes and restarts
    worker.is_running.return_value = False
    window.start_ocr()
    assert window.console_page.output_widget.source_edit.toPlainText() == ""


def test_waiting_source_can_be_stopped(qtbot, tmp_path):
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    worker.is_drained = True
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    # Simulate waiting_source state: run requested but not bound
    window.capture_run_requested = True
    window._capture_bound = False
    window.daily_state_changed.emit()

    assert window.daily_coordinator.run_state().phase == "waiting_source"

    # Stop through toggle_daily_translation
    window.toggle_daily_translation()

    assert not window.capture_run_requested
    assert window.daily_coordinator.run_state().phase == "stopped"
    worker.stop_worker.assert_called()


def test_missing_model_exposes_repair_action_without_start(qtbot, tmp_path):
    save_config_values({"current_provider": "Custom API", "model_id": "", "custom_api_base_url": "https://api.example.com/v1"})
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)
    _setup_bound_ready_state(window, tmp_path)
    # Re-save missing model since _setup_bound_ready_state sets provider
    save_config_values({"current_provider": "Custom API", "model_id": "", "custom_api_base_url": "https://api.example.com/v1"})

    window.daily_coordinator.refresh()
    readiness = window.daily_coordinator.readiness()
    assert not readiness.ready
    assert readiness.action == "configure_provider"

    # Attempt to start
    window.console_page.primary_btn.click()
    worker.start_worker.assert_not_called()

    # Repair action button
    assert not window.console_page.readiness_action_btn.isHidden()
    window.console_page.readiness_action_btn.click()

    # Should switch to AI page (page index 1)
    assert window.pages.currentIndex() == 1
    worker.start_worker.assert_not_called()


def test_startup_never_constructs_preview_or_calls_provider(qtbot, fake_translator):
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)
    game_controls = GameControls(window, worker)

    # Zero calls to fake_translator
    assert fake_translator.call_count == 0
    # No preview image loaded on startup
    assert window.console_page.snapshot_widget._image is None


def test_active_paid_provider_is_not_reset(qtbot, tmp_path):
    save_config_values({"current_provider": "OpenAI"})
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    assert load_active_provider() == "OpenAI"
    assert window.settings_coordinator.snapshot().ai.provider == "OpenAI"
    assert window.console_page.provider_combo.currentData() == 'OpenAI'
