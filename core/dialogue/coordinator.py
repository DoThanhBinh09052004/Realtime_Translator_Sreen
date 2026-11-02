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
from core.capture.sessions import RegionDialogueSession
from core.capture.models import CaptureObservation, RegionOcrObservation
from core.dialogue.evidence import evidence_from_ocr
from core.dialogue.context_models import ContextStatus
from core.dialogue.context_builder import context_supported,context_available,build_context
from core.dialogue.context_memory import DialogueMemory


class DialogueCoordinator(QObject):
    jobs_changed = pyqtSignal(object,object,int)
    scan_policy_changed = pyqtSignal(int,bool)
    capture_scan_policy_changed = pyqtSignal(int,object)
    subtitle_updated = pyqtSignal(object)
    blocks_updated = pyqtSignal(object)
    error_occurred = pyqtSignal(object)
    diagnostic_event = pyqtSignal(object)
    context_status_changed = pyqtSignal(object)

    def __init__(self, *, clock=time.monotonic, policy=DEFAULT_DIALOGUE_POLICY, parent=None):
        super().__init__(parent)
        self._clock,self.policy=clock,policy
        self._running=False
        self.context_memory=DialogueMemory()
        self._snapshots={}
        self._source_turns={}
        self._context_status=None
        self._timer=QTimer(self)
        self._timer.setInterval(policy.tick_ms)
        self._timer.timeout.connect(self.tick)

    def reset(self, settings, *, revision, session_id, running,memory_source=None,memory_scopes=()):
        self._timer.stop()
        self.settings,self.revision,self.session_id=settings,revision,session_id
        self._running=running
        self._scan_id=-1
        self._completed_at=float('-inf')
        self._sequence=0
        self._capture=False
        self._snapshots.clear();self._source_turns.clear()
        provider=settings.provider
        settings_key=(settings.source_lang,settings.target_lang,provider.name,provider.model_id,provider.base_url or '',settings.overlay_mode,settings.context_enabled)
        self.context_memory.reconcile(memory_source,settings_key,memory_scopes,now_s=self._clock())
        self._set_context_status('active' if context_supported(settings) else 'unsupported' if settings.context_enabled else 'off')
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
        if (not self._running or self._capture or observation.revision!=self.revision
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
        else:self.session.observe(observation.ocr.text,now_s=observation.completed_at_s,evidence=evidence_from_ocr(observation.ocr),captured_at_s=observation.captured_at_s)
        if observation.ocr.text and 'legacy-subtitle' in self.context_memory._scopes:
            self.context_memory.mark_seen('legacy-subtitle',now_s=observation.completed_at_s)
        self.tick()

    @pyqtSlot(object,object)
    def configure_capture(self, profile, context):
        if self._capture:
            if profile!=self.session.profile:
                raise ValueError('Capture profile changes require a new revision')
            self.update_capture_geometry(context)
            return
        session=RegionDialogueSession(profile,policy=self.policy)
        session.reset(self.revision,self.settings)
        if not session.set_geometry(context):return
        self.session=session
        self._capture=True
        self._last_frame=self._last_jobs=self._last_scan_policy=None
        self.tick()

    @pyqtSlot(object)
    def observe_capture(self, batch):
        if not self._running or not self._capture or not isinstance(batch,CaptureObservation):return
        now=self._clock()
        # Rejected ROI timestamps must not poison other ROI observations.
        regions=tuple(item for item in batch.regions
                      if isinstance(item,RegionOcrObservation)
                      and type(item.completed_at_s) in (int,float)
                      and math.isfinite(item.completed_at_s) and item.completed_at_s <= now+.001)
        accepted=self.session.observe(replace(batch,regions=regions)) or ()
        for item in accepted:
            if item.ocr.error is None and item.ocr.text and item.region_id in self.context_memory._scopes:
                self.context_memory.mark_seen(item.region_id,now_s=item.completed_at_s)
        self.tick()

    @pyqtSlot(object)
    def update_capture_geometry(self, context):
        if not self._capture:return
        self.session.set_geometry(context)
        self.tick()

    @pyqtSlot(object)
    def on_job_started(self, job):
        if not self._running or job.revision!=self.revision:return
        self.session.mark_dispatched(job,now_s=self._clock())
        if job.context is not None:
            self._snapshots[job.request_key]=job.context
            while len(self._snapshots)>33:self._snapshots.pop(next(iter(self._snapshots)))
        self._trace('started',job)
        self.tick()

    @pyqtSlot(object)
    def on_result(self, result):
        if not self._running or result.revision!=self.revision:
            self._trace('dropped',result)
            return
        self._trace('received',result)
        snapshot=self._snapshots.get(result.request_key)
        if result.context_stamp is not None:
            if snapshot is None or result.context_stamp!=snapshot.stamp:
                self._trace('dropped',result);return
            scope=self.context_memory._scopes.get(snapshot.stamp.scope_id)
            if scope is None or scope.epoch!=snapshot.stamp.memory_epoch:
                self._trace('dropped',result);return
        if result.result.context_degraded:self._set_context_status('text_fallback')
        accepted=self.session.apply_result(result,now_s=self._clock())
        self._trace('accepted' if accepted else 'dropped',result)
        if accepted and result.result.error is not None:self.error_occurred.emit(result.result.error)
        self.tick()

    def _trace(self,kind,item=None,**data):
        key=item.request_key if item is not None else data.get('request_key')
        snapshot=getattr(item,'context',None)
        if not hasattr(snapshot,'current'):snapshot=self._snapshots.get(key)
        if snapshot is not None:
            data.setdefault('source_id',snapshot.current.source_id)
            data.setdefault('stamp',dict(memory_epoch=snapshot.stamp.memory_epoch,scope_id=snapshot.stamp.scope_id,snapshot_digest=snapshot.stamp.snapshot_digest))
        event=dict(kind=kind,t=self._clock(),revision=self.revision,request_key=key)
        event.update(data)
        self.diagnostic_event.emit(event)

    def _set_context_status(self,phase):
        status=ContextStatus(phase,self.revision)
        if status!=self._context_status:
            self._context_status=status;self.context_status_changed.emit(status)

    def clear_context(self):
        self.context_memory.reset_all(now_s=self._clock())
        self._snapshots.clear();self._source_turns.clear()

    def _context_jobs(self,jobs,now):
        if not context_supported(self.settings):return jobs
        output=[]
        for job in jobs:
            scope=self.session.scope_for_job(job) if self._capture else 'legacy-subtitle'
            source=self._source_turns.get(job.request_key)
            if scope in self.context_memory._scopes and source is not None:
                snapshot=build_context(self.context_memory.view(scope,now_s=now),source)
                job=replace(job,context=snapshot)
            output.append(job)
        return tuple(output)

    @pyqtSlot()
    def tick(self):
        if not self._running:return
        now=self._clock()
        self.session.tick(now_s=now)
        if self.settings.overlay_mode=='subtitle':
            stable=self.session.drain_stable_turns()
            if not self._capture:stable=tuple(('legacy-subtitle',turn) for turn in stable)
            for scope,turn in stable:
                key=(turn.revision,turn.track_id,turn.turn_id,turn.text_version)
                if context_supported(self.settings) and scope in self.context_memory._scopes:
                    current=self.context_memory.observe(scope,turn)
                    self._source_turns[key]=current
                    self._trace('stable',request_key=key,source_id=current.source_id,scope_id=scope,captured_at_s=current.captured_at_s)
                else:self._trace('stable',request_key=key,scope_id=scope,captured_at_s=turn.captured_at_s)
            active=self.session.active_turns
            self._source_turns={k:v for k,v in self._source_turns.items() if k[:3] in active}
            while len(self._source_turns)>32:self._source_turns.pop(next(iter(self._source_turns)))
            receipts=self.session.drain_presentations()
            if not self._capture:receipts=tuple(('legacy-subtitle',receipt) for receipt in receipts)
            for scope,receipt in receipts:
                snapshot=self._snapshots.pop(receipt.request_key,None)
                if snapshot is not None and snapshot.stamp.scope_id==scope:
                    if self.context_memory.commit(receipt,snapshot,now_s=now):
                        relations=self.context_memory.view(scope,now_s=now).relations
                        self._trace('selected',receipt,source_id=snapshot.current.source_id,scope_id=scope,
                                    stamp=dict(memory_epoch=snapshot.stamp.memory_epoch,scope_id=scope,snapshot_digest=snapshot.stamp.snapshot_digest),
                                    candidate_relations=sum(r.status=='candidate' for r in relations),supported_relations=sum(r.status=='supported' for r in relations),conflicted_relations=sum(r.status=='conflicted' for r in relations))
                elif not context_supported(self.settings):self._trace('selected',receipt,scope_id=scope)
            self._snapshots={k:v for k,v in self._snapshots.items() if k[:3] in active}
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
        state=(self._context_jobs(self.session.translation_jobs(now_s=now),now),self.session.active_turns,self.revision)
        if state!=self._last_jobs:
            self._last_jobs=state
            for job in state[0]:self._trace('queued',job)
            self.jobs_changed.emit(*state)
        scan=(self.revision,self.session.needs_scan_regions if self._capture else bool(self.session.needs_scan))
        if scan!=self._last_scan_policy:
            self._last_scan_policy=scan
            if self._capture:self.capture_scan_policy_changed.emit(*scan)
            else:self.scan_policy_changed.emit(*scan)
        for error in self.session.drain_errors():self.error_occurred.emit(error)
