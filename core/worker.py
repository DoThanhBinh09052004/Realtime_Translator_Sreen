import time
import cv2
import numpy as np
import mss
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from engines.ocr import ocr_image
from engines.translator import translate
from core.config import SUPPORTED_LANGUAGES


class TranslationWorker(QThread):
    """
    Worker chạy ngầm trên QThread độc lập.
    Đảm nhận toàn bộ chu trình: Chụp màn hình -> Nhận diện thay đổi ảnh -> OCR -> Dịch thuật.
    Không bao giờ gây gián đoạn hay đơ giao diện PyQt5.
    """

    # Signals gửi về UI Main Thread
    text_translated = pyqtSignal(str)
    text_unchanged = pyqtSignal()
    error_occurred = pyqtSignal(str)
    status_updated = pyqtSignal(str)

    def __init__(self, state, region, interval_ms=500):
        super().__init__()
        self.state = state
        self._region = region.copy()
        self._interval_ms = interval_ms
        self._is_running = False
        self._mutex = QMutex()

        self._prev_frame_thumb = None
        self._prev_text = ""
        self._prev_source = None
        self._prev_target = None
        self._overlay_rect = None  # (x, y, w, h)

    # ===== Interface tương thích với Controller =====
    def setInterval(self, ms: int):
        with QMutexLocker(self._mutex):
            self._interval_ms = max(50, int(ms))

    def interval(self) -> int:
        with QMutexLocker(self._mutex):
            return self._interval_ms

    def set_region(self, region: dict):
        with QMutexLocker(self._mutex):
            self._region = region.copy()
            self._prev_frame_thumb = None
            self._prev_text = ""

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
        """Dừng an toàn worker thread"""
        with QMutexLocker(self._mutex):
            self._is_running = False
        self.requestInterruption()
        self.wait(3000)

    # Hỗ trợ trực tiếp các phương thức start() và stop()
    def start(self, priority=QThread.InheritPriority):
        with QMutexLocker(self._mutex):
            self._is_running = True
        super().start(priority)

    def stop(self):
        self.stop_worker()

    # ===== Change Detection & Masking =====
    def _mask_overlay_numpy(self, img, region, overlay_rect):
        """Che mờ vùng overlay phụ đề nếu nằm đè lên vùng chụp để tránh OCR chính nó"""
        if not overlay_rect:
            return img

        ox, oy, ow, oh = overlay_rect
        rx, ry = region["left"], region["top"]

        x1 = max(0, ox - rx)
        y1 = max(0, oy - ry)
        x2 = min(img.shape[1], x1 + ow)
        y2 = min(img.shape[0], y1 + oh)

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
    def run(self):
        """Chạy vòng lặp nền độc lập"""
        with mss.mss() as sct:
            while True:
                # Đọc cấu hình thread-safe
                with QMutexLocker(self._mutex):
                    if not self._is_running or self.isInterruptionRequested():
                        break
                    region = self._region.copy()
                    interval = self._interval_ms
                    overlay_rect = self._overlay_rect
                    source_lang = self.state.source
                    target_lang = self.state.target

                # Nếu người dùng đổi ngôn ngữ -> reset cache để dịch ngay lập tức
                if self._prev_source != source_lang or self._prev_target != target_lang:
                    self._prev_text = ""
                    self._prev_frame_thumb = None
                    self._prev_source = source_lang
                    self._prev_target = target_lang

                start_time = time.time()

                try:
                    if region.get("width", 0) <= 0 or region.get("height", 0) <= 0:
                        time.sleep(0.1)
                        continue

                    monitor = {
                        "top": int(region["top"]),
                        "left": int(region["left"]),
                        "width": int(region["width"]),
                        "height": int(region["height"])
                    }

                    # 1. Chụp màn hình
                    img_raw = sct.grab(monitor)
                    img = np.array(img_raw)
                    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

                    # 2. Mask overlay nếu bị trùng
                    img_gray = self._mask_overlay_numpy(img_gray, region, overlay_rect)

                    # 3. Kiểm tra biến động khung hình
                    frame_changed = self._is_frame_changed(img_gray)

                    if not frame_changed and self._prev_text:
                        # Màn hình tĩnh, giữ hiển thị overlay hiện tại
                        self.text_unchanged.emit()
                    elif frame_changed:
                        # 4. Màn hình thay đổi -> Thực hiện OCR
                        # shortcut: OCR và dịch chạy tuần tự trong worker loop, nâng cấp sang queue nếu cần >20 FPS.
                        ocr_lang = SUPPORTED_LANGUAGES.get(source_lang, 'en')
                        text = ocr_image(img_gray, lang=ocr_lang).strip()

                        if not text:
                            pass
                        elif text != self._prev_text:
                            # 5. Có văn bản mới -> Dịch ngầm
                            translated = translate(
                                text,
                                source_lang=source_lang,
                                target_lang=target_lang
                            )
                            if translated:
                                self.text_translated.emit(translated)
                            self._prev_text = text
                        else:
                            self.text_unchanged.emit()

                except Exception as e:
                    self.error_occurred.emit(str(e))

                # 6. Tính thời gian nghỉ để duy trì đúng tần số
                elapsed_ms = (time.time() - start_time) * 1000
                sleep_needed_ms = max(20, interval - elapsed_ms)
                time.sleep(sleep_needed_ms / 1000.0)
