"""GUI lifecycle decisions and real QThread drain/restart contracts."""
from dataclasses import replace
from threading import Event

import numpy as np
import pytest

from core import config
from core.contracts import OcrResult
from core.runtime.worker import TranslationWorker


@pytest.mark.parametrize('capture_running, translation_running', [(True, False), (False, True), (True, True)])
def test_pending_restart_waits_for_both_threads_and_keeps_first_session_policy(capture_running, translation_running):
    from core.runtime.lifecycle import WorkerLifecycle
    lifecycle = WorkerLifecycle()
    lifecycle.request_stop()
    assert not lifecycle.request_start(capture_running=capture_running,
        translation_running=translation_running, running=False, preserve_session=True)
    assert not lifecycle.request_start(capture_running=capture_running,
        translation_running=translation_running, running=False, preserve_session=False)
    assert lifecycle.threads_finished(capture_running=capture_running,
        translation_running=translation_running) is None
    action = lifecycle.threads_finished(capture_running=False, translation_running=False)
    assert action.kind == 'restart' and action.preserve_session is True
    assert not lifecycle.restart_pending
    lifecycle.started()
    # Late delivery from the retired thread cannot finish the new active run.
    assert lifecycle.threads_finished(capture_running=True, translation_running=True) is None
    assert lifecycle.threads_finished(capture_running=False, translation_running=False) is None


def test_stop_cancels_pending_restart_and_shutdown_is_emitted_once():
    from core.runtime.lifecycle import WorkerLifecycle
    lifecycle = WorkerLifecycle()
    lifecycle.request_restart(preserve_session=True)
    lifecycle.request_stop()
    assert not lifecycle.restart_pending
    assert lifecycle.threads_finished(capture_running=False, translation_running=True) is None
    assert lifecycle.threads_finished(capture_running=False, translation_running=False).kind == 'shutdown'
    assert lifecycle.threads_finished(capture_running=False, translation_running=False) is None


def test_direct_start_consumes_pending_intent_without_a_second_restart():
    from core.runtime.lifecycle import WorkerLifecycle
    lifecycle = WorkerLifecycle()
    lifecycle.request_restart(preserve_session=False)
    assert lifecycle.request_direct_start(capture_running=False, translation_running=False, preserve_session=False)
    lifecycle.started()
    assert not lifecycle.restart_pending
    assert lifecycle.threads_finished(capture_running=False, translation_running=False) is None


def test_rapid_stop_start_during_held_ocr_starts_one_backend_after_both_drain(qtbot, monkeypatch, runtime_settings):
    import core.runtime.worker as module
    entered, release, next_run = Event(), Event(), Event()
    reads = []
    created = []
    shutdown = []

    def reader(*a, **k):
        reads.append(1)
        if len(reads) == 1:
            entered.set()
            assert release.wait(5)
        else:
            next_run.set()
        return OcrResult('')

    class Desktop:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def grab(self, monitor): return np.zeros((8, 8, 4), dtype=np.uint8)

    monkeypatch.setattr(module.mss, 'mss', Desktop)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION, ocr_reader=reader)
    worker.configure(replace(runtime_settings, interval_ms=100))
    factory = worker._new_block_translator
    def new_backend():
        value = factory()
        created.append(value)
        return value
    monkeypatch.setattr(worker, '_new_block_translator', new_backend)
    worker.shutdown_finished.connect(lambda: shutdown.append(1))
    worker.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        worker.stop_worker()
        worker.start_worker()
        worker.start_worker()
        assert worker.restart_pending and len(created) == 1
        assert worker.translation_session_id == 1
        release.set()
        qtbot.waitUntil(next_run.is_set, timeout=3000)
        assert len(created) == 2 and worker.translation_session_id == 2
        worker._threads_finished()  # Delayed old finished delivery during the active run.
        assert worker.is_running() and not worker.restart_pending
        assert len(created) == 2 and shutdown == []
    finally:
        release.set()
        worker.stop_worker()
        qtbot.waitUntil(lambda: worker.is_drained, timeout=3000)
    assert shutdown == [1]
