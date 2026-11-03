"""Capture runner contracts at the worker boundary."""
from dataclasses import replace
from threading import get_ident

import numpy as np
import pytest

from core import config
from core.contracts import OcrResult
from core.runtime.worker import TranslationWorker
from test_capture_app_integration import capture_values


def test_legacy_ocr_uses_frame_settings_when_settings_change_during_detection(qtbot, monkeypatch, runtime_settings):
    """A reconfigure during detection must not select the next frame's OCR settings."""
    seen = []
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION,
        ocr_reader=lambda image, **kwargs: seen.append(kwargs) or OcrResult('old frame'))
    original = replace(runtime_settings, ocr_performance_mode='eco', ocr_auto_threads=False, ocr_threads=2)
    worker.configure(original)
    worker._is_running = True
    worker._take_snapshot()
    observations = []
    worker.observation_ready.connect(observations.append)

    def detect(image):
        worker.configure(replace(original, ocr_performance_mode='high', ocr_threads=6))
        return True

    monkeypatch.setattr(worker, '_is_frame_changed', detect)
    worker._process_dialogue_frame(np.zeros((8, 8), dtype=np.uint8), original, worker.revision)
    assert seen[0]['enable_mkldnn'] is False
    assert seen[0]['cpu_threads'] == 2
    assert observations == []
    worker._is_running = False


@pytest.mark.parametrize('failure', ['open', 'read', 'close'])
def test_profile_capture_exception_cleans_up_on_capture_thread(qtbot, monkeypatch, capture_geometry, failure):
    """Native-source failures must still release source and OCR on their owner thread."""
    import core.runtime.worker as module
    from core.capture.models import SourceStatus
    owners = []
    released = []
    profile, context = capture_values(capture_geometry)

    class Source:
        def open(self, *args, **kwargs):
            owners.append(('open', get_ident()))
            if failure == 'open':
                raise RuntimeError('open failed')
        def read_latest(self, **kwargs):
            if failure == 'read':
                raise RuntimeError('read failed')
            return None
        def status(self):
            return SourceStatus(context.binding_epoch, 'error')
        def close(self):
            owners.append(('close', get_ident()))
            if failure == 'close':
                raise RuntimeError('close failed')

    monkeypatch.setattr(module, 'create_capture_source', lambda *a, **k: Source())
    monkeypatch.setattr(module, 'release_ocr_engine', lambda: released.append(get_ident()))
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker.configure_capture(profile, context)
    # QThread.run exceptions must not escape into Qt's process-wide exception hook.
    errors = []
    worker.capture_terminal_status.connect(errors.append)
    worker.start_worker()
    try:
        qtbot.waitUntil(lambda: worker.is_drained, timeout=3000)
    finally:
        worker.stop_worker()
        qtbot.waitUntil(lambda: worker.is_drained, timeout=3000)
    assert owners[0][0] == 'open' and owners[-1][0] == 'close'
    assert owners[0][1] == owners[-1][1] == released[0] != get_ident()
    qtbot.waitUntil(lambda: bool(errors), timeout=1000)


@pytest.mark.parametrize('capture_seconds, expected_sleep', [(0.04, 0.06), (0.12, 0.02)])
def test_legacy_loop_subtracts_capture_time_with_twenty_ms_floor(qtbot, monkeypatch, runtime_settings, capture_seconds, expected_sleep):
    import core.runtime.worker as module
    now = [0.]
    sleeps = []
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION,
        ocr_reader=lambda *a, **k: OcrResult(''))
    worker.configure(replace(runtime_settings, interval_ms=100))

    class Desktop:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, monitor):
            now[0] += capture_seconds
            return np.zeros((8, 8, 4), dtype=np.uint8)

    def sleep(seconds):
        sleeps.append(seconds)
        worker._is_running = False

    monkeypatch.setattr(module.mss, 'mss', Desktop)
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(module.time, 'sleep', sleep)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker._is_running = True
    worker.run()
    assert sleeps == pytest.approx([expected_sleep])


def test_profile_loop_polls_in_twenty_ms_steps_until_scan_deadline(qtbot, monkeypatch, runtime_settings, capture_geometry):
    import core.runtime.worker as module
    from core.capture.models import SourceStatus
    now = [0.]
    sleeps = []
    reads = []
    profile, context = capture_values(capture_geometry)
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker.configure(replace(runtime_settings, interval_ms=100))
    worker.configure_capture(profile, context)

    class Source:
        def open(self, *args, **kwargs): pass
        def read_latest(self, *, now_s):
            reads.append(now_s)
            if len(reads) == 2:
                worker._is_running = False
            return None
        def status(self): return SourceStatus(context.binding_epoch, 'ready')
        def close(self): pass

    def sleep_ms(ms):
        sleeps.append(ms)
        now[0] += ms / 1000

    monkeypatch.setattr(module, 'create_capture_source', lambda *a, **k: Source())
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(worker, 'msleep', sleep_ms)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker._is_running = True
    worker._run_capture()
    assert reads == pytest.approx([0., .1])
    assert sleeps == [20, 20, 20, 20, 20]

