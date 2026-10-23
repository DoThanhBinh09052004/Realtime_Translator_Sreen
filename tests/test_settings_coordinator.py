from unittest.mock import Mock
import pytest
from core import config


CASES = [
    ('set_provider', ('OpenAI',), 'provider', True),
    ('set_model', ('fake-custom',), 'model', True),
    ('set_api_key', ('fake-new-key',), 'api_key', True),
    ('set_source', ('Japanese',), 'source', True),
    ('set_target', ('English',), 'target', True),
    ('set_interval', (800,), 'interval', True),
    ('set_subtitle_style', ({'font_size': 30, 'bg_color': '#123456'},), 'subtitle_style', False),
    ('set_overlay_preset', ('top_center',), 'preset', False),
    ('save_overlay_position', (-200, 40), 'overlay_position', False),
    ('apply_region_selection', ({'left': -10, 'top': 0, 'width': 200, 'height': 100},), 'region', False),
]


@pytest.fixture
def coordinator():
    from ui.settings_coordinator import SettingsCoordinator
    config.save_active_provider('Google Gemini')
    worker = Mock()
    worker.interval.return_value = 500
    overlay = Mock()
    overlay.is_drag_mode = False
    return SettingsCoordinator(config.State(), worker, overlay)


@pytest.mark.parametrize('method,args,field,runtime', CASES)
def test_commits_before_apply_and_emits_once(coordinator, method, args, field, runtime):
    events = []
    coordinator.settings_changed.connect(lambda snapshot, changed: events.append(changed))
    def configured(settings):
        saved = config.load_runtime_settings(config.State(), config.load_config()['interval_ms'])
        assert settings == saved
    coordinator.worker.configure.side_effect = configured
    coordinator.worker.set_region.side_effect = lambda region: pytest.fail('region before save') if region != config.load_region() else None
    coordinator.overlay.apply_style.side_effect = lambda **style: (
        None if style['font_size'] == config.load_config()['font_size'] else pytest.fail('style before save'))
    assert getattr(coordinator, method)(*args)
    assert events == [field]
    assert coordinator.worker.configure.call_count == int(runtime)
    assert 'fake-new-key' not in repr(coordinator.snapshot())
    if field == 'region':
        coordinator.worker.set_region.assert_called_once_with(args[0])
    if field == 'subtitle_style':
        coordinator.overlay.apply_style.assert_called_once()
    if field == 'preset':
        coordinator.overlay.apply_preset.assert_called_once_with('top_center')


@pytest.mark.parametrize('method,args,field,runtime', CASES)
def test_failure_rolls_back_before_safe_error_without_apply(coordinator, monkeypatch, method, args, field, runtime):
    coordinator.state.update(overlay_preset='custom', overlay_x=-100, overlay_y=40)
    before = coordinator.snapshot()
    events = []
    coordinator.settings_changed.connect(lambda snapshot, field: events.append((field, snapshot)))
    coordinator.save_failed.connect(lambda text: events.append(('error', text)))
    def denied(*args):
        raise OSError('fake-secret')
    monkeypatch.setattr(config.os, 'replace', denied)
    assert not getattr(coordinator, method)(*args)
    assert events[0] == ('rollback', before)
    assert events[1][0] == 'error' and 'fake-secret' not in events[1][1]
    assert coordinator.snapshot() == before
    coordinator.worker.configure.assert_not_called()
    coordinator.worker.set_region.assert_not_called()
    coordinator.overlay.apply_style.assert_not_called()
    if field == 'overlay_position':
        coordinator.overlay.move.assert_called_once_with(-100, 40)
    else:
        coordinator.overlay.move.assert_not_called()
        coordinator.overlay.apply_preset.assert_not_called()


def test_interval_init_drag_style_validation_and_programming_errors(coordinator):
    coordinator.initialize_worker_interval()
    coordinator.initialize_worker_interval()
    coordinator.worker.setInterval.assert_called_once_with(500)
    assert coordinator.toggle_overlay_drag()
    coordinator.overlay.set_drag_mode.assert_called_once_with(True)
    with pytest.raises(ValueError):
        coordinator.set_subtitle_style({'source': 'Japanese'})
    with pytest.raises(RuntimeError):
        coordinator._commit(lambda: (_ for _ in ()).throw(RuntimeError()), field='model')
    coordinator.set_overlay(None)
    assert not coordinator.toggle_overlay_drag()


def test_invalid_custom_api_url_reports_validation_error(coordinator):
    config.save_active_provider('Custom API')
    errors = []
    coordinator.save_failed.connect(errors.append)

    assert not coordinator.set_custom_base_url('ftp://llm.example.test/v1')
    assert errors == ['Base URL phải bắt đầu bằng http:// hoặc https://.']
