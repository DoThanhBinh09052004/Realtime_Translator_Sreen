import os
from pathlib import Path

import pytest

from core import config


def test_normal_load_never_reads_legacy_or_environment(monkeypatch):
    Path(config.ENV_PATH).write_text('OPENAI_API_KEY=legacy-secret\n')
    monkeypatch.setenv('OPENAI_API_KEY', 'environment-secret')
    assert config.load_provider_api_key('OpenAI') == ''


def test_development_environment_is_explicit_and_disabled_when_frozen(monkeypatch):
    import sys
    monkeypatch.setenv('OPENAI_API_KEY', 'environment-secret')
    monkeypatch.setenv('TRANSLATE_HUD_DEV_ENV', '1')
    assert config.load_provider_api_key('OpenAI') == 'environment-secret'
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    assert config.load_provider_api_key('OpenAI') == ''


def test_explicit_import_and_confirmed_cleanup_preserve_other_lines():
    path = Path(config.ENV_PATH)
    original = '# retained\nOPENAI_API_KEY=legacy-secret\nOTHER=keep\nMODEL_ID=m1\n'
    path.write_text(original)
    config.import_legacy_provider_key('OpenAI', persist=True)
    assert config.load_provider_api_key('OpenAI') == 'legacy-secret'
    assert path.read_text() == original
    config.remove_legacy_provider_key('OpenAI')
    assert path.read_text() == '# retained\nOTHER=keep\nMODEL_ID=m1\n'


def test_session_only_import_cannot_remove_unprotected_legacy():
    path = Path(config.ENV_PATH)
    original = 'OPENAI_API_KEY=legacy-secret\n'
    path.write_text(original)
    config.import_legacy_provider_key('OpenAI', persist=False)
    with pytest.raises(config.ConfigError):
        config.remove_legacy_provider_key('OpenAI')
    assert path.read_text() == original


def test_saving_key_never_writes_environment_or_plaintext():
    config.save_provider_api_key('OpenAI', 'fake-sensitive-key')
    assert config.load_provider_api_key('OpenAI') == 'fake-sensitive-key'
    assert 'OPENAI_API_KEY' not in os.environ
    assert not Path(config.ENV_PATH).exists()
