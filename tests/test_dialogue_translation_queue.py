from threading import Event
from dataclasses import replace
import pytest
from core.blocks.models import BlockJob
from core.contracts import TranslationResult, EngineError


def test_one_inflight_and_latest_pending_per_track(qtbot,runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    entered,release=Event(),Event();calls=[];events=[]
    class Service:
        def translate(self,text,settings):
            calls.append(text);entered.set();release.wait(2)
            return TranslationResult(text)
        def close(self):pass
    w=BlockTranslationWorker(service_factory=Service)
    w.job_started.connect(lambda j:events.append(('start',j.request_key)))
    w.result_ready.connect(lambda r:events.append(('result',r.request_key)))
    j=BlockJob(1,1,'A',runtime_settings,1,1)
    w.replace_pending((j,),frozenset({(1,1,1)}),1);w.start()
    try:
        qtbot.waitUntil(entered.is_set)
        for v in (2,3):w.replace_pending((replace(j,source_text='A'*v,text_version=v),),frozenset({(1,1,1)}),1)
        assert calls==['A'] and w.pending_count==1
        release.set();qtbot.waitUntil(lambda:len(calls)==2)
        qtbot.waitUntil(lambda:len(events)==4)
        assert calls==['A','AAA']
        assert events==[('start',(1,1,1,1)),('result',(1,1,1,1)),('start',(1,1,1,3)),('result',(1,1,1,3))]
    finally:release.set();w.request_stop();assert w.wait(2000)


def test_three_changing_tracks_get_fair_service(qtbot,runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    entered,release=Event(),Event();calls=[]
    class Service:
        def translate(self,text,settings):
            calls.append(text);entered.set();release.wait(2);return TranslationResult(text)
        def close(self):pass
    w=BlockTranslationWorker(service_factory=Service)
    jobs=tuple(BlockJob(1,i,str(i),runtime_settings,1,1) for i in range(3))
    active=frozenset((1,i,1) for i in range(3))
    w.replace_pending(jobs,active,1);w.start()
    try:
        qtbot.waitUntil(entered.is_set)
        w.replace_pending((replace(jobs[0],source_text='0new',text_version=2),*jobs[1:]),active,1)
        release.set();qtbot.waitUntil(lambda:len(calls)==4)
        assert calls==['0','1','2','0new']
    finally:release.set();w.request_stop();assert w.wait(2000)


def test_ai_text_growth_does_not_reset_retry_budget(qtbot,runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    now=[0.];calls=[]
    settings=replace(runtime_settings,provider=replace(runtime_settings.provider,name='OpenAI'))
    class Service:
        def translate(self,text,settings):
            calls.append(text);return TranslationResult(error=EngineError('network','failed',True))
        def close(self):pass
    w=BlockTranslationWorker(clock=lambda:now[0],service_factory=Service)
    def submit(v):w.replace_pending((BlockJob(1,1,'x'*v,settings,1,v),),frozenset({(1,1,1)}),1)
    submit(1);w.start()
    try:
        for i,t in enumerate((0,1,3,7)):
            now[0]=t;submit(i+1);qtbot.waitUntil(lambda:len(calls)==i+1)
            qtbot.waitUntil(lambda:bool(w.drain_results()))
        now[0]=100;submit(5)
        assert w.pending_count==0 and len(calls)==4
    finally:w.request_stop();assert w.wait(2000)


def test_retry_survives_empty_pending_snapshot(qtbot,runtime_settings):
    from core.blocks.translation_worker import BlockTranslationWorker
    now=[0.];calls=[]
    settings=replace(runtime_settings,provider=replace(runtime_settings.provider,name='OpenAI'))
    class Service:
        def translate(self,*args):calls.append(1);return TranslationResult(error=EngineError('timeout','failed',True))
        def close(self):pass
    w=BlockTranslationWorker(clock=lambda:now[0],service_factory=Service)
    w.replace_pending((BlockJob(1,1,'A',settings,1,1),),frozenset({(1,1,1)}),1);w.start()
    try:
        qtbot.waitUntil(lambda:bool(w.drain_results()))
        w.replace_pending((),frozenset({(1,1,1)}),1)
        now[0]=1;qtbot.waitUntil(lambda:len(calls)==2)
    finally:w.request_stop();assert w.wait(2000)
