import sys
import time
import gc
import ctypes
from dataclasses import replace
from ctypes import wintypes
import cv2
import numpy as np
import mss
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QMutex, QMutexLocker, Qt

from engines.ocr import ocr_image, release_ocr_engine
from engines.translator import TranslationService
from core.config import SUPPORTED_LANGUAGES, load_runtime_settings
from core.contracts import EngineError, RuntimeSettings, TranslationStatus, SubtitleFrame
from core.retry import RetryState
from core.subtitle_stabilizer import SubtitleStabilizer
from core.blocks.translation_worker import BlockTranslationWorker
from core.blocks.models import Rect
from core.google_recovery import GoogleRecoveryGate
from core.dialogue.coordinator import DialogueCoordinator
from core.dialogue.models import DialogueObservation
from core.capture.models import CaptureStatus, SourceStatus
from core.capture.profile import serialize_capture_profile
from core.capture.source import create_capture_source
from core.capture.scan import RegionScanner
from core.capture.geometry import resolve_region_crops


def compact_memory():
    """
    Thu hồi bộ nhớ rác (GC) và giải phóng Working Set của Windows về OS.
    An toàn trên mọi hệ điều hành.
    """
    try:
        gc.collect()
        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
    except Exception:
        pass


class TranslationWorker(QThread):
    """
    Worker chạy ngầm trên QThread độc lập.
    Đảm nhận toàn bộ chu trình: Chụp màn hình -> Nhận diện thay đổi ảnh -> OCR -> Dịch thuật.
    Không bao giờ gây gián đoạn hay đơ giao diện PyQt5.
    """

    # Signals gửi về UI Main Thread
    text_translated = pyqtSignal(str)
    text_unchanged = pyqtSignal()
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

    def __init__(self, state, region, interval_ms=500, *, ocr_reader=None):
        super().__init__()
        self.state = state
        self._ocr_reader = ocr_reader
        self._region = region.copy()
        self._settings = load_runtime_settings(state, interval_ms)
        self._revision = 0
        self._invalidated = True
        self._is_running = False
        self._mutex = QMutex()

        self._prev_frame_thumb = None
        self._prev_text = ""
        self._retry_not_before = 0.0
        self._retry_state = RetryState()
        self._retry_frame_only = False
        self._stabilizer = SubtitleStabilizer()
        self._overlay_rect = None  # (x, y, w, h)
        self._capture_geometry = None
        self._capture_profile = None
        self._capture_context = None
        self._force_regions = frozenset()
        self._google_recovery = GoogleRecoveryGate()
        self._translation_session_id = 0
        self._last_translation_status = None
        self._needs_dialogue_scan = False
        self._dialogue_last_ocr = float('-inf')
        self._dialogue_retry = RetryState()
        self._dialogue_due = 0.
        self._dialogue_exhausted = False
        self._scan_id = 0
        self._last_emitted_translation = ''
        self._coordinator = DialogueCoordinator(clock=lambda: time.monotonic(), parent=self)
        self.observation_ready.connect(self._coordinator.observe, Qt.QueuedConnection)
        self.capture_observation_ready.connect(self._coordinator.observe_capture, Qt.QueuedConnection)
        self._coordinator.capture_scan_policy_changed.connect(self.request_capture_scan)
        self._coordinator.jobs_changed.connect(self._replace_dialogue_pending)
        self._coordinator.scan_policy_changed.connect(self.request_dialogue_scan)
        self._coordinator.subtitle_updated.connect(self._publish_dialogue_subtitle)
        self._coordinator.blocks_updated.connect(self.blocks_updated.emit)
        self._coordinator.error_occurred.connect(self.error_occurred.emit)
        self._coordinator._timer.timeout.connect(self._dialogue_status_tick)
        self._block_translator = self._new_block_translator()
        self._restart_pending = False
        self._restart_preserve_session = False
        self._shutdown_pending = False
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

    @staticmethod
    def _uses_async(settings):
        return True

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
            if revision != self._revision: return
            settings, running = self._settings, self._is_running
        self._last_emitted_translation = ''
        self._coordinator.reset(settings, revision=revision,
                                session_id=self.translation_session_id, running=running)
        with QMutexLocker(self._mutex):
            profile, context = self._capture_profile, self._capture_context
        if profile is not None and context is not None:
            self._coordinator.configure_capture(profile, context)

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
            self._capture_profile, self._capture_context = profile, context
            self._capture_geometry = context.geometry
            self._revision += 1
            revision = self._revision
            self._invalidated = True
            self._force_regions = frozenset()
        self.revision_changed.emit(revision)
        return revision

    @pyqtSlot(object)
    def update_capture_geometry(self, context):
        with QMutexLocker(self._mutex):
            old = self._capture_context
            if old is None or (old.binding_epoch, old.source_kind, old.window,
                    old.geometry.image_size_px, old.geometry.screen) != (
                    context.binding_epoch, context.source_kind, context.window,
                    context.geometry.image_size_px, context.geometry.screen):
                return
            if context.geometry_sequence < old.geometry_sequence:
                return
            self._capture_context = context
            self._capture_geometry = context.geometry
        self._coordinator.update_capture_geometry(context)

    @pyqtSlot(object)
    def _publish_dialogue_subtitle(self, frame):
        if not self._is_current(frame.revision): return
        self.subtitle_updated.emit(frame)
        if frame.text and frame.text != self._last_emitted_translation:
            self._last_emitted_translation = frame.text
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
            self._capture_geometry = geometry
            self._revision += 1
            self._invalidated = True
            revision = self._revision
        self.revision_changed.emit(revision)
        return revision

    def _threads_finished(self):
        if self.isRunning() or self._block_translator.isRunning():
            return
        if not self.is_running():
            self._reset_dialogue(self.revision)
        if self._restart_pending:
            preserve = self._restart_preserve_session
            self._restart_pending = False
            self.start_worker(preserve_translation_session=preserve)
        elif self._shutdown_pending:
            self._shutdown_pending = False
            self.shutdown_finished.emit()

    # ===== Interface tương thích với Controller =====
    def configure(self, settings: RuntimeSettings) -> int:
        """Publish an immutable snapshot; only run() consumes invalidation."""
        with QMutexLocker(self._mutex):
            mode_changed = self._settings.overlay_mode != settings.overlay_mode
            lane_changed = self._uses_async(self._settings) != self._uses_async(settings)
            self._settings = settings
            self._revision += 1
            self._invalidated = True
            revision = self._revision
        self.revision_changed.emit(revision)
        if ((mode_changed or lane_changed)
                and (self.is_running() or self._restart_pending)
                and (self.isRunning() or self._block_translator.isRunning())):
            self.stop_worker(preserve_translation_session=True)
            self._restart_pending = True
            self._restart_preserve_session = True
            self._threads_finished()
            return self.revision
        return revision

    def setInterval(self, ms: int):
        with QMutexLocker(self._mutex):
            self._settings = replace(self._settings, interval_ms=max(100, min(3000, int(ms))))
            self._revision += 1
            self._invalidated = True
            revision = self._revision
        self.revision_changed.emit(revision)

    def interval(self) -> int:
        with QMutexLocker(self._mutex):
            return self._settings.interval_ms

    def set_region(self, region: dict):
        with QMutexLocker(self._mutex):
            self._region = region.copy()
            self._revision += 1
            self._invalidated = True
            revision = self._revision
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
        """Khởi động worker thread nếu chưa chạy"""
        if self._restart_pending:
            return  # Keep the existing start intent, including its session policy.
        if (self._shutdown_pending and self.isRunning()) or self._block_translator.isRunning() and not self.is_running():
            self._restart_pending = True
            self._restart_preserve_session = preserve_translation_session
            return
        if not self.isRunning() and not self._block_translator.isRunning():
            with QMutexLocker(self._mutex):
                self._is_running = True
            self._start_threads(QThread.InheritPriority, preserve_translation_session)

    def stop_worker(self, *, preserve_translation_session=False):
        """Dừng an toàn worker thread và dọn dẹp RAM"""
        with QMutexLocker(self._mutex):
            self._is_running = False
            self._revision += 1
            self._invalidated = True
        self.requestInterruption()
        if not preserve_translation_session:
            self._google_recovery.invalidate_requests()
        self._restart_pending = False
        self._shutdown_pending = True
        self._block_translator.request_stop()
        self.revision_changed.emit(self.revision)
        if not self._uses_async(self._settings) and not self._block_translator.isRunning():
            self.wait(3000)
            compact_memory()
        self._threads_finished()

    # Hỗ trợ trực tiếp các phương thức start() và stop()
    def start(self, priority=QThread.InheritPriority):
        self._start_threads(priority, False)

    def _start_threads(self, priority, preserve_translation_session):
        if self.isRunning():
            return
        if self._block_translator.isRunning():
            self._restart_pending = True
            self._restart_preserve_session = preserve_translation_session
            return
        if not preserve_translation_session:
            self._google_recovery.begin_session(now_s=time.monotonic())
            with QMutexLocker(self._mutex):
                self._translation_session_id += 1
        self._shutdown_pending = False
        with QMutexLocker(self._mutex):
            self._is_running = True
            self._revision += 1
            self._invalidated = True
        if self._uses_async(self._settings):
            old = self._block_translator
            self._block_translator = self._new_block_translator()
            old.deleteLater()
            self._block_translator.start()
        self.revision_changed.emit(self.revision)
        super().start(priority)

    def stop(self):
        self.stop_worker()

    # ===== Change Detection & Masking =====
    def _mask_overlay_numpy(self, img, region, overlay_rect):
        """Che mờ vùng overlay phụ đề nếu nằm đè lên vùng chụp để tránh OCR chính nó"""
        if not overlay_rect:
            return img

        try:
            ox, oy, ow, oh = overlay_rect
            if not all(isinstance(value, (int, float)) and np.isfinite(value)
                       for value in (ox, oy, ow, oh)) or ow <= 0 or oh <= 0:
                return img
        except (TypeError, ValueError):
            return img
        rx, ry = region["left"], region["top"]

        x1 = max(0, int(np.floor(ox - rx - 6)))
        y1 = max(0, int(np.floor(oy - ry - 6)))
        x2 = min(img.shape[1], int(np.ceil(ox + ow - rx + 6)))
        y2 = min(img.shape[0], int(np.ceil(oy + oh - ry + 6)))

        if x1 < x2 and y1 < y2:
            img[y1:y2, x1:x2] = 0

        return img

    def _is_frame_changed(self, img_gray, threshold=1.2) -> bool:
        """
        Fast Change Detection:
        Thu nhỏ ảnh xuống (100x40) và tính trung bình sai lệch pixel (MAE).
        Nếu ảnh tĩnh (< threshold), bỏ qua OCR để tiết kiệm 90% tải CPU và không gọi API thừa.
        """
        try:
            thumb = cv2.resize(img_gray, (100, 40), interpolation=cv2.INTER_LINEAR)
            if self._prev_frame_thumb is None:
                self._prev_frame_thumb = thumb
                return True

            diff = cv2.absdiff(self._prev_frame_thumb, thumb)
            mean_diff = float(np.mean(diff))

            if mean_diff > threshold:
                self._prev_frame_thumb = thumb
                return True
            return False
        except Exception:
            return True

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
            snapshot = (self._settings, self._revision, self._region.copy(), self._overlay_rect)
            invalidated, self._invalidated = self._invalidated, False
        if invalidated:
            # These fields belong to this worker, never to the settings UI.
            self._prev_text = ""
            self._prev_frame_thumb = None
            self._retry_not_before = 0.0
            self._retry_state.reset()
            self._retry_frame_only = False
            self._stabilizer.reset()
            self._dialogue_last_ocr = float('-inf')
            self._dialogue_retry.reset()
            self._dialogue_due = 0.
            self._dialogue_exhausted = False
            self._scan_id = 0
        return snapshot

    def retry_current(self) -> None:
        """Ask the worker to reprocess the current frame as a new revision."""
        with QMutexLocker(self._mutex):
            self._revision += 1
            self._invalidated = True
        self.revision_changed.emit(self.revision)

    def retry_translation(self):
        with QMutexLocker(self._mutex):
            if not self._is_running or self._settings.provider.name != 'Google Translate':
                return False
        if self._google_recovery.snapshot(now_s=time.monotonic()).phase != 'paused':
            return False
        with QMutexLocker(self._mutex):
            self._revision += 1
            revision = self._revision
            self._invalidated = True
        self._block_translator.replace_pending((), frozenset(), revision)
        self._google_recovery.manual_retry(now_s=time.monotonic())
        self.revision_changed.emit(revision)
        return True

    def _publish_translation_status(self, settings, revision):
        if settings.provider.name == 'Google Translate':
            recovery = self._google_recovery.snapshot(now_s=time.monotonic())
            phase = 'active' if recovery.phase == 'ready' else recovery.phase
            status = TranslationStatus(settings.provider.name, revision, self.translation_session_id,
                                       phase, recovery.retries_issued, recovery.not_before_s if phase == 'retry_wait' else None)
        else:
            status = TranslationStatus(settings.provider.name, revision, self.translation_session_id, 'active')
        if status != self._last_translation_status:
            self._last_translation_status = status
            self._emit_current(revision, self.translation_status_updated, status)

    def _schedule_retry(self, error: EngineError, settings: RuntimeSettings) -> None:
        retry_error = error
        # Keep the provider's existing cooldown floor while enforcing the shared
        # three-retry budget and honoring any larger Retry-After value.
        if settings.provider.name == "Google Gemini":
            minimum = 5.0 if error.code == "rate_limit" else 2.0
            retry_error = replace(
                error,
                retry_after_s=max(error.retry_after_s or 0.0, minimum),
            )
        due = self._retry_state.next_due(time.monotonic(), retry_error)
        self._retry_not_before = due or 0.0
        self._retry_frame_only = due is None
        if due is not None:
            # Force OCR again after the deadline even when the capture is static.
            self._prev_frame_thumb = None

    def _process_dialogue_frame(self, img_gray, settings, revision, geometry=None, *, captured_at_s=None):
        if not self._is_current(revision): return False
        now=time.monotonic()
        changed=self._is_frame_changed(img_gray)
        if changed:
            self._dialogue_exhausted=False
            self._dialogue_retry.reset()
        with QMutexLocker(self._mutex):force=self._needs_dialogue_scan
        scan=changed or force or now-self._dialogue_last_ocr>=max(1000,settings.interval_ms)/1000
        if not scan or now<self._dialogue_due or self._dialogue_exhausted:return True
        result=self._read_ocr(img_gray, settings.source_lang)
        completed=time.monotonic()
        if not self._is_current(revision):return False
        self._dialogue_last_ocr=now
        if result.error is None:
            self._dialogue_retry.reset();self._dialogue_due=0.
        else:
            due=self._dialogue_retry.next_due(completed,result.error)
            self._dialogue_due=due or 0.
            self._dialogue_exhausted=due is None
        self._scan_id+=1
        self.observation_ready.emit(DialogueObservation(revision,self._scan_id,
            now if captured_at_s is None else captured_at_s,completed,settings,result,geometry))
        return False

    def _process_frame(self, img_gray, settings: RuntimeSettings, revision: int, service: TranslationService) -> bool:
        """Legacy direct-call helper. Runtime run() always uses the async coordinator.

        Retained for existing embedding/tests; not used for game dialogue dispatch.
        """
        if not self._is_current(revision):
            return False
        if time.monotonic() < self._retry_not_before:
            return True
        frame_changed = self._is_frame_changed(img_gray)
        if not frame_changed and (not self._stabilizer.has_pending or self._retry_frame_only):
            if self._prev_text:
                self._emit_current(revision, self.text_unchanged)
            return True
        result = self._read_ocr(img_gray, settings.source_lang)
        if not self._is_current(revision):
            return False
        if result.error is not None:
            self._schedule_retry(result.error, settings)
            self._emit_current(revision, self.error_occurred, result.error)
            return False
        decision = self._stabilizer.observe(result.text, time.monotonic())
        if decision.action == 'wait':
            # A fresh candidate still needs its second observation even if the
            # previous source exhausted retries or failed permanently.
            self._retry_frame_only = False
            if not self._stabilizer.has_pending:
                self._retry_state.reset()
                self._retry_not_before = 0.0
            return False
        if decision.action == 'unchanged':
            self._emit_current(revision, self.text_unchanged)
            return False
        text = decision.text
        translated = service.translate(text, settings)
        if not self._is_current(revision):
            return False
        if translated.error is not None:
            self._schedule_retry(translated.error, settings)
            self._emit_current(revision, self.error_occurred, translated.error)
        elif translated.text:
            # Commit atomically with respect to settings/region publication.
            with QMutexLocker(self._mutex):
                if (self._revision != revision or not self._is_running
                        or self.isInterruptionRequested()):
                    return False
                self._retry_not_before = 0.0
                self._retry_frame_only = False
                self._retry_state.reset()
                self._stabilizer.commit(text)
                self._prev_text = text
            self._emit_current(revision, self.text_translated, translated.text)
            self._emit_current(revision, self.subtitle_updated, SubtitleFrame(revision, 0, text, translated.text))
        return False

    def _read_ocr(self, image, source_name):
        lang = SUPPORTED_LANGUAGES.get(source_name)
        if lang is None:
            from core.contracts import OcrResult
            return OcrResult(error=EngineError('ocr_model_missing', 'Ngôn ngữ nguồn không được hỗ trợ.', False))
        return (self._ocr_reader or ocr_image)(image, lang=lang)

    def run(self):
        # Construction, use and cleanup all happen on this thread. UI only publishes settings.
        if self.capture_profile is not None:
            self._run_capture()
            return
        revision = None
        idle_counter = 0
        try:
            with mss.mss() as sct:
                while True:
                    snapshot = self._take_snapshot()
                    if snapshot is None:
                        break
                    settings, revision, region, overlay_rect = snapshot
                    started = time.monotonic()
                    img_raw = img = img_gray = None
                    idle = False
                    try:
                        if region.get("width", 0) <= 0 or region.get("height", 0) <= 0:
                            time.sleep(0.1)
                            continue
                        monitor = {k: int(region[k]) for k in ("top", "left", "width", "height")}
                        img_raw = sct.grab(monitor)
                        img = np.array(img_raw)
                        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        if settings.overlay_mode == 'blocks':
                            with QMutexLocker(self._mutex):
                                geometry = self._capture_geometry
                            expected = Rect(region['left'], region['top'], region['width'], region['height'])
                            if geometry is None or geometry.region_px != expected:
                                self._emit_current(revision, self.error_occurred,
                                                   EngineError('capture_geometry', 'Hãy chọn vùng OCR nằm trọn trên một màn hình.', False))
                                with QMutexLocker(self._mutex):
                                    self._is_running = False
                                continue
                            geometry = replace(geometry, image_size_px=(img_gray.shape[1], img_gray.shape[0]))
                            idle = self._process_dialogue_frame(img_gray, settings, revision, geometry, captured_at_s=started)
                        else:
                            img_gray = self._mask_overlay_numpy(img_gray, region, overlay_rect)
                            idle = self._process_dialogue_frame(img_gray, settings, revision, captured_at_s=started)
                    except Exception:
                        self._emit_current(revision, self.error_occurred,
                                           EngineError("capture", "Không thể xử lý ảnh chụp màn hình.", True))
                    finally:
                        del img_raw, img, img_gray
                    idle_counter = idle_counter + 1 if idle else 0
                    if idle_counter == 3 or (idle_counter > 0 and idle_counter % 20 == 0):
                        compact_memory()
                    elapsed_ms = (time.monotonic() - started) * 1000
                    time.sleep(max(20, settings.interval_ms - elapsed_ms) / 1000.0)
        except Exception:
            if revision is None:
                with QMutexLocker(self._mutex):
                    revision = self._revision
            self._emit_current(revision, self.error_occurred,
                               EngineError("capture", "Không thể mở bộ chụp màn hình.", True))
        finally:
            self._block_translator.request_stop()
            self._stabilizer.reset()
            release_ocr_engine()
            with QMutexLocker(self._mutex):
                self._is_running = False
            compact_memory()

    def _run_capture(self):
        source = None
        source_key = scanner_revision = None
        scanner = None
        last_status = None
        revision = self.revision
        try:
            while True:
                snapshot = self._take_snapshot()
                if snapshot is None:
                    break
                settings, revision, _, overlay_rect = snapshot
                with QMutexLocker(self._mutex):
                    profile, context = self._capture_profile, self._capture_context
                    forced = self._force_regions
                started = time.monotonic()
                key = (profile, context.binding_epoch)
                if key != source_key:
                    if source is not None:
                        source.close()
                    source = None
                    # The callback only emits immutable data. Qt delivers the
                    # terminal event to the GUI even while Paddle is blocked.
                    source = create_capture_source(context, on_terminal=self.capture_terminal_status.emit)
                    source.open(context, roi_rects_px=tuple(resolve_region_crops(profile, context.geometry.image_size_px).values()))
                    source_key = key
                    last_status = None
                if scanner_revision != revision:
                    scanner = RegionScanner(profile, ocr_reader=self._ocr_reader or ocr_image, clock=time.monotonic)
                    scanner_revision = revision
                frame = source.read_latest(now_s=started)
                status = source.status()
                current_status = CaptureStatus(revision, status.binding_epoch, status.phase, status.error)
                if current_status != last_status:
                    self._emit_current(revision, self.capture_status_updated, current_status)
                    last_status = current_status
                if status.phase in ('unavailable', 'error'):
                    self.capture_terminal_status.emit(status)
                    break
                masks = ()
                if context.source_kind == 'desktop' and overlay_rect:
                    x, y, width, height = overlay_rect
                    if width > 0 and height > 0:
                        origin = context.geometry.region_px
                        masks = (Rect(x-origin.x-6, y-origin.y-6, width+12, height+12),)
                if frame is not None:
                    batch = scanner.observe(frame, settings=settings, context=context,
                        revision=revision, force_regions=forced, dynamic_masks_px=masks,
                        is_current=lambda: self._is_current(revision))
                    if batch is not None:
                        self._emit_current(revision, self.capture_observation_ready, batch)
                # Interruption is checked frequently without involving the GUI.
                deadline = started + settings.interval_ms / 1000
                while self._is_current(revision) and time.monotonic() < deadline:
                    self.msleep(20)
        except Exception:
            with QMutexLocker(self._mutex):
                context = self._capture_context
            if context is not None:
                self.capture_terminal_status.emit(SourceStatus(context.binding_epoch, 'error',
                    EngineError('capture', 'Không thể mở hoặc xử lý nguồn chụp. Chọn nguồn hoặc thử lại.', True)))
        finally:
            try:
                if source is not None:
                    source.close()
            finally:
                self._block_translator.request_stop()
                release_ocr_engine()
                with QMutexLocker(self._mutex):
                    self._is_running = False
                compact_memory()