@pytest.mark.parametrize('replacement', [False, True])
def test_old_source_close_failure_keeps_old_binding_identity(qtbot, monkeypatch, capture_geometry, replacement):
    import core.runtime.worker as module
    from core.capture.models import SourceStatus
    profile, old_context = capture_values(capture_geometry)
    new_context = replace(old_context, binding_epoch=2)
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    terminal = []
    worker.capture_terminal_status.connect(terminal.append)
    closed = []

    class Source:
        def open(self, *a, **k): pass
        def read_latest(self, **k):
            worker.configure_capture(profile, new_context)
            if not replacement:
                worker._is_running = False
            return None
        def status(self): return SourceStatus(1, 'ready')
        def close(self):
            closed.append(1)
            raise RuntimeError('retired source close failed')

    monkeypatch.setattr(module, 'create_capture_source', lambda *a, **k: Source())
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker.configure_capture(profile, old_context)
    worker._is_running = True
    worker._run_capture()
    qtbot.wait(1)
    assert terminal and all(status.binding_epoch == 1 for status in terminal)
    assert worker.capture_context == new_context
    assert worker._context_source_invalid is False
    assert closed == [1]


@pytest.mark.parametrize('route', ['run_legacy', 'run_capture'])
@pytest.mark.parametrize('failure', ['stop', 'release', 'mark', 'compact', 'all'])
def test_cleanup_attempts_all_steps_and_reports_without_source_invalidation(qtbot, route, failure):
    """A failed cleanup step cannot strand run state or later native cleanup."""
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    runner = worker._new_runner()
    calls, errors, terminals = [], [], []
    worker.error_occurred.connect(errors.append)
    worker.capture_terminal_status.connect(terminals.append)

    def step(name, action=lambda: None):
        def invoke():
            calls.append(name)
            action()
            if failure in (name, 'all'):
                raise RuntimeError(name)
        return invoke

    class Desktop:
        def __enter__(self): return self
        def __exit__(self, *args): pass

    runner.ports = replace(runner.ports, take_snapshot=lambda: None,
        stop_translation=step('stop'), mark_stopped=step('mark', worker._runner_mark_stopped))
    runner.dependencies = replace(runner.dependencies, desktop_factory=Desktop,
        release_ocr=step('release'), compact_memory=step('compact'))
    getattr(runner, route)()
    assert calls == ['stop', 'release', 'mark', 'compact']
    assert not worker.is_running()
    assert len(errors) == 1 and errors[0].code == 'worker_cleanup'
    assert terminals == [] and not worker._context_source_invalid


def test_cleanup_error_from_old_run_is_dropped(qtbot):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    runner = worker._new_runner()
    errors = []
    worker.error_occurred.connect(errors.append)

    def release():
        worker.set_region(dict(left=1, top=1, width=10, height=10))
        raise RuntimeError('old run engine close')

    runner.ports = replace(runner.ports, take_snapshot=lambda: None)
    runner.dependencies = replace(runner.dependencies, release_ocr=release, compact_memory=lambda: None)
    runner.run_capture()
    assert errors == []
    assert not worker.is_running()


@pytest.mark.parametrize('profile_capture', [False, True])
def test_ocr_cleanup_failure_on_qthread_still_compacts_and_notifies(qtbot, monkeypatch, capture_geometry, profile_capture):
    import core.runtime.worker as module
    from core.capture.models import SourceStatus
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    profile, context = capture_values(capture_geometry)
    if profile_capture:
        worker.configure_capture(profile, context)
    owners, errors, terminals = [], [], []
    worker.error_occurred.connect(errors.append)
    worker.capture_terminal_status.connect(terminals.append)

    class Source:
        def open(self, *args, **kwargs): pass
        def read_latest(self, **kwargs):
            worker._is_running = False
            return None
        def status(self): return SourceStatus(context.binding_epoch, 'ready')
        def close(self): owners.append(('close', get_ident()))

    class Desktop:
        def __enter__(self): return self
        def __exit__(self, *args): owners.append(('close', get_ident()))
        def grab(self, monitor):
            worker._is_running = False
            return np.zeros((8, 8, 4), dtype=np.uint8)

    def release():
        owners.append(('release', get_ident()))
        raise RuntimeError('native close failed')

    monkeypatch.setattr(module, 'create_capture_source', lambda *a, **k: Source())
    monkeypatch.setattr(module.mss, 'mss', Desktop)
    monkeypatch.setattr(module, 'release_ocr_engine', release)
    monkeypatch.setattr(module, 'compact_memory', lambda: owners.append(('compact', get_ident())))
    worker.start_worker()
    try:
        qtbot.waitUntil(lambda: worker.is_drained and bool(errors), timeout=3000)
        assert not worker.is_running()
        assert [name for name, _ in owners] == ['close', 'release', 'compact']
        assert len({owner for _, owner in owners}) == 1 and owners[0][1] != get_ident()
        assert errors[-1].code == 'worker_cleanup'
        assert terminals == [] and not worker._context_source_invalid
    finally:
        worker.stop_worker()
        assert worker.wait(2000) and worker._block_translator.wait(2000)


def test_cleanup_reporting_failure_does_not_escape(qtbot):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    runner = worker._new_runner()
    calls = []

    def fail(*args):
        raise RuntimeError('failed')

    runner.ports = replace(runner.ports, take_snapshot=lambda: None,
        stop_translation=fail, publish_cleanup_error=fail)
    runner.dependencies = replace(runner.dependencies,
        release_ocr=lambda: calls.append('release'), compact_memory=lambda: calls.append('compact'))
    runner.run_capture()
    assert calls == ['release', 'compact']
