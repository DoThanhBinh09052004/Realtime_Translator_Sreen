from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from core import config


def test_custom_api_persists_normalized_endpoint_and_builds_runtime_settings():
    config.save_custom_api_base_url("  https://llm.example.test/v1/  ")
    config.save_provider_api_key("Custom API", "fake-custom-key")
    config.save_provider_model_id("Custom API", "vendor/model")

    settings = config.load_provider_settings("Custom API")

    assert settings.name == "Custom API"
    assert settings.base_url == "https://llm.example.test/v1"
    assert settings.api_key == "fake-custom-key"
    assert settings.model_id == "vendor/model"


def test_custom_api_rejects_non_http_endpoint():
    try:
        config.save_custom_api_base_url("file:///tmp/openai")
    except config.ConfigError as exc:
        assert 'HTTPS' in str(exc) and 'loopback' in str(exc)
    else:
        raise AssertionError("An unsafe Custom API endpoint was accepted")


def test_custom_api_translation_uses_saved_endpoint(monkeypatch):
    from core.contracts import RuntimeSettings
    from engines import translator
    from engines.translator import TranslationService

    assert "Custom API" in config.get_available_providers()
    clients = []

    def factory(**kwargs):
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Xin chào"))], usage=None,
            )))),
            close=Mock(), options=kwargs,
        )
        clients.append(client)
        return client

    monkeypatch.setattr(translator, "OpenAI", factory)
    provider = replace(
        config.load_provider_settings("Custom API"),
        api_key="fake-custom-key", model_id="vendor/model",
        base_url="https://llm.example.test/v1",
    )

    result = TranslationService().translate(
        "Hello", RuntimeSettings("English", "Vietnamese", provider, 500),
    )

    assert result.text == "Xin chào"
    assert clients[0].options["base_url"] == "https://llm.example.test/v1"


def test_custom_api_does_not_fall_back_to_openai_when_endpoint_is_missing(monkeypatch):
    from core.contracts import RuntimeSettings
    from engines import translator
    from engines.translator import TranslationService

    factory = Mock()
    monkeypatch.setattr(translator, "OpenAI", factory)
    provider = replace(
        config.load_provider_settings("Custom API"),
        api_key="fake-custom-key", model_id="vendor/model", base_url="",
    )

    result = TranslationService().translate(
        "Hello", RuntimeSettings("English", "Vietnamese", provider, 500),
    )

    assert result.error.code == "invalid_endpoint"
    factory.assert_not_called()


def test_custom_api_base_url_is_editable_only_for_custom_provider(qtbot):
    from ui.controller_state import AiPageState
    from ui.pages.ai_settings_page import AiSettingsPage

    custom = AiPageState(
        "Custom API", "vendor/model", ("vendor/model",), "fake-key", "sk-...",
        "https://llm.example.test/v1",
        supports_base_url=True,
    )
    page = AiSettingsPage(custom, ("OpenAI", "Custom API"))
    qtbot.addWidget(page)

    assert page.base_url_container.isVisibleTo(page)
    assert page.base_url_input.text() == "https://llm.example.test/v1"

    emitted = []
    page.base_url_changed.connect(emitted.append)
    page.base_url_input.setText("https://other.example/v1")
    page.base_url_input.editingFinished.emit()
    assert emitted == ["https://other.example/v1"]

    page.render(replace(custom, provider="OpenAI", base_url="", supports_base_url=False), changed_field="provider")
    assert not page.base_url_container.isVisibleTo(page)
