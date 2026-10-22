from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def settings():
    from core.contracts import ProviderSettings, RuntimeSettings
    return RuntimeSettings("English", "Vietnamese",
                           ProviderSettings("OpenAI", "m1", "fake-key", None), 500)


@pytest.fixture
def transport(monkeypatch):
    from engines import translator
    create = Mock(side_effect=lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=f"result-{kw['model']}"))],
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=3),
    ))
    clients = []

    def factory(**kwargs):
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                 close=Mock(), options=kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(translator, "OpenAI", factory)
    return SimpleNamespace(create=create, clients=clients)


def test_switching_model_misses_cache(transport):
    from engines.translator import TranslationService
    service = TranslationService()
    first = settings()
    second = replace(first, provider=replace(first.provider, model_id="m2"))
    assert service.translate("Hello", first).text == "result-m1"
    assert service.translate("Hello", second).text == "result-m2"
    assert [call.kwargs["model"] for call in transport.create.call_args_list] == ["m1", "m2"]
    assert service.translate("Hello", first).text == "result-m1"
    assert transport.create.call_count == 2
    service.close()


@pytest.mark.parametrize("field,value", [("source_lang", "Japanese"), ("target_lang", "English")])
def test_language_changes_miss_cache(transport, field, value):
    from engines.translator import TranslationService
    service = TranslationService()
    original = settings()
    service.translate("Hello", original)
    service.translate("Hello", replace(original, **{field: value}))
    assert transport.create.call_count == 2
    service.close()


@pytest.mark.parametrize("change", [
    {"name": "Google Gemini", "base_url": "https://provider.invalid/v1"},
    {"api_key": "fake-new-key"}, {"base_url": "https://other.invalid/v1"},
])
def test_provider_credentials_and_endpoint_invalidate_session(transport, change):
    from engines.translator import TranslationService
    service = TranslationService()
    original = settings()
    changed = replace(original, provider=replace(original.provider, **change))
    service.translate("Hello", original)
    service.translate("Hello", changed)
    assert transport.create.call_count == 2
    assert len(transport.clients) == 2
    transport.clients[0].close.assert_called_once()
    service.close()
    service.close()
    transport.clients[1].close.assert_called_once()


def test_cache_is_fifo_bounded_and_does_not_include_key(transport):
    from engines.translator import TranslationService
    service = TranslationService()
    snapshot = settings()
    for index in range(300):
        service.translate(str(index), snapshot)
    service.translate("0", snapshot)  # a hit must not change FIFO ordering
    service.translate("300", snapshot)
    service.translate("1", snapshot)
    assert transport.create.call_count == 301
    assert len(service._cache) == 300
    assert snapshot.provider.api_key not in repr(service._cache)
    service.translate("0", snapshot)
    assert transport.create.call_count == 302
    service.close()


def test_services_do_not_share_clients_or_cache(transport):
    from engines.translator import TranslationService
    first, second = TranslationService(), TranslationService()
    first.translate("Hello", settings())
    second.translate("Hello", settings())
    assert len(transport.clients) == transport.create.call_count == 2
    first.close()
    transport.clients[1].close.assert_not_called()
    second.close()


def test_sdk_retries_disabled_and_timeout_bounded(transport):
    from engines.translator import TranslationService
    service = TranslationService()
    result = service.translate("Hello", settings())
    assert transport.clients[0].options["max_retries"] == 0
    assert transport.clients[0].options["timeout"] == 8.0
    assert transport.create.call_args.kwargs["timeout"] == 8.0
    assert (result.input_tokens, result.output_tokens) == (4, 3)
    service.close()


def test_gemini_allows_ten_seconds_for_each_request(transport):
    from engines.translator import TranslationService
    snapshot = settings()
    snapshot = replace(snapshot, provider=replace(
        snapshot.provider,
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ))
    service = TranslationService()
    service.translate("Hello", snapshot)
    assert transport.clients[0].options["timeout"] == 10.0
    assert transport.create.call_args.kwargs["timeout"] == 10.0
    service.close()
