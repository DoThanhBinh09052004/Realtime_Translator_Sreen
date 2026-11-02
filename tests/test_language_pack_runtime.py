"""Managed OCR must use explicit assets and keep leases on the OCR owner."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import threading

import numpy as np
import pytest

from core.ocr_models import OcrModelError, OcrModelPaths
from engines import ocr


class RuntimeStore:
    def __init__(self, root: Path):
        self.root = root
        self.revision = 'one'
        self.events = []
        self.missing = False

    def identity(self, language_id):
        if self.missing:
            raise OcrModelError('Gói chưa được cài.')
        return language_id, self.revision

    def resolve(self, language_id):
        base = self.root / language_id / self.revision
        return OcrModelPaths(base / 'det', base / 'rec', base / 'cls', base / 'dict.txt')

    @contextmanager
    def lease(self, language_id):
        self.identity(language_id)
        self.events.append(('acquire', language_id, threading.get_ident()))
        try:
            yield self.resolve(language_id)
        finally:
            self.events.append(('release', language_id, threading.get_ident()))


@pytest.fixture(autouse=True)
def release_runtime_engine():
    ocr.release_ocr_engine()
    yield
    ocr.release_ocr_engine()


@pytest.mark.parametrize('code,language_id', [('en', 'en'), ('japan', 'ja'), ('ch', 'zh-Hans'), ('korean', 'ko')])
def test_managed_ocr_constructs_exact_language_paths_and_holds_lease(tmp_path, monkeypatch, code, language_id):
    store = RuntimeStore(tmp_path)
    calls = []
    def construct(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(ocr=lambda *args, **kw: [[]])
    monkeypatch.setattr(ocr, 'PaddleOCR', construct)
    result = ocr.ocr_image(np.zeros((20, 20), dtype='uint8'), code, store=store)
    assert result.error is None
    paths = store.resolve(language_id)
    assert calls[0]['det_model_dir'] == str(paths.det)
    assert calls[0]['rec_model_dir'] == str(paths.rec)
    assert calls[0]['cls_model_dir'] == str(paths.cls)
    assert calls[0]['rec_char_dict_path'] == str(paths.dictionary)
    assert calls[0]['lang'] == code
    assert store.events == [('acquire', language_id, threading.get_ident())]
    ocr.release_ocr_engine()
    assert store.events[-1] == ('release', language_id, threading.get_ident())


def test_pack_revision_switch_releases_old_lease_and_rebuilds_engine(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path)
    calls = []
    monkeypatch.setattr(ocr, 'PaddleOCR', lambda **kwargs: calls.append(kwargs) or SimpleNamespace(ocr=lambda *a, **k: [[]]))
    first = ocr.get_ocr_engine('ch', store=store)
    assert ocr.get_ocr_engine('ch', store=store) is first
    store.revision = 'two'
    second = ocr.get_ocr_engine('ch', store=store)
    assert second is not first
    assert len(calls) == 2
    assert calls[-1]['rec_model_dir'].endswith(str(Path('two') / 'rec'))
    assert [event[:2] for event in store.events] == [('acquire', 'zh-Hans'), ('release', 'zh-Hans'), ('acquire', 'zh-Hans')]


def test_managed_missing_pack_never_constructs_native_ocr(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path)
    store.missing = True
    monkeypatch.setattr(ocr, 'PaddleOCR', lambda **kwargs: pytest.fail('Missing pack must not construct or auto-download'))
    result = ocr.ocr_image(np.zeros((10, 10), dtype='uint8'), 'ch', store=store)
    assert result.error.code == 'ocr_model_missing'
    assert result.error.retryable is False
    assert store.events == []


def test_managed_native_failure_releases_lease_and_does_not_retry(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path)
    def fail(**kwargs):
        raise RuntimeError('sensitive-native-path')
    monkeypatch.setattr(ocr, 'PaddleOCR', fail)
    result = ocr.ocr_image(np.zeros((10, 10), dtype='uint8'), 'korean', store=store)
    assert result.error.code == 'ocr_model_missing'
    assert result.error.retryable is False
    assert 'sensitive-native-path' not in result.error.user_message
    assert [event[:2] for event in store.events] == [('acquire', 'ko'), ('release', 'ko')]
    assert ocr._current_engine is None


def test_injected_reader_preserves_stopped_worker_and_source_revision(tmp_path, monkeypatch):
    from core.config import State
    from core.contracts import OcrResult
    from core.worker import TranslationWorker
    reader_calls = []
    worker = TranslationWorker(State(), {'left': 0, 'top': 0, 'width': 20, 'height': 20}, ocr_reader=lambda image, lang: reader_calls.append(lang) or OcrResult('hello'))
    worker._is_running = True
    worker._process_dialogue_frame(np.zeros((20, 20), dtype='uint8'), worker._settings, worker.revision)
    assert reader_calls == ['en']
    worker._is_running = False
    old_revision = worker.revision
    from dataclasses import replace
    worker.configure(replace(worker._settings, source_lang='Japanese'))
    assert worker.revision > old_revision
    assert worker.is_running() is False


def test_config_keeps_known_source_without_installed_model(isolated_config):
    isolated_config.save_config('source_lang', 'Chinese')
    assert isolated_config.State().source == 'Chinese'
    assert isolated_config.load_config()['source_lang'] == 'Chinese'
