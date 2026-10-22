import sys
import time
import gc
import ctypes
from dataclasses import replace
from ctypes import wintypes
import cv2
import numpy as np
import mss
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from engines.ocr import ocr_image
from engines.translator import TranslationService
from core.config import SUPPORTED_LANGUAGES, load_runtime_settings
from core.contracts import EngineError, RuntimeSettings
from core.retry import RetryState
from core.subtitle_stabilizer import SubtitleStabilizer


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

    def __init__(self, state, region, interval_ms=500):
        super().__init__()
        self.state = state
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

    # ===== Interface tương thích với Controller =====
    def configure(self, settings: RuntimeSettings) -> int:
        """Publish an immutable snapshot; only run() consumes invalidation."""
        with QMutexLocker(self._mutex):
            self._settings = settings
            self._revision += 1
            self._invalidated = True
            return self._revision

    def setInterval(self, ms: int):
        with QMutexLocker(self._mutex):
            self._settings = replace(self._settings, interval_ms=max(100, min(3000, int(ms))))
            self._revision += 1
            self._invalidated = True

    def interval(self) -> int:
        with QMutexLocker(self._mutex):
            return self._settings.interval_ms

    def set_region(self, region: dict):
        with QMutexLocker(self._mutex):
            self._region = region.copy()
            self._revision += 1
            self._invalidated = True

    def set_overlay_rect(self, rect):
        with QMutexLocker(self._mutex):
            self._overlay_rect = rect

    def is_running(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._is_running

    def start_worker(self):
        """Khởi động worker thread nếu chưa chạy"""
        if not self.isRunning():
            with QMutexLocker(self._mutex):
                self._is_running = True
            self.start()

    def stop_worker(self):
        """Dừng an toàn worker thread và dọn dẹp RAM"""
        with QMutexLocker(self._mutex):
            self._is_running = False
            self._revision += 1
            self._invalidated = True
        self.requestInterruption()
        self.wait(3000)
        compact_memory()

    # Hỗ trợ trực tiếp các phương thức start() và stop()
    def start(self, priority=QThread.InheritPriority):
        if self.isRunning():
            return
        with QMutexLocker(self._mutex):
            self._is_running = True
            self._revision += 1
            self._invalidated = True
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
        return snapshot

    def retry_current(self) -> None:
        """Ask the worker to reprocess the current frame as a new revision."""
        with QMutexLocker(self._mutex):
            self._revision += 1
            self._invalidated = True

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

    def _process_frame(self, img_gray, settings: RuntimeSettings, revision: int, service: TranslationService) -> bool:
        """Return whether the frame was idle, preserving memory compaction cadence."""
        if not self._is_current(revision):
            return False
        if time.monotonic() < self._retry_not_before:
            return True
        frame_changed = self._is_frame_changed(img_gray)
        if not frame_changed and (not self._stabilizer.has_pending or self._retry_frame_only):
            if self._prev_text:
                self._emit_current(revision, self.text_unchanged)
            return True
        result = ocr_image(img_gray, lang=SUPPORTED_LANGUAGES.get(settings.source_lang, "en"))
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
        return False

    def run(self):
        # Construction, use and cleanup all happen on this thread. UI only publishes settings.
        service = TranslationService()
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
                        img_gray = self._mask_overlay_numpy(img_gray, region, overlay_rect)
                        idle = self._process_frame(img_gray, settings, revision, service)
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
            service.close()
            self._stabilizer.reset()
            with QMutexLocker(self._mutex):
                self._is_running = False
            compact_memory()
