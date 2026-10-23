from email.utils import formatdate
from threading import Thread, get_ident
import httpx
import pytest


def test_joins_all_segments_without_losing_whitespace():
    from engines.google_translate import parse_google_response
    assert parse_google_response([[['Xin chào. ', 'Hello.'], ['Thế giới!', 'World!']], None, 'en']) == 'Xin chào. Thế giới!'
    for payload in ({}, [], [None], [[['']]], [[['valid'], None]], [[[None]]]):
        with pytest.raises(ValueError):
            parse_google_response(payload)


@pytest.mark.parametrize('lang,code', [('English','en'),('Japanese','ja'),('Chinese','zh-CN'),('Korean','ko'),('Vietnamese','vi')])
def test_maps_all_app_languages(lang, code):
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[[['Dịch 日本語', 'source']]])
    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = GoogleTranslateClient(client_factory=lambda: client)
    try:
        result = adapter.translate('Hello 日本語', lang, 'Vietnamese')
        assert result.text == 'Dịch 日本語'
        assert result.input_tokens is result.output_tokens is None
        params = dict(calls[0].url.params)
        assert params == dict(client='gtx', sl=code, tl='vi', dt='t', q='Hello 日本語')
    finally:
        adapter.close()


def test_invalid_input_never_calls_transport():
    from engines.google_translate import GoogleTranslateClient
    def forbidden(): raise AssertionError('No client for invalid or empty input')
    adapter = GoogleTranslateClient(client_factory=forbidden)
    assert adapter.translate('', 'English', 'Vietnamese').text == ''
    for text, source in [('x'*2001,'English'), ('hi','unknown')]:
        assert adapter.translate(text, source, 'Vietnamese').error.code == 'invalid_input'


@pytest.mark.parametrize('status,code,retryable', [(408,'timeout',True),(429,'rate_limit',True),(503,'network',True),(403,'service_unavailable',False),(404,'service_unavailable',False),(302,'service_unavailable',False),(400,'invalid_input',False)])
def test_google_http_errors_are_safe(status, code, retryable):
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, text='secret response', headers={'retry-after':'12'})
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        result = adapter.translate('secret text', 'English', 'Vietnamese')
        assert result.error.code == code and result.error.retryable == retryable
        assert len(calls) == 1 and 'secret' not in result.error.user_message
        if status == 429: assert result.error.retry_after_s == 12
    finally:
        adapter.close()


@pytest.mark.parametrize('failure,code', [('html','invalid_response'),('timeout','timeout'),('network','network')])
def test_transport_and_html_errors(failure, code):
    from engines.google_translate import GoogleTranslateClient
    def respond(request):
        if failure == 'timeout': raise httpx.ReadTimeout('secret', request=request)
        if failure == 'network': raise httpx.ConnectError('secret', request=request)
        return httpx.Response(200, text='<html>blocked</html>')
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        result = adapter.translate('Hello', 'English', 'Vietnamese')
        assert result.error.code == code and not result.text
    finally:
        adapter.close()


def test_retry_after_seconds_http_date_and_invalid_values():
    from engines.google_translate import parse_retry_after
    now = 1700000000.
    assert parse_retry_after('12', now_epoch_s=now) == 12
    assert parse_retry_after(formatdate(now+12, usegmt=True), now_epoch_s=now) == 12
    assert parse_retry_after(formatdate(now-12, usegmt=True), now_epoch_s=now) == 0
    for value in (None, '', '-1', 'NaN', 'Infinity', 'broken'):
        assert parse_retry_after(value, now_epoch_s=now) is None


def test_client_factory_use_and_close_on_same_owner_thread():
    from engines.google_translate import GoogleTranslateClient
    threads = []
    class Client:
        def __init__(self): threads.append(get_ident())
        def get(self, *a, **kw):
            assert kw['timeout'] == 8.0
            assert not kw['follow_redirects']
            threads.append(get_ident())
            return httpx.Response(200, json=[[['ok']]])
        def close(self): threads.append(get_ident())
    adapter = GoogleTranslateClient(client_factory=Client)
    def work():
        assert adapter.translate('hi','English','Vietnamese').text == 'ok'
        adapter.close()
        adapter.close()
    thread = Thread(target=work)
    thread.start(); thread.join()
    assert len(threads) == 3 and len(set(threads)) == 1 and threads[0] != get_ident()
