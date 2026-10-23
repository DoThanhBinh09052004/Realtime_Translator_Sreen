from dataclasses import replace
from threading import Event
from core.contracts import TranslationResult, EngineError
from core.blocks.models import BlockJob
from core.google_recovery import GoogleRecoveryGate


def google_settings(settings):
    return replace(settings,provider=replace(settings.provider,name='Google Translate',api_key='',model_id=''))


def test_queue_has_shared_budget_even_when_scene_changes(qtbot, runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    clock, calls = [0.], []
    gate = GoogleRecoveryGate()
    class Service:
        def translate(self,text,*a):
            calls.append(text)
            return TranslationResult(error=EngineError('network','failed',True))
        def close(self): pass
    w = BlockTranslationWorker(clock=lambda:clock[0],service_factory=Service,google_recovery=gate)
    settings = google_settings(runtime_settings)
    def submit(rev):
        jobs = tuple(BlockJob(rev,i,f'{rev}:{i}',settings) for i in range(32))
        w.replace_pending(jobs,frozenset((j.block_id,j.source_text) for j in jobs),rev)
    submit(1); w.start()
    try:
        for i,t in enumerate((0,1,3,7)):
            clock[0] = t; submit(i+1)
            qtbot.waitUntil(lambda:len(calls)==i+1)
            qtbot.waitUntil(lambda:gate.snapshot(now_s=t).phase != 'ready')
        assert gate.snapshot(now_s=10000).phase == 'paused'
        clock[0]=10000; submit(10)
        assert not gate.can_dispatch(now_s=10000) and len(calls)==4
        assert w.pending_count <= 32
    finally:
        w.request_stop(); assert w.wait(2000)


def test_stale_source_error_updates_gate_but_never_results(qtbot,runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    entered,release=Event(),Event()
    gate=GoogleRecoveryGate()
    class Service:
        def translate(self,*a):
            entered.set(); release.wait(2)
            return TranslationResult(error=EngineError('network','fail',True))
        def close(self): pass
    w=BlockTranslationWorker(clock=lambda:0.,service_factory=Service,google_recovery=gate)
    settings=google_settings(runtime_settings)
    w.replace_pending((BlockJob(1,1,'A',settings),),frozenset({(1,'A')}),1); w.start()
    try:
        qtbot.waitUntil(entered.is_set)
        w.replace_pending((BlockJob(2,2,'B',settings),),frozenset({(2,'B')}),2)
        release.set()
        qtbot.waitUntil(lambda:gate.snapshot(now_s=0).retries_issued==1)
        assert not w.drain_results()
        assert gate.snapshot(now_s=0).not_before_s==1
    finally:
        release.set(); w.request_stop(); assert w.wait(2000)


def test_older_snapshot_cannot_repopulate_cleared_pending(runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    w=BlockTranslationWorker()
    w.replace_pending((),frozenset(),5)
    w.replace_pending((BlockJob(4,1,'old',google_settings(runtime_settings)),),frozenset({(1,'old')}),4)
    assert w.pending_count==0
