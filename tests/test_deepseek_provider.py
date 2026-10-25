from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from core import config


def test_deepseek_provider_has_current_models_and_persists_its_own_key():
    assert "DeepSeek" in config.get_available_providers()
    assert config.PROVIDERS["DeepSeek"]["base_url"] == "https://api.deepseek.com"
    assert config.PROVIDERS["DeepSeek"]["default_model"] == "deepseek-flash"
    assert "deepseek-v4-pro" in config.PROVIDERS["DeepSeek"]["models"]

    config.save_active_provider("DeepSeek")
    config.save_provider_api_key("DeepSeek", "fake-deepseek-key")
    snapshot = config.load_provider_settings()
    assert snapshot.name == "DeepSeek"
    assert snapshot.model_id == "deepseek-flash"
    assert snapshot.api_key == "fake-deepseek-key"
    from pathlib import Path
    assert not Path(config.ENV_PATH).exists()
    assert config.provider_key_storage('DeepSeek') == 'saved'


def test_deepseek_uses_official_endpoint_and_selected_model(monkeypatch):
    from engines import translator
    from core.contracts import RuntimeSettings
    from engines.translator import TranslationService

    create = Mock(side_effect=lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=f"result-{kwargs['model']}"))]))
    clients = []

    def factory(**kwargs):
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            close=Mock(), options=kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(translator, "OpenAI", factory)
    snapshot = RuntimeSettings(
        "English", "Vietnamese",
        config.load_provider_settings("DeepSeek"), 500,
    )
    snapshot = replace(snapshot, provider=replace(
        snapshot.provider, api_key="fake-deepseek-key", model_id="deepseek-v4-pro"))
    service = TranslationService()
    result = service.translate("Hello", snapshot)

    assert result.text == "result-deepseek-v4-pro"
    assert clients[0].options["base_url"] == "https://api.deepseek.com"
    assert clients[0].options["api_key"] == "fake-deepseek-key"
    assert create.call_args.kwargs["model"] == "deepseek-v4-pro"
    service.close()


def test_deepseek_is_available_in_ai_settings(qtbot):
    from ui.controller_state import AiPageState
    from ui.pages.ai_settings_page import AiSettingsPage

    page = AiSettingsPage(
        AiPageState("OpenAI", "gpt-4o-mini", ("gpt-4o-mini",), "", "sk-..."),
        tuple(config.get_available_providers()),
    )
    qtbot.addWidget(page)
    assert page.provider_combo.findText("DeepSeek") >= 0


def test_deepseek_api_key_is_cleared_by_test_isolation():
    import os

    assert "DEEPSEEK_API_KEY" not in os.environ
