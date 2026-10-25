import base64
from pathlib import Path

import pytest


class FakeProtector:
    def protect(self, value):
        return b'protected:' + base64.b64encode(value)

    def unprotect(self, value):
        if not value.startswith(b'protected:'):
            raise ValueError('fake-secret')
        return base64.b64decode(value[10:])


def make_store(tmp_path, protector=None):
    from core.secrets import SecretStore
    return SecretStore(tmp_path, protector=protector or FakeProtector())


def test_persisted_key_is_encrypted_and_survives_new_store(tmp_path):
    store = make_store(tmp_path)
    store.set('OpenAI', 'fake-sensitive-key', persist=True)
    blob, = tmp_path.glob('*.bin')
    assert b'fake-sensitive-key' not in blob.read_bytes()
    assert make_store(tmp_path).get('OpenAI') == 'fake-sensitive-key'
    assert 'fake-sensitive-key' not in repr(store)


def test_session_mode_removes_saved_key_and_does_not_encrypt(tmp_path):
    store = make_store(tmp_path)
    store.set('OpenAI', 'old-key', persist=True)
    store.set('OpenAI', 'session-key', persist=False)
    assert store.get('OpenAI') == 'session-key'
    assert make_store(tmp_path).get('OpenAI') is None
    assert not list(tmp_path.glob('*.bin'))


def test_dpapi_failure_is_safe_and_session_key_still_works(tmp_path):
    from core.secrets import SecretStoreError
    class Broken:
        def protect(self, value):
            raise OSError('fake-sensitive-key')
    store = make_store(tmp_path, Broken())
    with pytest.raises(SecretStoreError) as error:
        store.set('OpenAI', 'fake-sensitive-key', persist=True)
    assert 'fake-sensitive-key' not in str(error.value)
    assert store.get('OpenAI') is None
    store.set('OpenAI', 'session-key', persist=False)
    assert store.get('OpenAI') == 'session-key'


def test_failed_atomic_write_preserves_previous_key(tmp_path, monkeypatch):
    from core import secrets
    store = make_store(tmp_path)
    store.set('OpenAI', 'original', persist=True)
    def denied(*args):
        raise OSError('sensitive-exception')
    monkeypatch.setattr(secrets.os, 'replace', denied)
    with pytest.raises(secrets.SecretStoreError):
        store.set('OpenAI', 'replacement', persist=True)
    assert store.get('OpenAI') == 'original'
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize('provider', ['../escape', 'unknown', 'Google Translate'])
def test_provider_paths_are_whitelisted(tmp_path, provider):
    from core.secrets import SecretStoreError
    with pytest.raises(SecretStoreError):
        make_store(tmp_path).set(provider, 'fake-key', persist=True)
    assert not list(tmp_path.iterdir())


def test_corrupt_blob_does_not_crash_config_or_expose_exception(tmp_path, monkeypatch):
    from core import config
    store = make_store(tmp_path)
    store.set('OpenAI', 'key', persist=True)
    blob, = tmp_path.glob('*.bin')
    blob.write_bytes(b'corrupt')
    monkeypatch.setattr(config, '_secret_store', store, raising=False)
    assert config.load_provider_api_key('OpenAI') == ''
    assert config.provider_key_storage('OpenAI') == 'unavailable'


def test_delete_removes_disk_and_session(tmp_path):
    store = make_store(tmp_path)
    for persist in (True, False):
        store.set('OpenAI', 'key', persist=persist)
        store.delete('OpenAI')
        assert store.get('OpenAI') is None
        assert not list(tmp_path.glob('*.bin'))


def test_native_windows_dpapi_roundtrip_with_fake_key(tmp_path):
    import sys
    from core.secrets import SecretStore
    if sys.platform != 'win32':
        pytest.skip('Native Windows DPAPI check')
    store = SecretStore(tmp_path)
    store.set('OpenAI', 'fake-native-dpapi-key', persist=True)
    assert SecretStore(tmp_path).get('OpenAI') == 'fake-native-dpapi-key'
    blob, = tmp_path.glob('*.bin')
    assert b'fake-native-dpapi-key' not in blob.read_bytes()


def test_failed_session_conversion_preserves_active_key(tmp_path, monkeypatch):
    from core.secrets import SecretStoreError
    store = make_store(tmp_path)
    store.set('OpenAI', 'original', persist=True)
    def denied(*args, **kwargs):
        raise PermissionError('sensitive-exception')
    monkeypatch.setattr(Path, 'unlink', denied)
    with pytest.raises(SecretStoreError):
        store.set('OpenAI', 'session', persist=False)
    assert store.get('OpenAI') == 'original'


def test_oversized_utf8_key_does_not_replace_valid_credential(tmp_path):
    from core.secrets import SecretStoreError
    store = make_store(tmp_path)
    store.set('OpenAI', 'original', persist=True)
    with pytest.raises(SecretStoreError):
        store.set('OpenAI', '\U0001f512' * 4097, persist=True)
    assert store.get('OpenAI') == 'original'
