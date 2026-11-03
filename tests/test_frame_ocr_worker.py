"""Legacy worker contracts retained while frame processing is extracted."""
import numpy as np

from core import config
from core.contracts import EngineError, OcrResult
from core.runtime.worker import TranslationWorker


def test_worker_observation_uses_start_completion_and_capture_timestamps(monkeypatch, runtime_settings, capture_geometry):
    import core.runtime.worker as module
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker.configure(runtime_settings)
    worker._is_running = True
    snapshot = worker._take_snapshot()
    now = [10.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    def read(*args, **kwargs):
        now[0] = 10.4
        return OcrResult('frame')
    monkeypatch.setattr(worker, '_read_ocr', read)
    observations = []
    worker.observation_ready.connect(observations.append)
    assert worker._process_dialogue_frame(np.zeros((8, 8), dtype='uint8'), runtime_settings,
        snapshot.revision, capture_geometry, captured_at_s=9.5, force_scan=False) is False
    observation, = observations
    assert (observation.scan_id, observation.captured_at_s, observation.completed_at_s) == (1, 9.5, 10.4)
    assert observation.geometry is capture_geometry
    assert observation.settings is runtime_settings
    assert worker._dialogue_last_ocr == 10.


def test_worker_invalidation_resets_only_when_capture_takes_snapshot(monkeypatch, runtime_settings):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    worker.configure(runtime_settings)
    snapshot = worker._take_snapshot()
    monkeypatch.setattr(worker, '_read_ocr', lambda *a, **k: OcrResult(error=EngineError('ocr', 'bad', False)))
    observations = []
    worker.observation_ready.connect(observations.append)
    image = np.zeros((8, 8), dtype='uint8')
    worker._process_dialogue_frame(image, runtime_settings, snapshot.revision)
    thumb = worker._prev_frame_thumb
    worker.configure(runtime_settings)
    assert worker._prev_frame_thumb is thumb
    snapshot = worker._take_snapshot()
    assert worker._prev_frame_thumb is None
    assert worker._dialogue_last_ocr == float('-inf')
    worker._process_dialogue_frame(image, runtime_settings, snapshot.revision)
    assert [o.scan_id for o in observations] == [1, 1]


def test_worker_legacy_force_policy_is_read_after_detection(monkeypatch, runtime_settings):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    worker.configure(runtime_settings)
    snapshot = worker._take_snapshot()
    worker._dialogue_last_ocr = float('inf')
    def detect(image):
        worker.request_dialogue_scan(snapshot.revision, True)
        return False
    monkeypatch.setattr(worker, '_is_frame_changed', detect)
    monkeypatch.setattr(worker, '_read_ocr', lambda *a, **k: OcrResult('forced'))
    observations = []
    worker.observation_ready.connect(observations.append)
    worker._process_dialogue_frame(None, runtime_settings, snapshot.revision)
    assert [o.ocr.text for o in observations] == ['forced']
