"""GUI-owned dialogue state; OCR and SDK work never run on this event loop."""
from dataclasses import replace
import math
import time
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from core.blocks.grouping import group_spans
from core.blocks.session import BlockSession
from core.contracts import EngineError
from core.dialogue.policy import DEFAULT_DIALOGUE_POLICY
from core.dialogue.subtitle_session import SubtitleDialogueSession


class DialogueCoordinator(QObject):
    jobs_changed = pyqtSignal(object,object,int)
    scan_policy_changed = pyqtSignal(int,bool)
    subtitle_updated = pyqtSignal(object)
    blocks_updated = pyqtSignal(object)
    error_occurred = pyqtSignal(object)
    diagnostic_event = pyqtSignal(object)

    def __init__(self, *, clock=time.monotonic, policy=DEFAULT_DIALOGUE_POLICY, parent=None):
        super().__init__(parent)
        self._clock,self.policy=clock,policy
        self._running=False
        self._timer=QTimer(self)
        self._timer.setInterval(policy.tick_ms)
        self._timer.timeout.connect(self.tick)

    def reset(self, settings, *, revision, session_id, running):
        self._timer.stop()
        self.settings,self.revision,self.session_id=settings,revision,session_id
        self._running=running
        self._scan_id=-1
        self._completed_at=float('-inf')
        self._sequence=0
        self._last_frame=self._last_jobs=self._last_scan_policy=None
        if settings.overlay_mode=='blocks':
            self.session=BlockSession(policy=self.policy)
        else:
            self.session=SubtitleDialogueSession(policy=self.policy)
            self.session.reset(revision,settings)
        self.jobs_changed.emit((),frozenset(),revision)
        if running:
            self._timer.start()
            self.tick()

    @pyqtSlot(object)
    def observe(self, observation):
        if (not self._running or observation.revision!=self.revision
                or observation.settings!=self.settings or observation.scan_id<=self._scan_id
                or not math.isfinite(observation.completed_at_s)
                or observation.completed_at_s<self._completed_at
                or observation.captured_at_s>observation.completed_at_s):return
        self._scan_id,self._completed_at=observation.scan_id,observation.completed_at_s
        if observation.ocr.error is not None:
            self.error_occurred.emit(observation.ocr.error)
            self.tick()
            return
        if self.settings.overlay_mode=='blocks':
            if observation.geometry is None:
                self.error_occurred.emit(EngineError('capture_geometry','Không có hình học vùng OCR hợp lệ.',False))
                return
            self.session.observe(group_spans(observation.ocr.spans,observation.geometry.image_size_px),
                                 settings=self.settings,revision=self.revision,frame_id=observation.scan_id,
                                 geometry=observation.geometry,now_s=observation.completed_at_s)
        else:self.session.observe(observation.ocr.text,now_s=observation.completed_at_s)
        self.tick()

    @pyqtSlot(object)
    def on_job_started(self, job):
        if not self._running or job.revision!=self.revision:return
        self.session.mark_dispatched(job,now_s=self._clock())
        self._trace('started',job)
        self.tick()

    @pyqtSlot(object)
    def on_result(self, result):
        if not self._running or result.revision!=self.revision:
            self._trace('dropped',result)
            return
        self._trace('received',result)
        accepted=self.session.apply_result(result,now_s=self._clock())
        self._trace('accepted' if accepted else 'dropped',result)
        if accepted and result.result.error is not None:self.error_occurred.emit(result.result.error)
        self.tick()

    def _trace(self,kind,item=None,**data):
        self.diagnostic_event.emit(dict(kind=kind,t=self._clock(),revision=self.revision,
                                       request_key=item.request_key if item is not None else None,**data))

    @pyqtSlot()
    def tick(self):
        if not self._running:return
        now=self._clock()
        self.session.tick(now_s=now)
        frame=self.session.current_frame()
        if frame is not None:
            signature=replace(frame,frame_id=0) if self.settings.overlay_mode=='blocks' else frame
            if signature!=self._last_frame:
                self._last_frame=signature
                self._sequence+=1
                if self.settings.overlay_mode=='blocks':
                    frame=replace(frame,frame_id=self._sequence)
                    self.blocks_updated.emit(frame)
                    count=sum(len(b.translated_text) for b in frame.blocks)
                else:
                    frame=replace(frame,render_sequence=self._sequence)
                    self.subtitle_updated.emit(frame)
                    count=len(frame.text)
                self._trace('shown' if count else 'cleared',characters=count,sequence=self._sequence)
        state=(self.session.translation_jobs(now_s=now),self.session.active_turns,self.revision)
        if state!=self._last_jobs:
            self._last_jobs=state
            self.jobs_changed.emit(*state)
        scan=(self.revision,bool(self.session.needs_scan))
        if scan!=self._last_scan_policy:
            self._last_scan_policy=scan
            self.scan_policy_changed.emit(*scan)
        for error in self.session.drain_errors():self.error_occurred.emit(error)
