from threading import Event, get_ident
from dataclasses import replace
from core.blocks.models import BlockJob
from core.contracts import TranslationResult, EngineError


def test_latest_snapshot_replaces_waiting_jobs_while_one_request_runs(qtbot, runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    entered, release = Event(), Event()
    threads, started = [], []
    class Service:
        def __init__(self):
            threads.append(get_ident())
        def translate(self, text, settings):
            threads.append(get_ident())
            started.append(text)
            entered.set()
            release.wait(2)
            return TranslationResult('translated '+text)
        def close(self):
            threads.append(get_ident())
    worker = BlockTranslationWorker(service_factory=Service)
    jobs = tuple(BlockJob(1, i, str(i), runtime_settings) for i in range(40))
    worker.replace_pending(jobs, frozenset((j.block_id, j.source_text) for j in jobs), 1)
    worker.start()
    try:
        qtbot.waitUntil(entered.is_set)
        assert worker.pending_count <= 32
        new = BlockJob(1, 100, 'new', runtime_settings)
        worker.replace_pending((new,), frozenset({(100, 'new')}), 1)
        release.set()
        qtbot.waitUntil(lambda: 'new' in started)
        qtbot.waitUntil(lambda: bool(worker.drain_results()))
        assert started == ['0', 'new']
    finally:
        release.set()
        worker.request_stop()
        assert worker.wait(2000)
    assert len(set(threads)) == 1 and threads[0] != get_ident()


def test_stop_during_request_discards_result_and_closes_client_after_release(qtbot, runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    entered, release, closed = Event(), Event(), Event()
    class Service:
        def translate(self, *args):
            entered.set()
            release.wait(2)
            return TranslationResult('old')
        def close(self):
            closed.set()
    w = BlockTranslationWorker(service_factory=Service)
    w.replace_pending((BlockJob(1, 1, 'A', runtime_settings),), frozenset({(1, 'A')}), 1)
    w.start()
    try:
        qtbot.waitUntil(entered.is_set)
        w.request_stop()
        assert not closed.is_set()
    finally:
        release.set()
        assert w.wait(2000)
    assert closed.is_set() and not w.drain_results()


def test_retry_is_bounded_and_exhausted_snapshot_cannot_resubmit(qtbot, runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    clock = [0.]
    attempts = []
    class Service:
        def translate(self, *args):
            attempts.append(clock[0])
            return TranslationResult(error=EngineError('network', 'failed', True))
        def close(self): pass
    w = BlockTranslationWorker(clock=lambda: clock[0], service_factory=Service)
    job = BlockJob(1, 1, 'A', runtime_settings)
    def submit(): w.replace_pending((job,), frozenset({(1, 'A')}), 1)
    submit()
    w.start()
    try:
        for i, t in enumerate((0., 2., 4., 8.)):
            clock[0] = t
            submit()
            qtbot.waitUntil(lambda: len(attempts) == i+1)
        clock[0] = 100
        submit()
        assert w.pending_count == 0
        assert attempts == [0., 2., 4., 8.]
    finally:
        w.request_stop()
        assert w.wait(2000)
