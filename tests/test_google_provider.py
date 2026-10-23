from pathlib import Path
import pytest
from core import config


@pytest.mark.parametrize('value', [None, 'invalid', 'Google Translate'])
def test_missing_or_invalid_provider_defaults_google_without_writes(value):
    if value is not None: config.save_config('current_provider', value)
    before = Path(config.CONFIG_PATH).read_bytes() if Path(config.CONFIG_PATH).exists() else None
    assert config.load_active_provider() == 'Google Translate'
    provider = config.load_provider_settings()
    assert (provider.model_id, provider.api_key, provider.base_url) == ('', '', None)
    assert not config.get_provider_capabilities().requires_api_key
    assert not Path(config.ENV_PATH).exists()
    after = Path(config.CONFIG_PATH).read_bytes() if Path(config.CONFIG_PATH).exists() else None
    assert before == after


@pytest.mark.parametrize('provider', ['Google Gemini','OpenAI','DeepSeek','Custom API'])
def test_every_saved_valid_provider_is_preserved(provider):
    config.save_active_provider(provider)
    assert config.load_active_provider() == provider
    assert config.get_provider_capabilities(provider).requires_api_key


def test_google_key_and_model_access_do_not_touch_env_or_ai_models():
    config.save_provider_api_key('OpenAI','fake-saved-key')
    config.save_provider_model_id('OpenAI','saved-model')
    before = Path(config.ENV_PATH).read_bytes(), Path(config.CONFIG_PATH).read_bytes()
    config.save_provider_api_key('Google Translate','ignored')
    config.save_provider_model_id('Google Translate','ignored')
    assert config.load_provider_api_key('Google Translate') == ''
    assert config.load_provider_model_id('Google Translate') == ''
    assert before == (Path(config.ENV_PATH).read_bytes(), Path(config.CONFIG_PATH).read_bytes())
