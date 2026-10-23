from dataclasses import replace
from threading import Event
import time
import numpy as np
from core import config
from core.contracts import OcrResult, TranslationResult, EngineError
from core.worker import TranslationWorker


def test_google_pause_survives_reconfiguration_and_preserved_stop(qtbot,monkeypatch,runtime_settings,capture_geometry):
    import core.worker as module
    class Capture:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def grab(self,r): return np.zeros((600,800,4),dtype='uint8')
    monkeypatch.setattr(module.mss,'mss',Capture)
    monkeypatch.setattr(module,'ocr_image',lambda *a,**kw:OcrResult())
    monkeypatch.setattr(module,'compact_memory',lambda:None)
    w=TranslationWorker(config.State(),dict(left=100,top=100,width=800,height=600))
    settings=replace(runtime_settings,interval_ms=100,provider=replace(runtime_settings.provider,name='Google Translate',api_key='',model_id=''))
    w.configure(settings); w.set_capture_geometry(capture_geometry); w.start_worker()
    session=w.translation_session_id
    try:
        g=w._google_recovery
        g.record_result(TranslationResult(error=EngineError('invalid_response','fail',False)),generation=g.snapshot(now_s=0).generation,now_s=0)
        w.set_region(dict(left=100,top=100,width=800,height=600))
        for candidate in [replace(settings,source_lang='Japanese'),replace(settings,overlay_mode='blocks'),
                          replace(settings,overlay_mode='blocks',provider=runtime_settings.provider),settings]:
            w.configure(candidate)
            qtbot.waitUntil(lambda:w.is_running() and w.isRunning())
            assert g.snapshot(now_s=time.monotonic()).phase=='paused'
            assert w.translation_session_id==session
        w.stop_worker(preserve_translation_session=True)
        w.start_worker(preserve_translation_session=True)
        qtbot.waitUntil(lambda:w.is_running() and w.isRunning())
        assert g.snapshot(now_s=time.monotonic()).phase=='paused'
        assert w.translation_session_id==session
        w.stop_worker(); assert w.wait(2000) and w._block_translator.wait(2000)
        w.start_worker()
        assert g.snapshot(now_s=time.monotonic()).phase=='ready'
        assert w.translation_session_id>session
    finally:
        w.stop_worker(); assert w.wait(2000) and w._block_translator.wait(2000)
