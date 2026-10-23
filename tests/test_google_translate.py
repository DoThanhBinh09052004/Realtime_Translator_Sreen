"""Cross-layer Google smoke using a fake transport, never a live service."""
import httpx
import json
from urllib.parse import parse_qs
from core import config
from engines.google_translate import GoogleTranslateClient
from engines.translator import TranslationService


def test_google_default_to_real_adapter_and_shared_cache(google_batch_response):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, text=google_batch_response('Xin chào. ', 'Thế giới!'))
    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = GoogleTranslateClient(client_factory=lambda: client)
    service = TranslationService(google_factory=lambda: adapter)
    settings = config.load_runtime_settings(config.State(), 500)
    assert settings.provider.name == 'Google Translate' and settings.provider.api_key == ''
    try:
        assert service.translate('Hello. World!', settings).text == 'Xin chào. Thế giới!'
        assert service.translate('Hello. World!', settings).from_cache
        assert len(calls) == 1 and calls[0].method == 'POST'
        rpc = json.loads(parse_qs(calls[0].content.decode())['f.req'][0])
        assert json.loads(rpc[0][0][1])[0] == ['Hello. World!', 'en', 'vi', True]
    finally:
        service.close()
    assert client.is_closed
