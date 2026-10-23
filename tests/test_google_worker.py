from dataclasses import replace
from threading import Event, get_ident
import numpy as np
import pytest
from core import config
from core.contracts import TranslationResult, EngineError
from core.worker import TranslationWorker


@pytest.mark.parametrize('mode',['subtitle','blocks'])
def test_google_capture_continues_while_http_is_held(qtbot,monkeypatch,runtime_settings,capture_geometry,mode):
    import core.worker as module
    entered, release=Event(),Event()
    calls, captures, threads=[],[],[]
    class Service:
        def translate(self,text,settings):
            calls.append(text); threads.append(get_ident()); entered.set(); release.wait(4)
            return TranslationResult('Xin chào')
        def close(self): pass
    class Capture:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def grab(self,r):
            captures.append(get_ident())
            return np.full((600,800,4),100,dtype='uint8')
    monkeypatch.setattr(module,'TranslationService',Service)
    monkeypatch.setattr(module.mss,'mss',Capture)
    monkeypatch.setattr(module,'compact_memory',lambda:None)
    w=TranslationWorker(config.State(),dict(left=100,top=100,width=800,height=600))
    settings=replace(runtime_settings,overlay_mode=mode,interval_ms=100,provider=replace(runtime_settings.provider,name='Google Translate',api_key='',model_id=''))
    w.configure(settings); w.set_capture_geometry(capture_geometry)
    frames=[]
    (w.subtitle_updated if mode=='subtitle' else w.blocks_updated).connect(frames.append)
    w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        qtbot.waitUntil(lambda:len(captures)>=3)
        assert len(calls)==1 and threads[0] != captures[0] and threads[0] != get_ident()
        release.set()
        qtbot.waitUntil(lambda:any(getattr(f,'text','') or getattr(f,'blocks',()) for f in frames))
    finally:
        release.set(); w.stop_worker()
        assert w.wait(2000) and w._block_translator.wait(2000)


def test_manual_retry_observes_new_capture_before_submitting(monkeypatch,runtime_settings):
    import core.worker as module
    from core.contracts import OcrResult
    w=TranslationWorker(config.State(),config.DEFAULT_REGION)
    settings=replace(runtime_settings,provider=replace(runtime_settings.provider,name='Google Translate',api_key='',model_id=''))
    w.configure(settings); w._is_running=True; w._take_snapshot()
    g=w._google_recovery; generation=g.snapshot(now_s=0).generation
    g.record_result(TranslationResult(error=EngineError('invalid_response','bad',False)),generation=generation,now_s=0)
    assert w.retry_translation()
    assert not w.retry_translation()
    monkeypatch.setattr(module,'ocr_image',lambda *a,**k:OcrResult('Current scene'))
    img=np.zeros((40,100),dtype='uint8')
    w._take_snapshot()
    w._process_google_subtitle_frame(img,settings,w.revision)
    w._process_google_subtitle_frame(img,settings,w.revision)
    assert [j.source_text for j in w._google_subtitle.translation_jobs()]==['Current scene']


def test_ai_also_publishes_revision_bound_subtitle_for_safe_switching(monkeypatch,runtime_settings):
    import core.worker as module
    from core.contracts import OcrResult
    monkeypatch.setattr(module,'ocr_image',lambda *a,**kw:OcrResult('Hello'))
    w=TranslationWorker(config.State(),config.DEFAULT_REGION)
    rev=w.configure(runtime_settings); w._is_running=True
    frames=[]; w.subtitle_updated.connect(frames.append)
    class Service:
        def translate(self,*a): return TranslationResult('Xin chào')
    img=np.zeros((40,100),dtype='uint8')
    w._process_frame(img,runtime_settings,rev,Service())
    w._process_frame(img,runtime_settings,rev,Service())
    assert frames[-1].revision==rev and frames[-1].text=='Xin chào'
