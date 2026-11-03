"""Frame scheduling and observation contracts without a worker or Qt loop."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from core.contracts import EngineError, OcrResult


@pytest.fixture
def frame_processor():
    from core.ocr.frame_processor import FrameOcrProcessor
    state = SimpleNamespace(now=0., current=True, observations=[], calls=[], result=OcrResult('text'))
    def read(image, source_name, *, settings):
        state.calls.append((state.now, source_name, settings))
        state.now += .25
        return state.result
    state.processor = FrameOcrProcessor(read_ocr=read, is_current=lambda revision: state.current,
        publish=state.observations.append, clock=lambda: state.now)
    state.image = np.zeros((40, 100), dtype='uint8')
    return state


@pytest.mark.parametrize('interval,deadline', [(500, 1.), (2500, 2.5)])
def test_periodic_static_scan_uses_start_time_and_preserves_observation(frame_processor, runtime_settings, capture_geometry, interval, deadline):
    s = frame_processor
    settings = replace(runtime_settings, interval_ms=interval)
    assert s.processor.process(s.image, settings, 7, capture_geometry, captured_at_s=-.1) is False
    s.now = deadline - .001
    assert s.processor.process(s.image, settings, 7) is True
    s.now = deadline
    assert s.processor.process(s.image, settings, 7) is False
    first, second = s.observations
    assert (first.revision, first.scan_id, first.captured_at_s, first.completed_at_s) == (7, 1, -.1, .25)
    assert first.settings is settings and first.geometry is capture_geometry
    assert (second.scan_id, second.captured_at_s, second.completed_at_s) == (2, deadline, deadline + .25)


def test_thumbnail_compares_against_last_changed_frame(frame_processor):
    p = frame_processor.processor
    assert p.is_frame_changed(np.zeros((40, 100), dtype='uint8'))
    assert not p.is_frame_changed(np.ones((40, 100), dtype='uint8'))
    boundary = np.ones((40, 100), dtype='uint8')
    boundary[:8] = 2  # Mean difference is exactly 1.2: the comparison is strict.
    assert not p.is_frame_changed(boundary)
    assert p.is_frame_changed(np.full((40, 100), 2, dtype='uint8'))
    assert not p.is_frame_changed(np.full((40, 100), 2, dtype='uint8'))
    assert p.is_frame_changed(None)  # Invalid image must fall back to OCR.


def test_force_scan_cannot_bypass_retry_deadline_or_exhaustion(frame_processor, runtime_settings):
    s = frame_processor
    s.result = OcrResult(error=EngineError('ocr', 'retry', True))
    s.processor.process(s.image, runtime_settings, 1)
    for before, due in [(1.249, 1.25), (3.499, 3.5), (7.749, 7.75)]:
        s.now = before
        assert s.processor.process(s.image, runtime_settings, 1, force_scan=True) is True
        s.now = due
        assert s.processor.process(s.image, runtime_settings, 1, force_scan=True) is False
    s.now = 100.
    assert s.processor.process(s.image, runtime_settings, 1, force_scan=True) is True
    assert [o.scan_id for o in s.observations] == [1, 2, 3, 4]
    s.result = OcrResult('recovered')
    assert s.processor.process(s.image + 10, runtime_settings, 1) is False
    assert s.observations[-1].ocr.text == 'recovered'


def test_change_resets_retry_budget_but_preserves_pending_deadline(frame_processor, runtime_settings):
    s = frame_processor
    s.result = OcrResult(error=EngineError('ocr', 'retry', True, retry_after_s=5.))
    s.processor.process(s.image, runtime_settings, 1)
    s.now = 1.
    assert s.processor.process(s.image + 10, runtime_settings, 1, force_scan=True) is True
    s.now = 5.25
    assert s.processor.process(s.image + 10, runtime_settings, 1, force_scan=True) is False
    assert len(s.observations) == 2


def test_revision_change_during_ocr_discards_observation_and_does_not_commit_scan(frame_processor, runtime_settings):
    s = frame_processor
    invalidate = [True]
    def stale_read(*args, **kwargs):
        if invalidate[0]:
            s.current = False
            invalidate[0] = False
        return OcrResult('frame')
    s.processor = type(s.processor)(read_ocr=stale_read, is_current=lambda revision: s.current,
        publish=s.observations.append, clock=lambda: s.now)
    assert s.processor.process(s.image, runtime_settings, 1) is False
    assert s.observations == []
    assert s.processor.last_ocr == float('-inf')
    # A stale frame is rejected before even invoking detection or OCR.
    assert s.processor.process(None, runtime_settings, 1,
        change_detector=lambda image: pytest.fail('stale frame detection')) is False
    # Reactivate the same processor: the discarded scan has no committed ID.
    s.current = True
    s.processor.process(s.image, runtime_settings, 2)
    assert s.observations[0].scan_id == 1


def test_reset_reopens_exhausted_static_frame_and_restarts_scan_ids(frame_processor, runtime_settings):
    s = frame_processor
    s.result = OcrResult(error=EngineError('ocr', 'terminal', False))
    s.processor.process(s.image, runtime_settings, 1)
    s.now = 20.
    assert s.processor.process(s.image, runtime_settings, 1, force_scan=True) is True
    s.processor.reset()
    s.result = OcrResult('reset')
    assert s.processor.process(s.image, runtime_settings, 2) is False
    assert [(o.revision, o.scan_id) for o in s.observations] == [(1, 1), (2, 1)]
