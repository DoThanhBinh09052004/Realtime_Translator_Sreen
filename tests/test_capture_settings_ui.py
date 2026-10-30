from dataclasses import replace
from pathlib import Path
from core import config
from core.capture.models import CaptureRegion, NormalizedRect
from test_capture_app_integration import capture_values


def test_numeric_editor_is_draft_until_apply(qtbot, capture_geometry):
    from ui.capture_regions_dialog import CaptureRegionsDialog
    profile, context = capture_values(capture_geometry)
    d = CaptureRegionsDialog(profile, None, context); qtbot.addWidget(d)
    selected = []; d.profile_selected.connect(selected.append)
    d.table.item(0, 3).setText('10')
    d.table.item(0, 5).setText('80')
    assert not selected and not Path(config.CONFIG_PATH).exists()
    d.apply_btn.click()
    assert selected[0].regions[0].rect == NormalizedRect(.1, 0, .8, 1)


def test_editor_rejects_overlap_disabled_and_stale_size(qtbot, capture_geometry):
    from ui.capture_regions_dialog import CaptureRegionsDialog
    from uuid import uuid4
    profile, context = capture_values(capture_geometry)
    d = CaptureRegionsDialog(profile, None, context); qtbot.addWidget(d)
    d.add_region()
    assert not d.apply_btn.isEnabled() and d.error_label.text()
    d.remove_row(1)
    d.table.item(0, 1).setCheckState(0)
    assert not d.apply_btn.isEnabled()
    d.table.item(0, 1).setCheckState(2)
    assert d.apply_btn.isEnabled()
    d.update_context(replace(context, binding_epoch=2, geometry=replace(capture_geometry, image_size_px=(900, 600))))
    assert not d.apply_btn.isEnabled() and 'ảnh' in d.error_label.text().lower()


def test_profile_save_failure_does_not_reconfigure_worker(qtbot, monkeypatch, capture_geometry):
    from ui.settings_coordinator import SettingsCoordinator
    import ui.settings_coordinator as module
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry)
    w = Mock(); w.capture_context = context
    c = SettingsCoordinator(config.State(), w)
    monkeypatch.setattr(module, 'save_capture_profile', lambda p: (_ for _ in ()).throw(config.ConfigError('disk full')), raising=False)
    errors = []; c.save_failed.connect(errors.append)
    assert not c.apply_capture_profile(profile)
    w.configure_capture.assert_not_called()
    assert errors


def test_source_picker_keeps_window_identity_and_profile(qtbot, capture_geometry):
    from ui.capture_settings import CaptureSettings
    from types import SimpleNamespace
    from core.capture.models import WindowIdentity
    profile, context = capture_values(capture_geometry, 'window')
    identity = WindowIdentity(123, 45, 67)
    panel = CaptureSettings(profile, screens=lambda: (), windows=lambda: (SimpleNamespace(identity=identity, title='Same title', process_name='game.exe', available=True),))
    qtbot.addWidget(panel); chosen = []; panel.source_selected.connect(lambda *args: chosen.append(args))
    panel.source_combo.setCurrentIndex(0); panel.choose_btn.click()
    assert chosen[0][0].regions == profile.regions and chosen[0][1] == identity


def test_window_profile_without_runtime_identity_cannot_start(ui_window, capture_geometry):
    profile, context = capture_values(capture_geometry, 'window')
    ui_window.set_capture_profile_state(profile, bound=False)
    ui_window.start_ocr()
    ui_window.worker.start_worker.assert_not_called()
    assert not ui_window.capture_run_requested

def test_invalid_profile_recovery_is_explicit_and_preserves_other_settings(tmp_path):
    import json
    from pathlib import Path
    path = Path(config.CONFIG_PATH)
    raw = {'capture_profile': {'version': 999}, 'font_size': 31, 'region': {'left': 10, 'top': 20, 'width': 300, 'height': 100}}
    path.write_text(json.dumps(raw), encoding='utf8')
    before = path.read_bytes()
    import pytest
    with pytest.raises(config.ConfigError): config.load_config()
    assert path.read_bytes() == before
    config.recover_legacy_capture_profile()
    data = config.load_config()
    assert 'capture_profile' not in data and data['font_size'] == 31 and data['region'] == raw['region']
