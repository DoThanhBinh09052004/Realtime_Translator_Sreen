from dataclasses import replace
from threading import Event
import time
import numpy as np
import pytest
from core import config
from core.contracts import OcrResult, TranslationResult, EngineError
from core.worker import TranslationWorker


@pytest.mark.parametrize('change', ['provider', 'mode'])
def test_configure_after_stop_does_not_restart_draining_google(qtbot, monkeypatch, runtime_settings, change):
    import core.worker as module
    entered, release = Event(), Event()
    shutdown = []
    class Service:
        def translate(self, *args):
            entered.set()
            assert release.wait(4)
            return TranslationResult('old')
        def close(self): pass
    class Capture:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, region): return np.zeros((600, 800, 4), dtype='uint8')
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module.mss, 'mss', Capture)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), config.DEFAULT_REGION)
    google = replace(runtime_settings, interval_ms=100,
                     provider=replace(runtime_settings.provider, name='Google Translate', api_key='', model_id=''))
    w.configure(google)
    w.shutdown_finished.connect(lambda: shutdown.append(True))
    w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        w.stop_worker()
        assert not w.is_running() and w._block_translator.isRunning()
        settings = (replace(google, provider=runtime_settings.provider) if change == 'provider'
                    else replace(google, overlay_mode='blocks'))
        w.configure(settings)
        assert not w._restart_pending
        release.set()
        qtbot.waitUntil(lambda: bool(shutdown))
        assert not w.is_running() and not w.isRunning() and not w._block_translator.isRunning()
    finally:
        release.set()
        w.stop_worker()
        assert w.wait(2000) and w._block_translator.wait(2000)


def test_start_during_internal_restart_preserves_google_session(qtbot, monkeypatch, runtime_settings, capture_geometry):
    import core.worker as module
    entered, release = Event(), Event()
    class Service:
        def translate(self, *args):
            entered.set()
            assert release.wait(4)
            return TranslationResult(error=EngineError('invalid_response', 'fail', False))
        def close(self): pass
    class Capture:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, region): return np.zeros((600, 800, 4), dtype='uint8')
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module.mss, 'mss', Capture)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), dict(left=100, top=100, width=800, height=600))
    google = replace(runtime_settings, interval_ms=100,
                     provider=replace(runtime_settings.provider, name='Google Translate', api_key='', model_id=''))
    w.configure(google)
    w.set_capture_geometry(capture_geometry)
    w.start_worker()
    session = w.translation_session_id
    translator = w._block_translator
    try:
        qtbot.waitUntil(entered.is_set)
        w.configure(replace(google, overlay_mode='blocks'))
        assert w._restart_pending and w._restart_preserve_session
        w.start_worker()  # A redundant Start must retain the internal restart intent.
        assert w._restart_preserve_session
        release.set()
        qtbot.waitUntil(lambda: w.is_running() and w.isRunning() and w._block_translator is not translator)
        assert w.translation_session_id == session
        assert w._google_recovery.snapshot(now_s=time.monotonic()).phase == 'paused'
    finally:
        release.set()
        w.stop_worker()
        assert w.wait(2000) and w._block_translator.wait(2000)


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
