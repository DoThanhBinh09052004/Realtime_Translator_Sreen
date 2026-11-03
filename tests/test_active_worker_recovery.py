"""Recovery assertions on the active OCR -> dialogue observation path."""
import numpy as np
from core import config
from core.contracts import EngineError, OcrResult
from core.runtime.worker import TranslationWorker


def test_static_frame_ocr_error_retries_after_deadline(monkeypatch):
    from core.runtime import worker as module
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    settings, revision, _, _ = worker._take_snapshot()
    now, observations, calls = [0.], [], []
    results = [OcrResult(error=EngineError('ocr', 'failed', True)), OcrResult('Hello')]
    def recognize(*args, **kwargs):
        calls.append(now[0])
        return results.pop(0)
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(module, 'ocr_image', recognize)
    worker.observation_ready.connect(observations.append)
    image = np.zeros((40, 100), dtype=np.uint8)
    worker._process_dialogue_frame(image, settings, revision)
    now[0] = .99
    worker._process_dialogue_frame(image, settings, revision)
    assert calls == [0.]
    now[0] = 1.
    worker._process_dialogue_frame(image, settings, revision)
    assert calls == [0., 1.]
    assert observations[0].ocr.error is not None
    assert observations[1].ocr.text == 'Hello'


def test_old_revision_does_not_publish_ocr_observation(monkeypatch):
    from core.runtime import worker as module
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    settings, revision, _, _ = worker._take_snapshot()
    def recognize(*args, **kwargs):
        worker.configure(settings)
        return OcrResult('stale')
    monkeypatch.setattr(module, 'ocr_image', recognize)
    observations = []
    worker.observation_ready.connect(observations.append)
    worker._process_dialogue_frame(np.zeros((40, 100), dtype=np.uint8), settings, revision)
    assert observations == [] and worker.revision > revision
