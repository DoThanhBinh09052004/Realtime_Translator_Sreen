from dataclasses import replace
import numpy as np
from core import config
from core.contracts import OcrResult
from core.worker import TranslationWorker


def test_static_thumbnail_still_refreshes_small_block_geometry(qtbot,monkeypatch,runtime_settings,capture_geometry,span_factory,dialogue_result):
    import core.worker as module
    now,calls=[0.],[]
    monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(module,'ocr_image',lambda *a,**k:calls.append(1) or OcrResult('Hello',spans=(span_factory(),)))
    w=TranslationWorker(config.State(),dict(left=100,top=100,width=800,height=600))
    settings=replace(runtime_settings,overlay_mode='blocks')
    w._is_running=True;rev=w.configure(settings);w._take_snapshot()
    img=np.zeros((600,800),dtype='uint8')
    try:
        for t in (0,.5):
            now[0]=t;w._process_dialogue_frame(img,settings,rev,capture_geometry);qtbot.wait(1)
        j,=w._coordinator.session.translation_jobs(now_s=.5)
        w._coordinator.on_job_started(j);w._coordinator.on_result(dialogue_result(j))
        now[0]=1.49;w._process_dialogue_frame(img,settings,rev,capture_geometry)
        assert len(calls)==2
        now[0]=1.5;w._process_dialogue_frame(img,settings,rev,capture_geometry)
        assert len(calls)==3
    finally:w.stop_worker()


def test_confirmed_missing_source_rejects_late_translation(qtbot,monkeypatch,runtime_settings,capture_geometry,span_factory,dialogue_result):
    import core.worker as module
    now,source=[0.],['Hello']
    monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(module,'ocr_image',lambda *a,**k:OcrResult(source[0],spans=(span_factory(),) if source[0] else ()))
    w=TranslationWorker(config.State(),dict(left=100,top=100,width=800,height=600))
    settings=replace(runtime_settings,overlay_mode='blocks')
    w._is_running=True;rev=w.configure(settings);w._take_snapshot()
    img=np.zeros((600,800),dtype='uint8');frames=[];w.blocks_updated.connect(frames.append)
    try:
        for t in (0,.5):
            now[0]=t;w._prev_frame_thumb=None;w._process_dialogue_frame(img,settings,rev,capture_geometry);qtbot.wait(1)
        j,=w._coordinator.session.translation_jobs(now_s=.5);w._coordinator.on_job_started(j)
        source[0]=''
        for t in (.75,1.):
            now[0]=t;w._prev_frame_thumb=None;w._process_dialogue_frame(img,settings,rev,capture_geometry);qtbot.wait(1)
        w._coordinator.on_result(dialogue_result(j,'old'))
        assert not frames[-1].blocks
        assert not w._coordinator.session.active_turns
    finally:w.stop_worker()
