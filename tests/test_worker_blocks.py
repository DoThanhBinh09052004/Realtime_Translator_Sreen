from dataclasses import replace
from threading import Event
import numpy as np
from core import config
from core.contracts import OcrResult, TranslationResult
from core.blocks.models import BlockTranslationResult
from core.worker import TranslationWorker


def test_static_thumbnail_still_refreshes_small_block_geometry(monkeypatch, runtime_settings, capture_geometry, span_factory):
    import core.worker as module
    w = TranslationWorker(config.State(), dict(left=100, top=100, width=800, height=600))
    settings = replace(runtime_settings, overlay_mode='blocks')
    rev = w.configure(settings)
    w._is_running = True
    w._take_snapshot()
    now, calls = [0.], []
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(module, 'ocr_image', lambda *a, **k: calls.append(1) or OcrResult('Hello', spans=(span_factory(),)))
    img = np.zeros((600, 800), dtype='uint8')
    for t in (0, .5, 1.49):
        now[0] = t
        w._process_block_frame(img, settings, rev, capture_geometry)
    assert len(calls) == 2
    now[0] = 1.5
    w._process_block_frame(img, settings, rev, capture_geometry)
    assert len(calls) == 3


def test_current_source_is_observed_before_applying_translation(monkeypatch, runtime_settings, capture_geometry, span_factory):
    import core.worker as module
    w = TranslationWorker(config.State(), dict(left=100, top=100, width=800, height=600))
    settings = replace(runtime_settings, overlay_mode='blocks')
    rev = w.configure(settings)
    w._is_running = True
    w._take_snapshot()
    monkeypatch.setattr(module, 'ocr_image', lambda *a, **k: OcrResult('Hello', spans=(span_factory(),)))
    monkeypatch.setattr(w, '_is_frame_changed', lambda *a: True)
    img = np.zeros((600, 800), dtype='uint8')
    w._process_block_frame(img, settings, rev, capture_geometry)
    w._process_block_frame(img, settings, rev, capture_geometry)
    job, = w._block_session.translation_jobs()
    old = BlockTranslationResult(rev, job.block_id, 'Hello', TranslationResult('old'))
    monkeypatch.setattr(w._block_translator, 'drain_results', lambda: (old,))
    monkeypatch.setattr(module, 'ocr_image', lambda *a, **k: OcrResult())
    frames = []
    w.blocks_updated.connect(frames.append)
    w._process_block_frame(img, settings, rev, capture_geometry)
    assert not frames[-1].blocks
