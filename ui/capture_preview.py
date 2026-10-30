"""One full-source preview, including native cleanup, owned by a QThread."""
import time
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage
from core.capture.source import create_capture_source
from core.contracts import EngineError


class CapturePreviewWorker(QThread):
    preview_ready = pyqtSignal(object, object)
    error_occurred = pyqtSignal(object)
    shutdown_finished = pyqtSignal()

    def __init__(self, profile, context, parent=None):
        super().__init__(parent)
        self.profile, self.context = profile, context
        self.finished.connect(self.shutdown_finished.emit)

    def request_stop(self):
        self.requestInterruption()

    def run(self):
        source = None
        try:
            source = create_capture_source(self.context)
            source.open(self.context, roi_rects_px=None)
            deadline = time.monotonic() + 2
            while not self.isInterruptionRequested():
                frame = source.read_latest(now_s=time.monotonic())
                status = source.status()
                if status.phase in ('error', 'unavailable'):
                    self.error_occurred.emit(status.error or EngineError('capture', 'Nguồn chụp chưa sẵn sàng.', True))
                    return
                if frame is not None:
                    if (frame.binding_epoch != self.context.binding_epoch
                            or frame.source_size_px != self.context.geometry.image_size_px
                            or frame.image_origin_px != (0, 0)):
                        raise ValueError('Preview must cover the current complete source')
                    pixels = frame.pixels
                    image = QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0], QImage.Format_ARGB32).copy()
                    if not self.isInterruptionRequested():
                        self.preview_ready.emit(image, self.context)
                    return
                if time.monotonic() >= deadline:
                    self.error_occurred.emit(EngineError('capture_timeout', 'Không nhận được ảnh. Chọn nguồn hoặc thử lại.', True))
                    return
                self.msleep(20)
        except Exception:
            self.error_occurred.emit(EngineError('capture', 'Không thể mở ảnh nguồn. Chọn nguồn hoặc thử lại.', True))
        finally:
            if source is not None:
                source.close()
