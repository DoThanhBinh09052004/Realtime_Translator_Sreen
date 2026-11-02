from dataclasses import replace
from threading import Event, Thread
import pytest
from PyQt5.QtCore import QThread, pyqtSignal, Qt


@pytest.fixture(params=[('subtitle','OpenAI'),('subtitle','Google Translate'),('blocks','OpenAI'),('blocks','Google Translate')])
def coordinator_case(request,qtbot,runtime_settings,dialogue_observation,span_factory,capture_geometry):
    from core.dialogue.coordinator import DialogueCoordinator
    mode,provider=request.param
    settings=replace(runtime_settings,overlay_mode=mode,provider=replace(runtime_settings.provider,name=provider))
    now=[0.];c=DialogueCoordinator(clock=lambda:now[0]);jobs=[];frames=[]
    c.jobs_changed.connect(lambda js,active,rev:jobs.extend(js))
    (c.subtitle_updated if mode=='subtitle' else c.blocks_updated).connect(frames.append)
    c.reset(settings,revision=1,session_id=1,running=True)
    def observe(text,t,scan):
        now[0]=t
        c.observe(dialogue_observation(text,settings=settings,revision=1,scan_id=scan,
                  captured_at_s=t,completed_at_s=t,spans=(span_factory(text),) if text else (),geometry=capture_geometry))
    observe('Hello',0,1);observe('Hello',.25,2)
    now[0]=.5;c.tick();job=jobs[-1]
    c.on_job_started(job)
    yield c,now,job,observe,frames,settings
    c.reset(settings,revision=2,session_id=2,running=False)


def text(frame):
    return frame.text if hasattr(frame,'text') else (frame.blocks[0].translated_text if frame.blocks else '')


def test_result_reaches_overlay_sink_while_next_ocr_is_held(coordinator_case,qtbot,dialogue_result):
    c,now,job,observe,frames,settings=coordinator_case
    release=Event();held=Thread(target=lambda:release.wait(2));held.start()
    class Sender(QThread):
        delivered=pyqtSignal(object)
        def run(self):self.delivered.emit(dialogue_result(job))
    sender=Sender();sender.delivered.connect(c.on_result,Qt.QueuedConnection)
    now[0]=.6;sender.start()
    try:
        qtbot.waitUntil(lambda:any(text(f)=='Xin chào' for f in frames),timeout=100)
        assert not release.is_set()
    finally:release.set();held.join();assert sender.wait(1000)


def test_late_scan_and_reset_cannot_rewind_or_revive(coordinator_case,dialogue_result):
    c,now,job,observe,frames,settings=coordinator_case
    c.on_result(dialogue_result(job));observe('Different',1,3);observe('Different',1.25,4)
    before=len(frames)
    observe('Hello',1.5,2)
    assert len(frames)==before
    c.reset(settings,revision=2,session_id=2,running=True)
    c.on_result(dialogue_result(job,'old'))
    assert not any(text(f)=='old' for f in frames)


def test_every_presented_frame_has_monotonic_sequence(coordinator_case,dialogue_result):
    c,now,job,observe,frames,settings=coordinator_case
    now[0]=.6;c.on_result(dialogue_result(job))
    observe('Hello world',.7,3)
    now[0]=1.2;c.tick()
    seq=[getattr(f,'render_sequence',getattr(f,'frame_id',0)) for f in frames]
    assert seq==sorted(set(seq)) and min(seq)>0


def test_read_and_expiry_deadlines_need_no_new_ocr(qtbot,runtime_settings,dialogue_observation,dialogue_result):
    from core.dialogue.coordinator import DialogueCoordinator
    now=[0.];c=DialogueCoordinator(clock=lambda:now[0]);frames=[];jobs=[]
    c.subtitle_updated.connect(frames.append);c.jobs_changed.connect(lambda js,*a:jobs.extend(js))
    c.reset(runtime_settings,revision=1,session_id=1,running=True)
    def obs(source,t,n):
        now[0]=t;c.observe(dialogue_observation(source,scan_id=n,captured_at_s=t,completed_at_s=t))
    try:
        obs('Hello',0,1);obs('Hello',.25,2);now[0]=.5;c.tick()
        j=jobs[-1];c.on_job_started(j);c.on_result(dialogue_result(j,'one'))
        obs('Hello world',.6,3);now[0]=1.1;c.tick()
        j=jobs[-1];c.on_job_started(j);c.on_result(dialogue_result(j,'two'))
        assert frames[-1].text=='one'
        now[0]=1.5;c.tick();assert frames[-1].text=='two'
        obs('',2,4);obs('',2.5,5)
        now[0]=5.499;c.tick();assert frames[-1].text=='two'
        now[0]=5.5;c.tick();assert frames[-1].text==''
    finally:c.reset(runtime_settings,revision=2,session_id=2,running=False)
