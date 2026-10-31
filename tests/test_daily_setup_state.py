from pathlib import Path
from unittest.mock import Mock
import pytest

from core import config
from core.blocks.models import Rect
from core.capture.models import CaptureProfile
from core.capture.profile import parse_capture_profile


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
from ui.settings_coordinator import SettingsCoordinator


def test_fresh_defaults_require_region_selection(tmp_path, monkeypatch):
    cfg_path = tmp_path / "fresh_config.json"
    legacy_path = tmp_path / "non_existent_legacy.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    
    config.initialize_user_storage(legacy_config=legacy_path)
    
    assert config.load_capture_setup_complete() is False
    assert config.load_region() == config.DEFAULT_REGION


def test_legacy_explicit_default_rectangle_is_preserved(tmp_path, monkeypatch):
    cfg_path = tmp_path / "legacy_config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    
    # 1. Legacy config with explicit region matching DEFAULT_REGION without marker
    legacy_raw = {"region": {"top": 0, "left": 0, "width": 800, "height": 600}}
    import json
    cfg_path.write_text(json.dumps(legacy_raw), encoding="utf-8")
    
    assert config.load_capture_setup_complete() is True
    
    # 2. Fresh config with marker False must not be re-inferred to True
    normalized = config.normalize_config({
        "region": {"top": 0, "left": 0, "width": 800, "height": 600},
        "capture_setup_complete": False,
    })
    assert normalized["capture_setup_complete"] is False


def test_selecting_source_does_not_finish_setup(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    
    # Fresh setup
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")
    assert config.load_capture_setup_complete() is False
    
    profile = make_profile()
    
    # Selecting source does not pass setup_complete, marker stays False
    config.save_capture_profile(profile)
    assert config.load_capture_setup_complete() is False
    
    # Explicit user region commit marks setup complete
    config.save_capture_profile(profile, setup_complete=True)
    assert config.load_capture_setup_complete() is True


def test_region_commit_is_atomic_on_save_failure(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")
    assert config.load_capture_setup_complete() is False
    
    original_bytes = cfg_path.read_bytes()
    
    def refuse_replace(*args, **kwargs):
        raise OSError("disk write error")
        
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    
    profile = make_profile()
    
    with pytest.raises(config.ConfigError):
        config.save_capture_profile(profile, setup_complete=True)
        
    assert cfg_path.read_bytes() == original_bytes
    assert config.load_capture_setup_complete() is False


def test_coordinator_apply_region_and_profile_marks_setup_complete(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    
    config.initialize_user_storage(legacy_config=tmp_path / "none.json")
    assert config.load_capture_setup_complete() is False
    
    coordinator = SettingsCoordinator(config.State())
    coordinator.apply_region_selection({"top": 10, "left": 20, "width": 300, "height": 400})
    assert config.load_capture_setup_complete() is True
    
    # Reset to false
    config.save_config("capture_setup_complete", False)
    assert config.load_capture_setup_complete() is False
    
    worker = Mock()
    worker.capture_context = Mock(source_kind='desktop')
    coordinator.worker = worker
    profile = make_profile()
    coordinator.apply_capture_profile(profile)
    assert config.load_capture_setup_complete() is True

