from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest

from core.contracts import ProviderSettings, RuntimeSettings
from core.retry import RetryState
from engines import translator


def settings(url='https://api.example.test/v1', key='fake-api-key'):
    return RuntimeSettings('English', 'Vietnamese', ProviderSettings('Custom API', 'test-model', key, url), 500)


def completion():
    return {'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 0, 'model': 'test-model',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'Xin chào'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}}


def install_real_sdk(monkeypatch, handler):
    from openai._client import OpenAI as RealOpenAI
    from engines.custom_api_http import build_custom_api_http_client
    monkeypatch.setattr(translator, 'OpenAI', RealOpenAI)
    transports = []
    class Transport(httpx.MockTransport):
        closes = 0
        def close(self):
            self.closes += 1
            super().close()
    def factory(url, *, timeout_s):
        transport = Transport(handler)
        transports.append(transport)
        return build_custom_api_http_client(url, timeout_s=timeout_s, transport=transport)
    monkeypatch.setattr(translator, 'build_custom_api_http_client', factory, raising=False)
    return transports


@pytest.mark.parametrize('url', ['http://remote.example.test/v1', 'http://192.168.1.20/v1',
                                 'https://fake-api-key@api.example.test/v1', None])
def test_direct_snapshot_cannot_bypass_policy(monkeypatch, url):
    factory = Mock()
    monkeypatch.setattr(translator, 'OpenAI', factory)
    logs = []
    service = translator.TranslationService(log_callback=logs.append)
    try:
        result = service.translate('fake-source', settings(url))
    finally:
        service.close()
    assert result.text == '' and result.error.code == 'invalid_endpoint'
    assert result.error.retryable is False
    assert RetryState().next_due(0., result.error) is None
    assert logs == []
    factory.assert_not_called()


def test_unsafe_snapshot_cannot_hit_existing_cache(monkeypatch):
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(200, json=completion())
    transports = install_real_sdk(monkeypatch, handler)
    service = translator.TranslationService()
    try:
        assert service.translate('Hello', settings()).text == 'Xin chào'
        result = service.translate('Hello', settings('http://remote.example.test/v1'))
        assert result.text == '' and result.error.code == 'invalid_endpoint'
        assert result.from_cache is False
        assert len(received) == 1
        assert transports[0].closes == 1
    finally:
        service.close()


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
@pytest.mark.parametrize('location', ['http://remote.example.test/fake-location-secret',
                                    'https://api.example.test/fake-location-secret'])
def test_real_sdk_redirect_is_not_retried(monkeypatch, status, location):
    received, logs = [], []
    def handler(request):
        received.append(request)
        return httpx.Response(status, headers={'Location': location}, content=b'fake-body-secret')
    install_real_sdk(monkeypatch, handler)
    service = translator.TranslationService(log_callback=logs.append)
    try:
        result = service.translate('Hello', settings())
    finally:
        service.close()
    assert result.text == '' and result.error.code == 'invalid_endpoint'
    assert result.error.retryable is False
    assert RetryState().next_due(0., result.error) is None
    assert len(received) == 1
    combined = str(result.error) + '\n'.join(logs)
    for sentinel in ('fake-api-key', 'fake-location-secret', 'fake-body-secret'):
        assert sentinel not in combined


def test_real_sdk_success_and_reconfigure_close(monkeypatch):
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(200, json=completion())
    transports = install_real_sdk(monkeypatch, handler)
    service = translator.TranslationService()
    try:
        assert service.translate('Hello', settings('http://localhost:8000/v1')).text == 'Xin chào'
        assert received[0].url.host == '127.0.0.1'
        assert received[0].url.path == '/v1/chat/completions'
        assert received[0].headers['authorization'] == 'Bearer fake-api-key'
        assert service.translate('Hello', settings('https://other.example.test/v1', 'fake-new-key')).text == 'Xin chào'
        assert transports[0].closes == 1
        assert received[1].headers['authorization'] == 'Bearer fake-new-key'
        assert len(received) == 2
    finally:
        service.close()
    assert [t.closes for t in transports] == [1, 1]


def test_real_sdk_redirect_cleanup_error_is_permanent(monkeypatch):
    class Stream(httpx.SyncByteStream):
        reads = 0
        def __iter__(self):
            self.reads += 1
            yield b'fake-body-secret'
        def close(self):
            raise OSError('fake-cleanup-secret')
    stream, received = Stream(), []
    def respond(request):
        received.append(request)
        return httpx.Response(307, headers={'Location': 'http://remote.example.test'}, stream=stream)
    install_real_sdk(monkeypatch, respond)
    service = translator.TranslationService()
    try:
        result = service.translate('Hello', settings())
    finally:
        service.close()
    assert result.error.code == 'invalid_endpoint' and not result.error.retryable
    assert RetryState().next_due(0., result.error) is None
    assert len(received) == 1 and stream.reads == 0
    assert 'fake-cleanup-secret' not in str(result.error)


def test_sdk_constructor_failure_closes_new_transport(monkeypatch):
    transports = install_real_sdk(monkeypatch, lambda request: httpx.Response(200, json=completion()))
    monkeypatch.setattr(translator, 'OpenAI', Mock(side_effect=ValueError('fake-api-key')))
    service = translator.TranslationService()
    result = service.translate('Hello', settings())
    service.close()
    assert result.error is not None and 'fake-api-key' not in str(result.error)
    assert len(transports) == 1 and transports[0].closes == 1


@pytest.mark.parametrize('provider', ['OpenAI', 'Google Gemini', 'DeepSeek', 'Google Translate'])
def test_other_providers_do_not_use_custom_http_factory(monkeypatch, provider):
    factory = Mock(side_effect=AssertionError('Custom client used for other provider'))
    monkeypatch.setattr(translator, 'build_custom_api_http_client', factory, raising=False)
    google = Mock()
    from core.contracts import TranslationResult
    google.translate.return_value = TranslationResult(text='Xin chào')
    service = translator.TranslationService(google_factory=lambda: google)
    snapshot = settings()
    snapshot = replace(snapshot, provider=replace(snapshot.provider, name=provider, base_url=None))
    try:
        assert service.translate('Hello', snapshot).error is None
    finally:
        service.close()
    factory.assert_not_called()
