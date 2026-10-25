import httpx
import pytest


def make_client(base_url, transport):
    from engines.custom_api_http import build_custom_api_http_client
    return build_custom_api_http_client(base_url, timeout_s=8., transport=transport)


@pytest.mark.parametrize('url', ['https://api.example.test/v1', 'http://127.0.0.1:8000/v1', 'http://[::1]:8000/v1'])
def test_allowed_https_and_loopback_dispatch(url):
    received = []
    def respond(request):
        received.append(request)
        return httpx.Response(200, json={'ok': True})
    with make_client(url, httpx.MockTransport(respond)) as client:
        assert client.post(url + '/chat/completions', content=b'fake-source').status_code == 200
    assert len(received) == 1
    assert received[0].content == b'fake-source'


@pytest.mark.parametrize('target', ['https://other.example.test/v1', 'http://127.0.0.1/v1',
                                  'http://api.example.test/v1', 'https://api.example.test:8443/v1'])
def test_origin_change_is_blocked_before_transport(target):
    from core.endpoint_policy import EndpointPolicyError
    received = []
    def respond(request):
        received.append(request)
        return httpx.Response(200)
    with make_client('https://api.example.test/v1', httpx.MockTransport(respond)) as client:
        with pytest.raises(EndpointPolicyError):
            client.post(target)
    assert received == []


@pytest.mark.parametrize('status', [300, 301, 302, 303, 304, 307, 308, 399])
@pytest.mark.parametrize('location', ['http://remote.example.test/fake-location-secret',
                                    'https://other.example.test/fake-location-secret',
                                    'https://api.example.test/fake-location-secret', '/fake-location-secret'])
def test_all_redirects_are_terminal(status, location):
    from core.endpoint_policy import EndpointPolicyError
    received, responses = [], []
    def respond(request):
        received.append(request)
        response = httpx.Response(status, headers={'Location': location}, content=b'fake-body-secret')
        responses.append(response)
        return response
    with make_client('https://api.example.test/v1', httpx.MockTransport(respond)) as client:
        # Even an explicit per-call override must not forward the request.
        with pytest.raises(EndpointPolicyError) as error:
            client.post('https://api.example.test/v1/chat/completions', follow_redirects=True)
    assert len(received) == 1
    assert responses[0].is_closed
    assert 'fake-location-secret' not in str(error.value)
    assert 'fake-body-secret' not in str(error.value)


def test_request_hook_canonicalizes_localhost_before_transport():
    received = []
    def respond(request):
        received.append(request)
        return httpx.Response(200)
    with make_client('http://127.0.0.1:8000/v1', httpx.MockTransport(respond)) as client:
        client.post('http://localhost:8000/v1/chat/completions')
    assert len(received) == 1
    assert received[0].url.host == '127.0.0.1'


def test_custom_client_closes_transport():
    class Transport(httpx.BaseTransport):
        closes = 0
        def handle_request(self, request):
            return httpx.Response(200)
        def close(self):
            self.closes += 1
    transport = Transport()
    with make_client('https://api.example.test/v1', transport) as client:
        client.post('https://api.example.test/v1/chat/completions')
    assert transport.closes == 1


def test_environment_proxy_is_not_used_and_tls_stays_enabled(monkeypatch):
    from engines.custom_api_http import build_custom_api_http_client
    from httpx import _client
    created, received = [], []
    class Transport(httpx.BaseTransport):
        def __init__(self, **kwargs):
            created.append(kwargs)
        def handle_request(self, request):
            received.append(request)
            return httpx.Response(200)
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.setenv(name, 'http://proxy.example.test:8080')
    for name in ('NO_PROXY', 'no_proxy'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(_client, 'HTTPTransport', Transport)
    with build_custom_api_http_client('http://localhost:8000/v1', timeout_s=8.) as client:
        client.post('http://localhost:8000/v1/chat/completions')
    assert len(created) == len(received) == 1
    assert created[0].get('proxy') is None
    assert created[0].get('verify', True) is not False
    assert created[0].get('trust_env') is False
    assert received[0].url.host == '127.0.0.1'
