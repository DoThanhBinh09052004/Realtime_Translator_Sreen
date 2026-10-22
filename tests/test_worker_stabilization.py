from dataclasses import replace

import numpy as np
import pytest

from core import config
from core import worker as module
from core.contracts import EngineError, OcrResult, TranslationResult
from core.worker import TranslationWorker


@pytest.fixture
def pipeline(monkeypatch):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    settings, revision, _, _ = worker._take_snapshot()
    settings = replace(settings, provider=replace(settings.provider, name='OpenAI'))
    now = [0.0]
    observations, requests, subtitles, refreshed = [], [], [], []
    outcome = [TranslationResult(text='translated')]

    def recognize(*args, **kwargs):
        observations.append(1)
        return OcrResult(text=source[0])

    class Service:
        def translate(self, text, snapshot):
            requests.append(text)
            return outcome[0]

    source = ['Hello world']
    monkeypatch.setattr(module, 'ocr_image', recognize)
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    worker.text_translated.connect(subtitles.append)
    worker.text_unchanged.connect(lambda: refreshed.append(1))

    def frame(text=None, at=0, changed=False):
        if text is not None:
            source[0] = text
        now[0] = at
        if changed:
            worker._prev_frame_thumb = None
        worker._process_frame(np.zeros((40, 100), dtype=np.uint8), settings, revision, Service())

    return worker, frame, observations, requests, subtitles, refreshed, outcome


def test_pending_forces_second_static_ocr_then_restores_idle_optimization(pipeline):
    worker, frame, observations, requests, subtitles, refreshed, _ = pipeline
    frame()
    assert requests == []
    assert subtitles == []
    frame(at=0.5)
    assert requests == ['Hello world']
    assert subtitles == ['translated']
    frame(at=1)
    assert len(observations) == 2
    assert refreshed == [1]
    assert not worker._stabilizer.has_pending


def test_trailing_fragment_refreshes_without_replacing_translation(pipeline):
    _, frame, _, requests, subtitles, refreshed, _ = pipeline
    frame()
    frame(at=0.5)
    frame('world', at=1, changed=True)
    frame(at=1.5)
    assert requests == ['Hello world']
    assert subtitles == ['translated']
    assert refreshed == [1, 1]
    frame('', at=2, changed=True)
    frame('world', at=2.5, changed=True)
    frame(at=3)
    assert requests == ['Hello world', 'world']


def test_progressive_text_uses_original_two_second_deadline(pipeline):
    _, frame, _, requests, _, _, _ = pipeline
    frame('Hello', at=10)
    frame('Hello there', at=11.5, changed=True)
    assert requests == []
    frame('Hello there friend', at=12, changed=True)
    assert requests == ['Hello there friend']


def test_disappearing_text_failure_is_not_committed_and_retries(pipeline):
    worker, frame, _, requests, subtitles, _, outcome = pipeline
    outcome[0] = TranslationResult(error=EngineError('timeout', 'Timeout', True))
    frame('Brief subtitle')
    frame('', at=0.5, changed=True)
    assert requests == ['Brief subtitle']
    assert worker._prev_text == ''
    assert subtitles == []
    frame(at=1)
    assert len(requests) == 1
    outcome[0] = TranslationResult(text='success')
    frame(at=1.5)
    assert requests == ['Brief subtitle', 'Brief subtitle']
    assert subtitles == ['success']
    assert not worker._stabilizer.has_pending


@pytest.mark.parametrize('retryable,expected', [(True, 4), (False, 1)])
def test_pending_does_not_bypass_retry_budget_or_permanent_failure(pipeline, retryable, expected):
    _, frame, _, requests, _, _, outcome = pipeline
    outcome[0] = TranslationResult(error=EngineError('timeout', 'Failure', retryable))
    frame()
    for at in [0.5, 1.5, 3.5, 7.5, 20, 30]:
        frame(at=at)
    assert len(requests) == expected


def test_new_subtitle_still_stabilizes_after_permanent_failure(pipeline):
    _, frame, _, requests, subtitles, _, outcome = pipeline
    outcome[0] = TranslationResult(error=EngineError('auth', 'Failure', False))
    frame()
    frame(at=0.5)
    assert requests == ['Hello world']
    outcome[0] = TranslationResult(text='new translation')
    frame('A new subtitle', at=1, changed=True)
    frame(at=1.5)
    assert requests == ['Hello world', 'A new subtitle']
    assert subtitles == ['new translation']


@pytest.mark.parametrize('invalidate', ['configure', 'region', 'retry'])
def test_snapshot_invalidation_clears_pending_candidate(pipeline, invalidate):
    worker, frame, _, _, _, _, _ = pipeline
    frame('Old pending')
    assert worker._stabilizer.has_pending
    if invalidate == 'configure':
        worker.configure(config.load_runtime_settings(worker.state, 500))
    elif invalidate == 'region':
        worker.set_region(config.DEFAULT_REGION)
    else:
        worker.retry_current()
    worker._take_snapshot()
    assert not worker._stabilizer.has_pending
    assert worker._stabilizer.observe('Old pending', 2).action == 'wait'


def test_stale_translation_cannot_commit(pipeline):
    worker, frame, _, _, subtitles, _, _ = pipeline
    frame()
    settings = config.load_runtime_settings(worker.state, 500)

    class Service:
        def translate(self, text, snapshot):
            worker.configure(snapshot)
            return TranslationResult(text='stale')

    worker._process_frame(np.zeros((40, 100), dtype=np.uint8), settings, worker._revision, Service())
    assert worker._prev_text == ''
    assert worker._stabilizer.has_pending
    assert subtitles == []
    worker._take_snapshot()
    assert not worker._stabilizer.has_pending


def test_restart_invalidates_pending_state(monkeypatch, pipeline):
    worker, frame, _, _, _, _, _ = pipeline
    frame('Old pending')
    monkeypatch.setattr(module.QThread, 'start', lambda *args: None)
    worker.start()
    worker._take_snapshot()
    assert not worker._stabilizer.has_pending
