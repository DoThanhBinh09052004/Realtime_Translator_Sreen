from dataclasses import replace
from unittest.mock import Mock
import pytest
from core import config
from ui.settings_coordinator import SettingsCoordinator
from ui.pages.subtitle_settings_page import SubtitleSettingsPage


@pytest.mark.parametrize('value', [None, 'invalid', 1, [], {}])
def test_old_or_invalid_config_defaults_to_subtitle(value):
    config.save_config('overlay_mode', value)
    assert config.State().overlay_mode == 'subtitle'


def test_failed_mode_save_leaves_worker_and_visible_mode_unchanged(monkeypatch):
    state, worker, overlay = config.State(), Mock(), Mock()
    c = SettingsCoordinator(state, worker, overlay)
    before = c.snapshot()
    monkeypatch.setattr(config.os, 'replace', Mock(side_effect=OSError('disk full')))
    assert not c.set_overlay_mode('blocks')
    assert c.snapshot() == before
    worker.configure.assert_not_called()
    overlay.set_mode.assert_not_called()


def test_saved_mode_is_applied_after_persistence():
    state, worker, overlay = config.State(), Mock(), Mock()
    worker.configure.return_value = 7
    c = SettingsCoordinator(state, worker, overlay)
    assert c.set_overlay_mode('blocks')
    assert config.State().overlay_mode == 'blocks'
    assert worker.configure.call_args.args[0].overlay_mode == 'blocks'
    overlay.set_mode.assert_called_with('blocks', 7)


def test_mode_render_does_not_save_and_disables_position(qtbot):
    state = SettingsCoordinator(config.State()).snapshot().subtitle
    page = SubtitleSettingsPage(state)
    qtbot.addWidget(page)
    events = []
    page.mode_changed.connect(events.append)
    page.render(replace(state, overlay_mode='blocks'))
    assert events == []
    assert page.mode_combo.currentData() == 'blocks'
    assert not page.preset_combo.isEnabled() and not page.drag_toggle_btn.isEnabled()
    assert 'bản ghi hình' in page.capture_warning.text()
    page.render(state)
    assert page.preset_combo.isEnabled()
