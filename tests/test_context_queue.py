from dataclasses import replace
from core.blocks.models import BlockJob
from core.blocks.translation_worker import BlockTranslationWorker
from core.contracts import TranslationResult, EngineError
from core.dialogue.context_builder import build_context
from core.dialogue.context_models import ContextOutcome
from tests.context_helpers import make_turn,make_view

def test_retry_same_version_keeps_snapshot(qtbot,runtime_settings):
    now=[0.]; calls=[]
    snap=build_context(make_view(),make_turn(text='Hello'))
    newer=build_context(make_view(epoch=2),make_turn(text='Hello'))
    class Service:
        def translate(self,text,settings,*,context):
            calls.append(context)
            return TranslationResult(error=EngineError('network','retry',True)) if len(calls)==1 else TranslationResult('Xin chào',context=ContextOutcome(context.stamp))
        def close(self): pass
    worker=BlockTranslationWorker(clock=lambda:now[0],service_factory=Service)
    job=BlockJob(1,0,'Hello',runtime_settings,1,1,context=snap)
    worker.replace_pending((job,),{(1,0,1)},1); worker.start()
    try:
        qtbot.waitUntil(lambda:bool(worker.drain_results()))
        worker.replace_pending((replace(job,context=newer),),{(1,0,1)},1)
        now[0]=2
        qtbot.waitUntil(lambda:len(calls)==2)
        assert calls==[snap,snap]
        qtbot.waitUntil(lambda:bool(worker.drain_results()))
        worker.replace_pending((replace(job,context=newer),),{(1,0,1)},1)
        assert worker.pending_count==0
    finally: worker.request_stop(); assert worker.wait(2000)

def test_outcome_stamp_mismatch_discards_metadata(qtbot,runtime_settings):
    snap=build_context(make_view(),make_turn(text='Hello'))
    other=build_context(make_view(epoch=2),make_turn(text='Hello'))
    class Service:
        def translate(self,*args,context): return TranslationResult('Xin chào',context=ContextOutcome(other.stamp))
        def close(self): pass
    worker=BlockTranslationWorker(service_factory=Service); results=[]
    worker.result_ready.connect(results.append)
    worker.replace_pending((BlockJob(1,0,'Hello',runtime_settings,1,1,context=snap),),{(1,0,1)},1); worker.start()
    try:
        qtbot.waitUntil(lambda:bool(results))
        assert results[0].context_stamp==snap.stamp
        assert results[0].result.context is None and results[0].result.context_degraded
    finally: worker.request_stop(); assert worker.wait(2000)
