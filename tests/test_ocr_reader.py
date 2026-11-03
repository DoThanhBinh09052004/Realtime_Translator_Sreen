from dataclasses import replace
from types import SimpleNamespace

import pytest

from core import config

from core.runtime import worker as worker_module
from core.contracts import OcrResult
from core.runtime.worker import TranslationWorker


def test_worker_reader_and_thread_resolution_are_selected_at_call_time(monkeypatch, runtime_settings, qtbot):
    worker = TranslationWorker(config.State(), {})
    image = object()

    def reader(actual_image, *, lang, enable_mkldnn, cpu_threads):
        assert actual_image is image
        return OcrResult(f'{lang}/{enable_mkldnn}/{cpu_threads}')

    monkeypatch.setattr(worker_module, 'ocr_image', reader)
    monkeypatch.setattr(config, 'resolve_ocr_threads', lambda auto, custom: 3 if auto else custom)
    worker._settings = replace(runtime_settings, ocr_performance_mode='eco', ocr_auto_threads=False, ocr_threads=2)
    assert worker._read_ocr(image, 'English').text == 'en/False/2'
    assert worker._read_ocr(image, 'japan', runtime_settings).text == 'japan/True/3'
    worker._ocr_reader = lambda *args, **kwargs: OcrResult('injected')
    assert worker._read_ocr(image, 'English').text == 'injected'


def test_worker_unknown_language_does_not_invoke_reader(qtbot):
    def forbidden(*args, **kwargs):
        pytest.fail('Unsupported language reached OCR')
    worker = TranslationWorker(config.State(), {}, ocr_reader=forbidden)
    result = worker._read_ocr(object(), 'unsupported')
    assert result.error.code == 'ocr_model_missing'
    assert result.error.retryable is False


@pytest.mark.parametrize('settings,expected', [(SimpleNamespace(), 'en/True/6'),
    (SimpleNamespace(ocr_performance_mode='eco', ocr_auto_threads=False, ocr_threads=99), 'en/False/12')])
def test_worker_performance_defaults_and_thread_bounds(monkeypatch, qtbot, settings, expected):
    monkeypatch.setattr(config.os, 'cpu_count', lambda: 12)
    def reader(image, *, lang, enable_mkldnn, cpu_threads):
        return OcrResult(f'{lang}/{enable_mkldnn}/{cpu_threads}')
    worker = TranslationWorker(config.State(), {}, ocr_reader=reader)
    assert worker._read_ocr(object(), 'English', settings).text == expected


def test_worker_legacy_reader_accepts_language_only(qtbot, runtime_settings):
    def reader(image, *, lang):
        return OcrResult(lang)
    worker = TranslationWorker(config.State(), {}, ocr_reader=reader)
    assert worker._read_ocr(object(), 'English', runtime_settings).text == 'en'


def test_worker_preserves_type_error_retry_from_reader_body(qtbot, runtime_settings):
    calls = []
    def reader(image, *, lang, **kwargs):
        calls.append(kwargs)
        if kwargs:
            raise TypeError('reader body failure')
        return OcrResult('legacy retry')
    worker = TranslationWorker(config.State(), {}, ocr_reader=reader)
    assert worker._read_ocr(object(), 'English', runtime_settings).text == 'legacy retry'
    assert len(calls) == 2 and calls[1] == {}


@pytest.mark.parametrize('source,expected', [('English', 'en'), ('japan', 'japan'), ('unsupported', None)])
def test_resolve_ocr_language(source, expected):
    from core.ocr.reader import resolve_ocr_language
    assert resolve_ocr_language(source) == expected


@pytest.mark.parametrize('settings,expected', [(SimpleNamespace(), 'en/True/6'),
    (SimpleNamespace(ocr_performance_mode='eco', ocr_auto_threads=False, ocr_threads=99), 'en/False/12')])
def test_read_ocr_resolves_performance_defaults_and_thread_bounds(monkeypatch, settings, expected):
    from core.ocr.reader import read_ocr
    monkeypatch.setattr(config.os, 'cpu_count', lambda: 12)
    def reader(image, *, lang, enable_mkldnn, cpu_threads):
        return OcrResult(f'{lang}/{enable_mkldnn}/{cpu_threads}')
    assert read_ocr(object(), 'en', settings, reader).text == expected


def test_read_ocr_resolves_threads_at_call_time_and_retries_legacy_reader(monkeypatch, runtime_settings):
    from core.ocr.reader import read_ocr
    monkeypatch.setattr(config, 'resolve_ocr_threads', lambda auto, custom: 5)
    def modern(image, *, lang, enable_mkldnn, cpu_threads):
        return OcrResult(str(cpu_threads))
    def legacy(image, *, lang):
        return OcrResult(lang)
    assert read_ocr(object(), 'en', runtime_settings, modern).text == '5'
    assert read_ocr(object(), 'en', runtime_settings, legacy).text == 'en'
