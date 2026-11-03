import time
import mss
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QMutexLocker, Qt

from engines.ocr import ocr_image, release_ocr_engine
from engines.translator import TranslationService
from core.config import load_runtime_settings
from core.ocr.reader import read_ocr, resolve_ocr_language
from core.runtime.state import WorkerRuntimeState, runtime_field
from core.runtime.lifecycle import WorkerLifecycle
from core.runtime.output import TranslationOutputPolicy
from core.runtime.memory import compact_memory
from core.runtime.runner import CaptureOcrRunner, RunnerDependencies, RunnerPorts, mask_overlay
from core.contracts import EngineError, RuntimeSettings
from core.ocr.frame_processor import FrameOcrProcessor
from core.blocks.translation_worker import BlockTranslationWorker
from core.translation.google_recovery import GoogleRecoveryGate
from core.dialogue.coordinator import DialogueCoordinator
from core.capture.profile import serialize_capture_profile
from core.capture.source import create_capture_source
from core.capture.scan import RegionScanner
from core.dialogue.source_identity import memory_identity


class TranslationWorker(QThread):
    """
    Worker chạy ngầm trên QThread độc lập.
    Đảm nhận toàn bộ chu trình: Chụp màn hình -> Nhận diện thay đổi ảnh -> OCR -> Dịch thuật.
    Không bao giờ gây gián đoạn hay đơ giao diện PyQt5.
    """

    # Signals gửi về UI Main Thread
    text_translated = pyqtSignal(str)
    error_occurred = pyqtSignal(object)
    status_updated = pyqtSignal(str)
    blocks_updated = pyqtSignal(object)
    shutdown_finished = pyqtSignal()
    revision_changed = pyqtSignal(int)
    subtitle_updated = pyqtSignal(object)
    translation_status_updated = pyqtSignal(object)
    log_updated = pyqtSignal(str)
    observation_ready = pyqtSignal(object)
    capture_observation_ready = pyqtSignal(object)
    capture_status_updated = pyqtSignal(object)
    capture_terminal_status = pyqtSignal(object)
    capture_rebind_requested = pyqtSignal(object)
    context_status_changed = pyqtSignal(object)

    _settings = runtime_field('settings')
    _region = runtime_field('region')
    _revision = runtime_field('revision')
    _invalidated = runtime_field('invalidated')
    _is_running = runtime_field('running')
    _overlay_rect = runtime_field('overlay_rect')
    _capture_geometry = runtime_field('geometry')
    _capture_profile = runtime_field('profile')
    _capture_context = runtime_field('context')
    _context_source_invalid = runtime_field('source_invalid')
    _force_regions = runtime_field('force_regions')
    _needs_dialogue_scan = runtime_field('needs_dialogue_scan')
    _translation_session_id = runtime_field('session_id')

    def __init__(self, state, region, interval_ms=500, *, ocr_reader=None):
        super().__init__()
        self.state = state
        self._ocr_reader = ocr_reader
        self._runtime = WorkerRuntimeState(load_runtime_settings(state, interval_ms), region)
        self._mutex = self._runtime.mutex
        self._frame_ocr = FrameOcrProcessor(
            read_ocr=lambda *args, **kwargs: self._read_ocr(*args, **kwargs),
            is_current=self._is_current,
            publish=self.observation_ready.emit,
            clock=lambda: time.monotonic(),
        )
        self._google_recovery = GoogleRecoveryGate()
        self._output = TranslationOutputPolicy()
        self._coordinator = DialogueCoordinator(clock=lambda: time.monotonic(), parent=self)
        self.observation_ready.connect(self._coordinator.observe, Qt.QueuedConnection)
        self.capture_observation_ready.connect(self._coordinator.observe_capture, Qt.QueuedConnection)
        self._coordinator.capture_scan_policy_changed.connect(self.request_capture_scan)
        self._coordinator.jobs_changed.connect(self._replace_dialogue_pending)
        self._coordinator.scan_policy_changed.connect(self.request_dialogue_scan)
        self._coordinator.subtitle_updated.connect(self._publish_dialogue_subtitle)
        self._coordinator.blocks_updated.connect(self.blocks_updated.emit)
        self._coordinator.error_occurred.connect(self.error_occurred.emit)
        self._coordinator.context_status_changed.connect(self.context_status_changed.emit)
        self.capture_terminal_status.connect(self._on_context_terminal,Qt.QueuedConnection)
        self._coordinator._timer.timeout.connect(self._dialogue_status_tick)
        self._block_translator = self._new_block_translator()
        self._lifecycle = WorkerLifecycle()
        self.finished.connect(self._threads_finished)
        self.revision_changed.connect(self._reset_dialogue)
        self._reset_dialogue(self._revision)

    def _new_block_translator(self):
        thread = BlockTranslationWorker(clock=lambda: time.monotonic(), service_factory=lambda: TranslationService(log_callback=self.log_updated.emit), google_recovery=self._google_recovery, parent=self)
        thread.log_updated.connect(self.log_updated.emit)
        thread.job_started.connect(self._coordinator.on_job_started, Qt.QueuedConnection)
        thread.result_ready.connect(self._coordinator.on_result, Qt.QueuedConnection)
        thread.finished.connect(self._threads_finished)
        return thread

    @property
    def translation_session_id(self):
        with QMutexLocker(self._mutex):
            return self._translation_session_id


    @pyqtSlot(object, object, int)
    def _replace_dialogue_pending(self, jobs, active_turns, revision):
        self._block_translator.replace_pending(jobs, active_turns, revision)

    @pyqtSlot(int, bool)
    def request_dialogue_scan(self, revision, needs_scan):
        with QMutexLocker(self._mutex):
            if revision == self._revision:
                self._needs_dialogue_scan = needs_scan

    @pyqtSlot(int)
    def _reset_dialogue(self, revision):
        with QMutexLocker(self._mutex):
            snapshot = self._runtime.snapshot()
        if revision != snapshot.revision:
            return
        source, scopes = memory_identity(source_invalid=snapshot.source_invalid,
            profile=snapshot.profile, context=snapshot.context,
            geometry=snapshot.geometry, region=snapshot.region)
        self._output.reset_subtitle()
        self._coordinator.reset(snapshot.settings, revision=revision,
            session_id=snapshot.session_id, running=snapshot.running,
            memory_source=source, memory_scopes=scopes)
        if snapshot.profile is not None and snapshot.context is not None:
            self._coordinator.configure_capture(snapshot.profile, snapshot.context)

    def _memory_identity(self,profile,context):
        return memory_identity(source_invalid=self._context_source_invalid,
                               profile=profile, context=context,
                               geometry=self._capture_geometry, region=self._region)

    def reset_dialogue_context(self):
        self._coordinator.clear_context()
        with QMutexLocker(self._mutex):
            revision = self._runtime.reset_context()
        self.revision_changed.emit(revision)
        return revision

    @pyqtSlot(object)
    def _on_context_terminal(self,status):
        if status.phase in ('unavailable','error'):self.invalidate_context_source(status.binding_epoch)

    def invalidate_context_source(self,binding_epoch):
        with QMutexLocker(self._mutex):
            revision = self._runtime.invalidate_source(binding_epoch)
        if revision is not None:
            self._coordinator.clear_context()
            self.revision_changed.emit(revision)

    @pyqtSlot(int, object)
    def request_capture_scan(self, revision, regions):
        with QMutexLocker(self._mutex):
            if revision == self._revision:
                self._force_regions = frozenset(regions)

    @property
    def is_drained(self):
        return not self.isRunning() and not self._block_translator.isRunning()

    @property
    def capture_context(self):
        with QMutexLocker(self._mutex):
            return self._capture_context

    @property
    def capture_profile(self):
        with QMutexLocker(self._mutex):
            return self._capture_profile

    def configure_capture(self, profile, context):
        serialize_capture_profile(profile)
        if (context.source_kind != profile.source_kind
                or (profile.source_kind == 'window' and context.window is None)):
            raise ValueError('Capture source requires an explicit matching identity')
        with QMutexLocker(self._mutex):
            revision = self._runtime.configure_capture(profile, context)
        self.revision_changed.emit(revision)
        return revision

    @pyqtSlot(object)
    def update_capture_geometry(self, context):
        with QMutexLocker(self._mutex):
            if not self._runtime.update_geometry(context):
                return
        self._coordinator.update_capture_geometry(context)

    @pyqtSlot(object)
    def _publish_dialogue_subtitle(self, frame):
        if not self._is_current(frame.revision): return
        self.subtitle_updated.emit(frame)
        # Direct GUI listeners may reconfigure/reset during signal delivery.
        if not self._is_current(frame.revision): return
        if self._output.accept_text(frame.text):
            self.text_translated.emit(frame.text)

    @pyqtSlot()
    def _dialogue_status_tick(self):
        with QMutexLocker(self._mutex):
            settings, revision, running = self._settings, self._revision, self._is_running
        if running: self._publish_translation_status(settings, revision)

    @property
    def revision(self):
        with QMutexLocker(self._mutex):
            return self._revision

    def set_capture_geometry(self, geometry):
        with QMutexLocker(self._mutex):
            revision = self._runtime.set_geometry(geometry)
        self.revision_changed.emit(revision)
        return revision

    @property
    def _restart_pending(self):
        return self._lifecycle.restart_pending

    @property
    def _restart_preserve_session(self):
        return self._lifecycle.restart_preserve_session

    @property
    def _shutdown_pending(self):
        return self._lifecycle.shutdown_pending

    def _threads_finished(self):
        capture_running = self.isRunning()
        translation_running = self._block_translator.isRunning()
        if capture_running or translation_running:
            return
        if not self.is_running():
            self._reset_dialogue(self.revision)
        action = self._lifecycle.threads_finished(
            capture_running=capture_running, translation_running=translation_running)
        if action is not None:
            if action.kind == 'restart':
                self.start_worker(preserve_translation_session=action.preserve_session)
            else:
                self.shutdown_finished.emit()

    # ===== Interface tương thích với Controller =====
    def configure(self, settings: RuntimeSettings) -> int:
        """Publish an immutable snapshot; only run() consumes invalidation."""
        with QMutexLocker(self._mutex):
            revision, mode_changed = self._runtime.configure(settings)
        self.revision_changed.emit(revision)
        if (mode_changed
                and (self.is_running() or self._restart_pending)
                and (self.isRunning() or self._block_translator.isRunning())):
            self.stop_worker(preserve_translation_session=True)
            self._lifecycle.request_restart(preserve_session=True)
            self._threads_finished()
            return self.revision
        return revision

    def setInterval(self, ms: int):
        with QMutexLocker(self._mutex):
            revision = self._runtime.set_interval(ms)
        self.revision_changed.emit(revision)

    def interval(self) -> int:
        with QMutexLocker(self._mutex):
            return self._settings.interval_ms

    def set_region(self, region: dict):
        with QMutexLocker(self._mutex):
            revision = self._runtime.set_region(region)
        self.revision_changed.emit(revision)
        return revision

    def set_overlay_rect(self, rect):
        with QMutexLocker(self._mutex):
            self._overlay_rect = rect

    def is_running(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._is_running

    @property
    def restart_pending(self) -> bool:
        """GUI-owned start intent while the previous threads drain."""
        return self._restart_pending

    def start_worker(self, *, preserve_translation_session=False):
        """Start once both owners drain; retain the first queued session policy."""
        if self._lifecycle.request_start(
                capture_running=self.isRunning(),
                translation_running=self._block_translator.isRunning(),
                running=self.is_running(), preserve_session=preserve_translation_session):
            self._start_threads(QThread.InheritPriority, preserve_translation_session)

    def stop_worker(self, *, preserve_translation_session=False):
        """Dừng an toàn worker thread và dọn dẹp RAM"""
        with QMutexLocker(self._mutex):
            revision = self._runtime.stop_run()
        self.requestInterruption()
        if not preserve_translation_session:
            self._google_recovery.invalidate_requests()
        self._lifecycle.request_stop()
        self._block_translator.request_stop()
        self.revision_changed.emit(revision)
        self._threads_finished()

    # Hỗ trợ trực tiếp các phương thức start() và stop()
    def start(self, priority=QThread.InheritPriority):
        self._start_threads(priority, False)

    def _start_threads(self, priority, preserve_translation_session):
        if not self._lifecycle.request_direct_start(
                capture_running=self.isRunning(),
                translation_running=self._block_translator.isRunning(),
                preserve_session=preserve_translation_session):
            return
        if not preserve_translation_session:
            self._google_recovery.begin_session(now_s=time.monotonic())
        self._lifecycle.started()
        with QMutexLocker(self._mutex):
            revision = self._runtime.start_run(preserve_session=preserve_translation_session)
        old = self._block_translator
        self._block_translator = self._new_block_translator()
        old.deleteLater()
        self._block_translator.start()
        self.revision_changed.emit(revision)
        super().start(priority)

    def stop(self):
        self.stop_worker()

    # ===== Change Detection & Masking =====
    def _mask_overlay_numpy(self, img, region, overlay_rect):
        return mask_overlay(img, region, overlay_rect)

    def _is_frame_changed(self, img_gray, threshold=1.2) -> bool:
        return self._frame_ocr.is_frame_changed(img_gray, threshold)

    @property
    def _prev_frame_thumb(self):
        return self._frame_ocr.previous_thumbnail

    @_prev_frame_thumb.setter
    def _prev_frame_thumb(self, value):
        self._frame_ocr.previous_thumbnail = value

    @property
    def _dialogue_last_ocr(self):
        return self._frame_ocr.last_ocr

    @_dialogue_last_ocr.setter
    def _dialogue_last_ocr(self, value):
        self._frame_ocr.last_ocr = value

    # ===== Worker Loop =====
    def _is_current(self, revision: int) -> bool:
        with QMutexLocker(self._mutex):
            return (self._is_running and not self.isInterruptionRequested()
                    and self._revision == revision)

    def _emit_current(self, revision: int, signal, *args):
        if self._is_current(revision):
            signal.emit(*args)

    def _take_snapshot(self):
        with QMutexLocker(self._mutex):
            if not self._is_running or self.isInterruptionRequested():
                return None
            snapshot = self._runtime.snapshot(consume_invalidation=True)
        if snapshot.invalidated:
            # Processor state is reset only by the capture thread consuming invalidation.
            self._frame_ocr.reset()
        return snapshot


    def retry_translation(self):
        with QMutexLocker(self._mutex):
            if not self._is_running or self._settings.provider.name != 'Google Translate':
                return False
        if self._google_recovery.snapshot(now_s=time.monotonic()).phase != 'paused':
            return False
        with QMutexLocker(self._mutex):
            revision = self._runtime.invalidate()
        self._block_translator.replace_pending((), frozenset(), revision)
        self._google_recovery.manual_retry(now_s=time.monotonic())
        self.revision_changed.emit(revision)
        return True

    def _publish_translation_status(self, settings, revision):
        if not self._is_current(revision):
            return
        recovery = (self._google_recovery.snapshot(now_s=time.monotonic())
                    if settings.provider.name == 'Google Translate' else None)
        status = self._output.next_status(settings.provider.name, revision,
                                         self.translation_session_id, recovery)
        if status is not None:
            self.translation_status_updated.emit(status)


    def _process_dialogue_frame(self, img_gray, settings, revision, geometry=None, *, captured_at_s=None, force_scan=None):
        if force_scan is None:
            force_scan = self._dialogue_scan_requested
        return self._frame_ocr.process(img_gray, settings, revision, geometry,
            captured_at_s=captured_at_s, force_scan=force_scan,
            change_detector=self._is_frame_changed)

    def _dialogue_scan_requested(self):
        with QMutexLocker(self._mutex):
            return self._needs_dialogue_scan


    def _read_ocr(self, image, source_name, settings=None):
        lang = resolve_ocr_language(source_name)
        if lang is None:
            from core.contracts import OcrResult
            return OcrResult(error=EngineError('ocr_model_missing', 'Ngôn ngữ nguồn không được hỗ trợ.', False))
        if settings is None:
            with QMutexLocker(self._mutex):
                settings = self._settings
        reader = self._ocr_reader or ocr_image
        return read_ocr(image, lang, settings, reader)

    def _runner_mark_stopped(self):
        with QMutexLocker(self._mutex):
            self._is_running = False

    def _publish_cleanup_error(self, revision, error):
        # Cleanup reports after mark_stopped; reject newer revisions, not the
        # stopped flag. This is a worker error, never a source terminal event.
        with QMutexLocker(self._mutex):
            current = revision == self._revision
        if current:
            self.error_occurred.emit(error)

    def _new_runner(self):
        # Bind at invocation time to preserve injected factories and clocks.
        ports = RunnerPorts(
            take_snapshot=self._take_snapshot,
            read_revision=lambda: self.revision,
            is_current=self._is_current,
            mark_stopped=self._runner_mark_stopped,
            stop_translation=self._block_translator.request_stop,
            read_ocr=self._read_ocr,
            process_dialogue_frame=self._process_dialogue_frame,
            publish_error=lambda revision, value: self._emit_current(revision, self.error_occurred, value),
            publish_status=lambda revision, value: self._emit_current(revision, self.capture_status_updated, value),
            publish_observation=lambda revision, value: self._emit_current(revision, self.capture_observation_ready, value),
            publish_terminal=self.capture_terminal_status.emit,
            publish_cleanup_error=self._publish_cleanup_error,
        )
        dependencies = RunnerDependencies(
            desktop_factory=mss.mss, source_factory=create_capture_source,
            scanner_factory=RegionScanner, clock=time.monotonic,
            sleep=time.sleep, sleep_ms=self.msleep,
            release_ocr=release_ocr_engine, compact_memory=compact_memory,
        )
        return CaptureOcrRunner(ports, dependencies)

    def run(self):
        # Resource construction and cleanup happen on this existing QThread.
        if self.capture_profile is not None:
            self._run_capture()
        else:
            self._new_runner().run_legacy()

    def _run_capture(self):
        self._new_runner().run_capture()
