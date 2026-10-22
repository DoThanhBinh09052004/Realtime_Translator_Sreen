from dataclasses import replace

import numpy as np

from core import config
from core.contracts import EngineError, OcrResult, TranslationResult
from core.worker import TranslationWorker


def make_worker():
    config.save_provider_api_key("Google Gemini", "fake-key")
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    return worker


def test_static_frame_retries_failed_translation(monkeypatch):
    from core import worker as module

    worker = make_worker()
    settings = config.load_runtime_settings(worker.state, 500)
    settings = replace(settings, provider=replace(settings.provider, name="OpenAI", base_url=None))
    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module, "ocr_image", lambda *args, **kwargs: OcrResult(text="Hello"))
    attempts = []

    class Service:
        def translate(self, text, snapshot):
            attempts.append(text)
            if len(attempts) == 1:
                return TranslationResult(error=EngineError("timeout", "Timeout", True))
            return TranslationResult(text="Xin chào")

    image = np.zeros((40, 100), dtype=np.uint8)
    emitted = []
    worker.text_translated.connect(emitted.append)

    worker._process_frame(image, settings, worker._revision, Service())
    assert attempts == ["Hello"]
    now[0] = 0.99
    worker._process_frame(image, settings, worker._revision, Service())
    assert attempts == ["Hello"]
    now[0] = 1.0
    worker._process_frame(image, settings, worker._revision, Service())
    assert attempts == ["Hello", "Hello"]
    assert emitted == ["Xin chào"]


def test_old_revision_result_is_discarded(monkeypatch):
    from core import worker as module

    worker = make_worker()
    settings = config.load_runtime_settings(worker.state, 500)
    settings = replace(settings, provider=replace(settings.provider, name="OpenAI", base_url=None))
    monkeypatch.setattr(module, "ocr_image", lambda *args, **kwargs: OcrResult(text="Hello"))

    class ReconfiguringService:
        def translate(self, text, snapshot):
            worker.configure(replace(snapshot, target_lang="English"))
            return TranslationResult(text="stale translation")

    emitted = []
    worker.text_translated.connect(emitted.append)
    worker._process_frame(np.zeros((40, 100), dtype=np.uint8), settings,
                          worker._revision, ReconfiguringService())
    assert emitted == []


def test_retry_current_invalidates_worker_snapshot_without_mutating_cache():
    worker = make_worker()
    worker._prev_text = "previous text"
    thumbnail = np.zeros((40, 100), dtype=np.uint8)
    worker._prev_frame_thumb = thumbnail
    revision = worker._revision

    worker.retry_current()

    assert worker._revision == revision + 1
    assert worker._invalidated
    assert worker._prev_text == "previous text"
    assert worker._prev_frame_thumb is thumbnail


def test_ocr_failure_retries_without_frame_change(monkeypatch):
    from core import worker as module

    worker = make_worker()
    settings = config.load_runtime_settings(worker.state, 500)
    settings = replace(settings, provider=replace(settings.provider, name="OpenAI", base_url=None))
    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    results = [OcrResult(error=EngineError("ocr", "OCR failed", True)), OcrResult(text="Hello")]
    ocr_calls = []

    def recognize(*args, **kwargs):
        ocr_calls.append(1)
        return results.pop(0)

    monkeypatch.setattr(module, "ocr_image", recognize)
    translations = []

    class Service:
        def translate(self, text, snapshot):
            translations.append(text)
            return TranslationResult(text="Xin chào")

    image = np.zeros((40, 100), dtype=np.uint8)
    worker._process_frame(image, settings, worker._revision, Service())
    now[0] = 1.0
    worker._process_frame(image, settings, worker._revision, Service())
    assert len(ocr_calls) == 2
    assert translations == ["Hello"]
