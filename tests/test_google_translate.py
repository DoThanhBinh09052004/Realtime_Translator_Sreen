"""Cross-layer Google smoke using a fake transport, never a live service."""
import httpx
from core import config
from engines.google_translate import GoogleTranslateClient
from engines.translator import TranslationService


def test_google_default_to_clients5_and_shared_cache():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=['Xin chào. ', 'Thế giới!'])
    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = GoogleTranslateClient(client_factory=lambda: client)
    service = TranslationService(google_factory=lambda: adapter)
    settings = config.load_runtime_settings(config.State(), 500)
    assert settings.provider.name == 'Google Translate' and settings.provider.api_key == ''
    try:
        assert service.translate('Hello. World!', settings).text == 'Xin chào. Thế giới!'
        assert service.translate('Hello. World!', settings).from_cache
        assert len(calls) == 1 and calls[0].method == 'GET'
        assert calls[0].url.host == 'clients5.google.com'
        assert dict(calls[0].url.params) == dict(client='dict-chrome-ex', sl='en', tl='vi', q='Hello. World!')
    finally:
        service.close()
    assert client.is_closed
