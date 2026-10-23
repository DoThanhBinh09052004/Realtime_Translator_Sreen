"""Cross-layer Google smoke using a fake transport, never a live service."""
import httpx
from core import config
from engines.google_translate import GoogleTranslateClient
from engines.translator import TranslationService


def test_google_default_to_real_adapter_and_shared_cache():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[[["Xin chào. ", "Hello."], ["Thế giới!", "World!"]]])
    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = GoogleTranslateClient(client_factory=lambda: client)
    service = TranslationService(google_factory=lambda: adapter)
    settings = config.load_runtime_settings(config.State(), 500)
    assert settings.provider.name == 'Google Translate' and settings.provider.api_key == ''
    try:
        assert service.translate('Hello. World!', settings).text == 'Xin chào. Thế giới!'
        assert service.translate('Hello. World!', settings).from_cache
        assert len(calls) == 1 and calls[0].url.params['tl'] == 'vi'
    finally:
        service.close()
    assert client.is_closed
