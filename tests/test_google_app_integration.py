from dataclasses import replace
from types import SimpleNamespace
import time
import httpx
import json
from urllib.parse import parse_qs
import numpy as np
import pytest
from core import config
from core.contracts import OcrResult
from core.worker import TranslationWorker


@pytest.mark.parametrize('mode',['subtitle','blocks'])
def test_google_pause_retry_uses_current_capture_and_never_self_heals(qtbot,monkeypatch,capture_geometry,span_factory,mode,google_batch_response):
    import core.worker as module
    import ui.block_overlay as block_module
    from engines.google_translate import GoogleTranslateClient
    from engines.translator import TranslationService
    from ui.overlay import Overlay
    from ui.controller import ControllerWindow
    now, source, fail=[0.],['A'],[True]
    requests, captures=[],[]
    def respond(request):
        if request.method == 'POST':
            rpc = json.loads(parse_qs(request.content.decode())['f.req'][0])
            original = json.loads(rpc[0][0][1])[0][0]
        else:
            original = request.url.params['q']
        requests.append(original)
        if fail[0]: return httpx.Response(503)
        translated = 'Bản dịch ' + original
        if request.method == 'POST':
            return httpx.Response(200, text=google_batch_response(translated))
        if request.url.host == 'clients5.google.com':
            return httpx.Response(200, json=[translated])
        return httpx.Response(200, json=[[[translated]]])
    def service():
        return TranslationService(google_factory=lambda:GoogleTranslateClient(client_factory=lambda:httpx.Client(transport=httpx.MockTransport(respond))))
    class Capture:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def grab(self,r):
            captures.append(1)
            return np.full((600,800,4),len(captures)*7%255,dtype='uint8')
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:now[0],sleep=time.sleep))
    monkeypatch.setattr(module,'TranslationService',service)
    monkeypatch.setattr(module.mss,'mss',Capture)
    monkeypatch.setattr(module,'compact_memory',lambda:None)
    monkeypatch.setattr(module,'ocr_image',lambda *a,**k:OcrResult(source[0],spans=(span_factory(source[0]),)))
    monkeypatch.setattr(block_module,'set_capture_excluded',lambda *a:None)
    state=config.State()
    w=TranslationWorker(state,dict(left=100,top=100,width=800,height=600))
    overlay=Overlay(); qtbot.addWidget(overlay)
    window=ControllerWindow(w,state,lambda:None,lambda:w.stop_worker(),overlay=overlay); qtbot.addWidget(window)
    w.revision_changed.connect(lambda rev:overlay.set_mode(mode,rev))
    w.subtitle_updated.connect(overlay.update_subtitle); w.blocks_updated.connect(overlay.update_blocks)
    w.translation_status_updated.connect(window.show_translation_status)
    w.configure(replace(config.load_runtime_settings(state,100),overlay_mode=mode))
    w.set_capture_geometry(capture_geometry); w.start_worker()
    try:
        for index,t in enumerate((0,1,3,7)):
            now[0]=t
            qtbot.waitUntil(lambda:len(requests)==index+1)
            qtbot.waitUntil(lambda:w._google_recovery.snapshot(now_s=t).phase!='ready')
        qtbot.waitUntil(lambda:not window.console_page.retry_translation_btn.isHidden())
        now[0]=10000; source[0]='B'
        count=len(captures)
        qtbot.waitUntil(lambda:len(captures)>=count+3)
        assert requests==['A']*4
        fail[0]=False
        assert window.retry_translation()
        qtbot.waitUntil(lambda:len(requests)==5)
        assert requests[-1]=='B'
        if mode=='subtitle':
            qtbot.waitUntil(lambda:overlay.text()=='Bản dịch B')
        else:
            qtbot.waitUntil(lambda:bool(overlay.block_overlay.placed_blocks))
            assert overlay.block_overlay.placed_blocks[0].text=='Bản dịch B'
    finally:
        w.stop_worker(); assert w.wait(2000) and w._block_translator.wait(2000)
