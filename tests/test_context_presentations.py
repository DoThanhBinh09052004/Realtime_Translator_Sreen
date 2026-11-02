from dataclasses import replace
from core.dialogue.track import DialogueTrack
from core.blocks.models import BlockTranslationResult
from core.contracts import TranslationResult, OcrResult
from core.dialogue.models import DialogueObservation
from core.dialogue.context_models import ContextOutcome,SourceKey,ScopeSpec
from core.dialogue.coordinator import DialogueCoordinator

def deliver(track,settings,at,text):
    job=track.job(revision=1,settings=settings,now_s=at)
    track.mark_dispatched(job,now_s=at)
    track.apply_result(BlockTranslationResult(1,0,job.source_text,TranslationResult(text),job.turn_id,job.text_version),now_s=at)

def test_pending_translation_commits_once_when_selected(runtime_settings):
    t=DialogueTrack(0);t.observe('Hello',now_s=0);t.observe('Hello',now_s=.6)
    deliver(t,runtime_settings,.6,'Chào')
    assert len(t.drain_presentations())==1
    t.observe('Hello friend',now_s=.7);t.observe('Hello friend',now_s=1.3)
    deliver(t,runtime_settings,1.3,'Chào bạn')
    assert t.drain_presentations()==()
    t.advance(now_s=2.2)
    assert len(t.drain_presentations())==1
    assert t.drain_presentations()==()

def test_deferred_translation_does_not_commit_memory(runtime_settings):
    t=DialogueTrack(0);t.observe('Hello',now_s=0);t.observe('Hello',now_s=.6)
    job=t.job(revision=1,settings=runtime_settings,now_s=.6);t.mark_dispatched(job,now_s=.6)
    t.observe('Goodbye',now_s=.7)
    t.apply_result(BlockTranslationResult(1,0,'Hello',TranslationResult('Chào'),1,1),now_s=.8)
    assert t.drain_presentations()==()
    t.observe('Goodbye',now_s=.9)
    t.advance(now_s=2)
    assert t.drain_presentations()==()

def test_coordinator_builds_snapshot_and_commits_presentation(qtbot,runtime_settings):
    now=[0.];settings=replace(runtime_settings,context_enabled=True)
    c=DialogueCoordinator(clock=lambda:now[0]);jobs=[]
    c.jobs_changed.connect(lambda j,*args:jobs.extend(j))
    c.reset(settings,revision=1,session_id=1,running=True,memory_source=SourceKey('window',(1,)),memory_scopes=(ScopeSpec('legacy-subtitle'),))
    try:
        for i,at in enumerate((0.,.6)):
            now[0]=at;c.observe(DialogueObservation(1,i,at,at,settings,OcrResult('A: Hello'),None))
        job=jobs[-1];assert job.context is not None and job.context.history==()
        c.on_job_started(job)
        result=TranslationResult('Xin chào',context=ContextOutcome(job.context.stamp))
        c.on_result(BlockTranslationResult(1,0,job.source_text,result,job.turn_id,job.text_version,job.context.stamp))
        assert c.context_memory.view('legacy-subtitle',now_s=.6).styles[0].translated_text=='Xin chào'
        c.tick()
        assert len(c.context_memory.view('legacy-subtitle',now_s=.6).styles)==1
    finally:c._timer.stop()

def test_eight_region_contexts_and_receipts_remain_isolated(qtbot,runtime_settings,capture_geometry):
    from tests.test_capture_sessions import profile,context,observation
    now=[0.];settings=replace(runtime_settings,context_enabled=True)
    p=profile(8);ctx=context(capture_geometry);c=DialogueCoordinator(clock=lambda:now[0]);jobs=[]
    c.jobs_changed.connect(lambda j,*args:jobs.extend(j))
    c.reset(settings,revision=1,session_id=1,running=True,memory_source=SourceKey('desktop',('test',1)),memory_scopes=tuple(ScopeSpec(r.id) for r in p.regions))
    c.configure_capture(p,ctx)
    try:
        for i,at in enumerate((0.,.6)):
            now[0]=at;c.observe_capture(observation(p,ctx,settings,{i:f'Name{i}: line{i}' for i in range(8)},t=at,scan=i))
        by_scope={j.context.stamp.scope_id:j for j in jobs if j.context is not None}
        assert len(by_scope)==8
        for index,region in enumerate(p.regions):
            job=by_scope[region.id]
            assert job.context.current.source_text==f'Name{index}: line{index}'
            assert all(line.text==job.source_text for line in job.evidence.lines)
            c.on_job_started(job)
            c.on_result(BlockTranslationResult(1,job.block_id,job.source_text,TranslationResult(f'translated{index}',context=ContextOutcome(job.context.stamp)),job.turn_id,job.text_version,job.context.stamp))
        for index,region in enumerate(p.regions):
            assert c.context_memory.view(region.id,now_s=.6).styles[0].translated_text==f'translated{index}'
    finally:c._timer.stop()

def test_rejected_capture_batch_cannot_change_scene_activity(qtbot,runtime_settings,capture_geometry):
    from tests.test_capture_sessions import profile,context,observation
    now=[200.];settings=replace(runtime_settings,context_enabled=True);p=profile(1);ctx=context(capture_geometry)
    c=DialogueCoordinator(clock=lambda:now[0])
    c.reset(settings,revision=1,session_id=1,running=True,memory_source=SourceKey('desktop',('test',1)),memory_scopes=(ScopeSpec(p.regions[0].id),))
    c.configure_capture(p,ctx)
    try:
        scope=c.context_memory._scopes[p.regions[0].id]
        epoch=scope.epoch
        # Same ROI ID from a previous runtime must not rewind current activity.
        stale=replace(observation(p,ctx,settings,{0:'stale'},t=0.,scan=1),revision=0)
        c.observe_capture(stale)
        assert scope.seen==200. and scope.epoch==epoch
    finally:c._timer.stop()
