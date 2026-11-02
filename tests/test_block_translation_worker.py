from threading import Event, get_ident
from dataclasses import replace
from core.blocks.models import BlockJob
from core.contracts import TranslationResult, EngineError
import pytest


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


@pytest.mark.parametrize('code,retry_after,due', [('timeout', None, 2.), ('rate_limit', None, 5.), ('rate_limit', 12., 12.)])
def test_gemini_retry_deadline_and_provider_cooldown(qtbot, runtime_settings, code, retry_after, due):
    from core.blocks.translation_worker import BlockTranslationWorker
    now, calls = [0.], []
    class Service:
        def translate(self, text, settings):
            calls.append((text, now[0]))
            if len(calls) == 1:
                return TranslationResult(error=EngineError(code, 'failed', True, retry_after))
            return TranslationResult('ok')
        def close(self): pass
    w = BlockTranslationWorker(clock=lambda: now[0], service_factory=Service)
    jobs = (BlockJob(1, 1, 'A', runtime_settings),)
    if code == 'rate_limit':
        jobs += (BlockJob(1, 2, 'B', runtime_settings),)
    keys = frozenset((j.block_id, j.source_text) for j in jobs)
    w.replace_pending(jobs, keys, 1)
    w.start()
    try:
        qtbot.waitUntil(lambda: bool(w.drain_results()))
        now[0] = due-.01
        w.replace_pending(jobs, keys, 1)
        assert calls == [('A', 0.)]
        now[0] = due
        w.replace_pending(jobs, keys, 1)
        qtbot.waitUntil(lambda: len(calls) >= 2)
        assert calls[1][1] == due
    finally:
        w.request_stop()
        assert w.wait(2000)


def test_auth_blocks_revision_until_explicit_retry(qtbot, runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    calls = []
    class Service:
        def translate(self, text, settings):
            calls.append(text)
            return TranslationResult(error=EngineError('auth', 'invalid key', False))
        def close(self): pass
    w = BlockTranslationWorker(service_factory=Service)
    def submit(rev):
        w.replace_pending((BlockJob(rev, 1, 'A', runtime_settings), BlockJob(rev, 2, 'B', runtime_settings)), frozenset({(1, 'A'), (2, 'B')}), rev)
    submit(1)
    w.start()
    try:
        qtbot.waitUntil(lambda: bool(w.drain_results()))
        submit(1)
        assert w.pending_count == 0 and calls == ['A']
        submit(2)
        qtbot.waitUntil(lambda: len(calls) == 2)
        assert calls == ['A', 'A']
    finally:
        w.request_stop()
        assert w.wait(2000)


def test_duplicate_text_ids_reuse_translation_service_cache(qtbot, runtime_settings, fake_translator):
    from core.blocks.translation_worker import BlockTranslationWorker
    from engines.translator import TranslationService
    w = BlockTranslationWorker(service_factory=TranslationService)
    jobs = (BlockJob(1, 1, 'Same', runtime_settings), BlockJob(1, 2, 'Same', runtime_settings))
    w.replace_pending(jobs, frozenset({(1, 'Same'), (2, 'Same')}), 1)
    w.start()
    results = []
    try:
        def finished():
            results.extend(w.drain_results())
            return len(results) == 2
        qtbot.waitUntil(finished)
        assert {r.block_id for r in results} == {1, 2}
        assert all(r.result.text == 'fake translation' for r in results)
        assert fake_translator.call_count == 1
    finally:
        w.request_stop()
        assert w.wait(2000)
