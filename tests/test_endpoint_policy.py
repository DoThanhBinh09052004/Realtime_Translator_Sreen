import json
from pathlib import Path

import pytest

from core import config


@pytest.mark.parametrize('value, expected', [
    (' HTTPS://Api.Example.test:443/v1/ ', 'https://api.example.test/v1'),
    ('http://LOCALHOST:8080/v1/', 'http://127.0.0.1:8080/v1'),
    ('http://127.0.0.1:8000/v1', 'http://127.0.0.1:8000/v1'),
    ('http://127.0.0.2:80/v1', 'http://127.0.0.2/v1'),
    ('http://[::1]:8080/v1/', 'http://[::1]:8080/v1'),
    ('https://192.168.1.20/v1', 'https://192.168.1.20/v1'),
    ('https://[2001:db8::1]/v1', 'https://[2001:db8::1]/v1'),
    ('https://b\u00fccher.example/v1', 'https://xn--bcher-kva.example/v1'),
])
def test_normalizes_allowed_endpoint_without_dns(value, expected):
    from core.endpoint_policy import normalize_custom_api_endpoint
    assert normalize_custom_api_endpoint(value) == expected


@pytest.mark.parametrize('value', [
    'http://api.example.test/v1', 'http://192.168.1.20/v1',
    'http://localhost.evil.test/v1', 'http://localhost./v1',
    'http://sub.localhost/v1', 'http://127.1/v1', 'http://2130706433/v1',
    'http://0177.0.0.1/v1', 'http://[::ffff:127.0.0.1]/v1',
    'http://[::1%25lo]/v1', 'https://fake-key@api.example.test/v1',
    'https://api.example.test/v1?token=fake-key', 'https://api.example.test/v1?',
    'https://api.example.test/v1#fragment', 'https://api.example.test:0/v1',
    'https://api.example.test:65536/v1', 'https://api.example.test:bad/v1',
    'https://api.example.test:/v1', 'https://api.example.test\\@localhost/v1',
    'https://api.example.test/\nv1', '\thttps://api.example.test/v1',
    'https://api.example.test/ v1', 'https://api.example.test/\x7fv1',
    'https://[::1/v1', 'file:///tmp/api', 'https:///v1', '', None, 12, {},
])
def test_rejects_unsafe_or_ambiguous_endpoint(value):
    from core.endpoint_policy import EndpointPolicyError, normalize_custom_api_endpoint
    with pytest.raises(EndpointPolicyError) as error:
        normalize_custom_api_endpoint(value)
    assert 'fake-key' not in str(error.value)
    assert 'api.example.test' not in str(error.value)


def test_empty_endpoint_only_allowed_for_config_default():
    from core.endpoint_policy import EndpointPolicyError, normalize_custom_api_endpoint
    assert normalize_custom_api_endpoint('', allow_empty=True) == ''
    with pytest.raises(EndpointPolicyError):
        normalize_custom_api_endpoint(None, allow_empty=True)


def test_unsafe_legacy_config_is_sanitized_without_write():
    path = Path(config.CONFIG_PATH)
    raw = {'current_provider': 'Custom API', 'custom_api_base_url': 'http://remote.example.test/v1',
           'provider_models': {'Custom API': 'custom-model'}}
    original = json.dumps(raw).encode()
    path.write_bytes(original)
    snapshot = config.load_provider_settings()
    assert snapshot.base_url == ''
    assert (snapshot.name, snapshot.model_id) == ('Custom API', 'custom-model')
    assert path.read_bytes() == original


def test_invalid_save_preserves_config():
    config.save_custom_api_base_url('https://api.example.test/v1')
    path = Path(config.CONFIG_PATH)
    original = path.read_bytes()
    with pytest.raises(config.ConfigError) as error:
        config.save_custom_api_base_url('http://fake-key@remote.example.test/v1')
    assert path.read_bytes() == original
    assert 'fake-key' not in str(error.value)
    assert 'remote.example.test' not in str(error.value)
