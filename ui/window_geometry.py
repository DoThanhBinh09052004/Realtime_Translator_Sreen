"""GUI-owned 100ms physical window geometry poll and 200ms hard-rebind debounce."""
from time import monotonic

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal

from core.blocks.models import CaptureGeometry
from core.capture.models import CaptureContext
from core.capture.windows import read_window_geometry, WindowUnavailableError
from core.contracts import EngineError
from ui.screen_geometry import ScreenGeometryProvider


class WindowGeometryProvider(QObject):
    context_changed = pyqtSignal(object)
    source_unavailable = pyqtSignal(object)

    def __init__(self, parent=None, *, screen_provider=None, geometry_reader=None, clock=monotonic):
        super().__init__(parent)
        self._screens = screen_provider or ScreenGeometryProvider(self)
        self._read = geometry_reader or read_window_geometry
        self._clock = clock
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.poll)
        self._identity = self._profile = self._context = None
        self._pending = None
        self._error_code = None
        self._closed = False
        self._epoch, self._sequence = 0, 0
        self._bound_signature = None

    def _check_gui(self):
        if QThread.currentThread() != self.thread():
            raise RuntimeError('Window geometry must be read on its GUI owner thread')

    def clear_binding(self):
        self._check_gui()
        self._timer.stop()
        self._identity = self._profile = self._context = self._pending = None
        self._error_code = None
        self._bound_signature = None

    def set_binding(self, profile, identity, binding_epoch):
        self._check_gui()
        self.clear_binding()
        self._profile, self._identity = profile, identity
        self._epoch, self._sequence, self._closed = binding_epoch, 0, False
        if profile.source_kind != 'window' or identity is None:
            self._unavailable('window_not_selected', 'Vui lòng chọn cửa sổ.', False)
            return
        self.poll()
        self._timer.start()

    def _unavailable(self, code, message, retryable=True):
        self._pending = None
        if self._error_code != code:
            self._error_code = code
            self.source_unavailable.emit(EngineError(code, message, retryable))

    @staticmethod
    def _signature(geometry):
        # Origin only does not change raster semantics. Screen origin/topology,
        # physical/logical scale and source extent require a fresh native epoch.
        return geometry.image_size_px, geometry.screen

    def poll(self):
        self._check_gui()
        if self._identity is None or self._closed:
            return
        try:
            native = self._read(self._identity)
        except WindowUnavailableError:
            self._unavailable('window_unavailable', 'Cửa sổ đang ẩn hoặc thu nhỏ.')
            return
        except (OSError, ValueError):
            self._closed = True
            self._unavailable('window_closed', 'Cửa sổ đã đóng hoặc thay đổi. Vui lòng chọn lại.', False)
            return
        if native.minimized or not native.visible:
            self._unavailable('window_unavailable', 'Cửa sổ đang ẩn hoặc thu nhỏ.')
            return
        client = native.client_bounds_px
        screens = tuple(screen for screen in self._screens.snapshot() if screen.physical_rect.contains(client))
        if len(screens) != 1:
            self._unavailable('window_cross_monitor', 'Cửa sổ phải nằm trọn trên một màn hình.')
            return
        geometry = CaptureGeometry(client, screens[0], (int(client.width), int(client.height)))
        signature = self._signature(geometry), native.dpi
        changed = self._context is not None and signature != self._bound_signature
        if changed or self._error_code is not None:
            if self._error_code is None:
                self._unavailable('capture_geometry_changed', 'Hình học cửa sổ đã thay đổi.')
            if self._pending is None or self._pending[0] != signature:
                self._pending = signature, self._clock()
                return
            if self._clock()-self._pending[1] < .2:
                return
            self._epoch += 1
            self._pending = None
            self._error_code = None
        elif self._context is not None and geometry == self._context.geometry:
            return
        self._sequence += 1
        self._bound_signature = signature
        self._context = CaptureContext(self._epoch, self._sequence, 'window', self._identity, geometry)
        self.context_changed.emit(self._context)
