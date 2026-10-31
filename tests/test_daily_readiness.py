import json
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from core import config
from core.capture.profile import parse_capture_profile
from ui.controller_state import DailyReadiness, DailyRunState
from ui.daily_control import DailyControlCoordinator
from ui.settings_coordinator import SettingsCoordinator


def make_profile():
    return parse_capture_profile({
        'version': 1,
        'source_kind': 'desktop',
        'monitor_name': 'left',
        'window_hint': None,
        'regions': [{'id': '11111111-1111-4111-8111-111111111111', 'name': 'Subtitles',
                     'rect': {'x': .1, 'y': .2, 'width': .4, 'height': .3}, 'enabled': True}],
        'exclusions': [],
    })


def test_readiness_priority(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")

    # Mock dependencies
    state = config.State()
    worker = Mock()
    worker.is_running.return_value = False
    worker.isRunning.return_value = False
    worker.is_drained = True
    worker.restart_pending = False

    controller = Mock()
    controller.capture_run_requested = False
    controller._capture_profile = None
    controller._capture_bound = False

    coordinator = SettingsCoordinator(state)
    daily = DailyControlCoordinator(coordinator, worker, controller)

    # 1. Missing binding / source -> action select_source
    r = daily.readiness()
    assert r.ready is False
    assert r.action == "select_source"

    # Now bind source, but region setup not complete
    binding = Mock()
    binding.profile = make_profile()
    binding.is_bound = True
    binding.is_waiting = False
    lifecycle = Mock()
    lifecycle.is_active = False

    daily.attach_capture(binding, lifecycle)

    # 2. Missing region setup -> action select_regions
    r = daily.readiness()
    assert r.ready is False
    assert r.action == "select_regions"

    # Mark capture setup complete, but no regions enabled
    config.save_config("capture_setup_complete", True)
    disabled_profile = Mock(regions=(Mock(enabled=False),))
    binding.profile = disabled_profile
    r = daily.readiness()
    assert r.ready is False
    assert r.action == "select_regions"

    # Restore enabled profile, but language pack not ready
    binding.profile = make_profile()
    monkeypatch.setattr(coordinator, "source_ready", lambda: False)
    r = daily.readiness()
    assert r.ready is False
    assert r.action == "manage_packs"

    # Language pack ready, but provider (e.g. Gemini) missing key
    monkeypatch.setattr(coordinator, "source_ready", lambda: True)
    config.save_active_provider("Google Gemini")
    monkeypatch.setattr(config, "load_provider_api_key", lambda p: "")
    r = daily.readiness()
    assert r.ready is False
    assert r.action == "configure_provider"

    # Provider is Google Translate (needs no key) -> fully ready!
    config.save_active_provider("Google Translate")
    r = daily.readiness()
    assert r.ready is True
    assert r.action is None


def test_stop_is_available_while_google_paused(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")

    state = config.State()
    worker = Mock()
    worker.is_running.return_value = True
    worker.is_drained = False
    worker.restart_pending = False

    controller = Mock()
    controller.capture_run_requested = True

    coordinator = SettingsCoordinator(state)
    daily = DailyControlCoordinator(coordinator, worker, controller)

    run = daily.run_state()
    assert run.phase == "running"
    assert run.can_toggle is True


def test_stopping_disables_start_until_both_threads_drained(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")

    state = config.State()
    worker = Mock()
    worker.is_running.return_value = False
    worker.isRunning.return_value = False
    worker.is_drained = False  # Draining in progress!

    controller = Mock()
    controller.capture_run_requested = False  # Stop was clicked

    coordinator = SettingsCoordinator(state)
    daily = DailyControlCoordinator(coordinator, worker, controller)

    run = daily.run_state()
    assert run.phase == "stopping"
    assert run.can_toggle is False


def test_missing_key_is_not_probed_over_network(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")

    state = config.State()
    worker = Mock()
    worker.is_running.return_value = False
    worker.isRunning.return_value = False
    worker.is_drained = True

    controller = Mock()
    controller.capture_run_requested = False

    coordinator = SettingsCoordinator(state)
    daily = DailyControlCoordinator(coordinator, worker, controller)

    binding = Mock()
    binding.profile = make_profile()
    binding.is_bound = True
    lifecycle = Mock()
    daily.attach_capture(binding, lifecycle)
    config.save_config("capture_setup_complete", True)

    config.save_active_provider("OpenAI")
    monkeypatch.setattr(config, "load_provider_api_key", lambda p: "")

    # Socket or network probe should not be called
    with patch("socket.socket") as mock_sock:
        r = daily.readiness()
        assert r.ready is False
        assert r.action == "configure_provider"
        mock_sock.assert_not_called()


def test_failed_save_renders_previous_settings(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")

    state = config.State()
    coordinator = SettingsCoordinator(state)
    initial_snapshot = coordinator.snapshot()

    def refuse_save(*args, **kwargs):
        raise config.ConfigError("disk full")

    monkeypatch.setattr(config, "save_config_values", refuse_save)
    success = coordinator.set_interval(1000)
    assert success is False
    assert coordinator.snapshot().ocr.interval_ms == initial_snapshot.ocr.interval_ms
