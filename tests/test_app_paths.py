import json
from pathlib import Path


def test_paths_use_fixed_user_directories_without_creating_them(tmp_path, monkeypatch):
    from core import paths
    monkeypatch.setattr(paths.QStandardPaths, 'writableLocation', lambda kind: str(tmp_path / str(kind)))
    result = paths.get_app_paths()
    for directory in (result.config_dir, result.cache_dir, result.logs_dir, result.models_dir):
        assert directory.is_relative_to(tmp_path)
        assert 'TranslateHUD' in directory.parts
        assert not directory.exists()


def test_migrate_settings_once_without_touching_legacy(tmp_path, monkeypatch):
    from core import config
    legacy = tmp_path / 'legacy.json'
    original = '{"font_size": 29, "api_key": "fake-key", "provider_models": {"OpenAI": "m1"}}'
    legacy.write_text(original)
    target = tmp_path / 'user' / 'config.json'
    monkeypatch.setattr(config, 'CONFIG_PATH', str(target))
    config.initialize_user_storage(legacy_config=legacy)
    assert config.load_config()['font_size'] == 29
    saved = json.loads(target.read_text())
    assert saved['schema_version'] == 1
    assert 'fake-key' not in target.read_text()
    assert legacy.read_text() == original
    legacy.write_text('{"font_size": 15}')
    config.initialize_user_storage(legacy_config=legacy)
    assert config.load_config()['font_size'] == 29


def test_language_pack_root_is_durable_and_does_not_touch_legacy_cache(tmp_path,monkeypatch):
    from core import paths
    monkeypatch.setattr(paths.QStandardPaths,'writableLocation',lambda kind:str(tmp_path/str(kind)))
    result=paths.get_app_paths()
    assert paths.get_language_pack_root()==result.config_dir/'models'
    assert paths.get_language_pack_root()!=result.models_dir
    assert not paths.get_language_pack_root().exists()
