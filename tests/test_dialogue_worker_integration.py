from dataclasses import replace
from threading import Event
import numpy as np
import pytest
from core import config
from core.contracts import TranslationResult, OcrResult, SubtitleFrame
from core.worker import TranslationWorker


@pytest.mark.parametrize('mode',['subtitle','blocks'])
@pytest.mark.parametrize('provider',['Google Translate','OpenAI','Google Gemini','DeepSeek','Custom API'])
def test_all_provider_mode_combinations_keep_capture_running(qtbot,monkeypatch,runtime_settings,capture_geometry,span_factory,mode,provider):
    import core.worker as module
    entered,release=Event(),Event();calls=[];captures=[]
    class Service:
        def __init__(self,**kwargs):pass
        def translate(self,text,settings):
            calls.append(text);entered.set();release.wait(3);return TranslationResult('Xin chào')
        def close(self):pass
    class Capture:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def grab(self,region):captures.append(1);return np.zeros((80,200,4),dtype='uint8')
    monkeypatch.setattr(module,'TranslationService',Service)
    monkeypatch.setattr(module.mss,'mss',Capture)
    monkeypatch.setattr(module,'ocr_image',lambda *a,**k:OcrResult('Hello',spans=(span_factory(),)))
    monkeypatch.setattr(module,'compact_memory',lambda:None)
    w=TranslationWorker(config.State(),dict(left=100,top=100,width=800,height=600))
    settings=replace(runtime_settings,overlay_mode=mode,interval_ms=100,provider=replace(runtime_settings.provider,name=provider))
    w.configure(settings);w.set_capture_geometry(capture_geometry);w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set,timeout=2000);count=len(captures)
        qtbot.waitUntil(lambda:len(captures)>=count+2,timeout=1000)
        assert calls==['Hello']
    finally:
        release.set();w.stop_worker();assert w.wait(2000);assert w._block_translator.wait(2000)


@pytest.mark.parametrize('mode',['subtitle','blocks'])
@pytest.mark.parametrize('provider',['Google Translate','OpenAI'])
def test_complete_path_result_does_not_wait_for_capture(qtbot,monkeypatch,runtime_settings,capture_geometry,span_factory,mode,provider):
    import core.worker as module
    from ui.overlay import Overlay
    import ui.block_overlay as block_module
    ocr_held,release_ocr,entered,release_api=Event(),Event(),Event(),Event();scans=[]
    class Service:
        def __init__(self,**kwargs):pass
        def translate(self,*a):entered.set();release_api.wait(3);return TranslationResult('Xin chào')
        def close(self):pass
    class Capture:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def grab(self,*a):return np.zeros((80,200,4),dtype='uint8')
    def ocr(*a,**k):
        scans.append(1)
        if len(scans)==3:ocr_held.set();release_ocr.wait(3)
        return OcrResult('Hello',spans=(span_factory(),))
    monkeypatch.setattr(module,'TranslationService',Service);monkeypatch.setattr(module.mss,'mss',Capture)
    monkeypatch.setattr(module,'ocr_image',ocr);monkeypatch.setattr(module,'compact_memory',lambda:None)
    monkeypatch.setattr(block_module,'set_capture_excluded',lambda *a:None)
    w=TranslationWorker(config.State(),dict(left=100,top=100,width=800,height=600))
    o=Overlay();qtbot.addWidget(o)
    w.revision_changed.connect(lambda r:o.set_mode(mode,r))
    w.subtitle_updated.connect(o.update_subtitle);w.blocks_updated.connect(o.update_blocks)
    w.configure(replace(runtime_settings,overlay_mode=mode,interval_ms=100,provider=replace(runtime_settings.provider,name=provider)))
    w.set_capture_geometry(capture_geometry);w.start_worker()
    try:
        qtbot.waitUntil(ocr_held.is_set,timeout=1500);qtbot.waitUntil(entered.is_set,timeout=1500)
        release_api.set()
        qtbot.waitUntil(lambda:o.text()=='Xin chào' if mode=='subtitle' else bool(o.block_overlay.placed_blocks),timeout=100)
        assert not release_ocr.is_set()
    finally:
        release_api.set();release_ocr.set();w.stop_worker();assert w.wait(2000);assert w._block_translator.wait(2000)


def test_old_legacy_refresh_cannot_revive_managed_subtitle(qtbot):
    from ui.overlay import Overlay
    o=Overlay();qtbot.addWidget(o);o.set_mode('subtitle',2)
    o.update_subtitle(SubtitleFrame(2,1,'source','new',1))
    assert not o.hide_timer.isActive()
    o.update_subtitle(SubtitleFrame(2,99,'old','old'))
    assert o.text()=='new'
    o.update_subtitle(SubtitleFrame(2,1,'','',2));o.refresh()
    assert not o.text() and not o.isVisible() and not o.hide_timer.isActive()


@pytest.mark.parametrize('change',['provider','model','key','source','target','region','mode','stop'])
def test_hard_invalidation_clears_held_presentation(qtbot,monkeypatch,runtime_settings,dialogue_observation,dialogue_result,change):
    import core.worker as module
    from ui.overlay import Overlay
    now=[0.];monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    w=TranslationWorker(config.State(),config.DEFAULT_REGION)
    o=Overlay();qtbot.addWidget(o)
    w.revision_changed.connect(lambda r:o.set_mode(w._settings.overlay_mode,r))
    w.subtitle_updated.connect(o.update_subtitle)
    w._is_running=True;w.configure(runtime_settings)
    c=w._coordinator;jobs=[];c.jobs_changed.connect(lambda js,*args:jobs.extend(js))
    def observe(source,t,n):
        now[0]=t;c.observe(dialogue_observation(source,revision=w.revision,scan_id=n,captured_at_s=t,completed_at_s=t))
    try:
        observe('Hello',0,1);observe('Hello',.25,2);now[0]=.5;c.tick()
        j=jobs[-1];c.on_job_started(j);c.on_result(dialogue_result(j,'one'))
        observe('Hello world',.6,3);now[0]=1.1;c.tick()
        j=jobs[-1];c.on_job_started(j);c.on_result(dialogue_result(j,'two'))
        assert o.text()=='one'
        if change=='stop':w.stop_worker()
        elif change=='region':w.set_region(dict(left=1,top=1,width=100,height=40))
        else:
            settings=runtime_settings
            if change in ('provider','model','key'):
                fields={'provider':{'name':'OpenAI'},'model':{'model_id':'other'},'key':{'api_key':'other'}}[change]
                settings=replace(settings,provider=replace(settings.provider,**fields))
            elif change=='mode':settings=replace(settings,overlay_mode='blocks')
            elif change=='source':settings=replace(settings,source_lang='Japanese')
            else:settings=replace(settings,target_lang='English')
            w.configure(settings)
        now[0]=2;c.on_result(dialogue_result(j,'late'));c.tick()
        assert not o.text() and not o.isVisible()
    finally:w.stop_worker()
