"""Lazy WGC adapter: native callbacks publish one owned client BGRA raster.

open/read/close belong to a non-GUI worker. Callback and opening timer only
update guarded state and relay terminal status; neither drains native threads.
"""
from threading import RLock, Timer, get_ident, main_thread
from time import monotonic
import sys

import numpy as np

from core.capture.models import CapturedFrame, SourceStatus
from core.capture.windows import read_window_geometry, validate_window_identity, WindowUnavailableError
from core.contracts import EngineError


def _crop_client(pixels, geometry):
    capture, client = geometry.capture_bounds_px, geometry.client_bounds_px
    if (not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8
            or pixels.shape != (capture.height, capture.width, 4)):
        raise ValueError('Native surface must be BGRA8 and match DWM capture bounds')
    if not capture.contains(client):
        raise ValueError('Client lies outside DWM capture bounds')
    x, y = int(client.x-capture.x), int(client.y-capture.y)
    return pixels[y:y+int(client.height), x:x+int(client.width)]


class WgcCaptureSource:
    def __init__(self, *, native_factory=None, clock=monotonic, on_terminal=None,
                 geometry_reader=read_window_geometry, identity_validator=validate_window_identity):
        self._factory, self._clock, self._on_terminal = native_factory, clock, on_terminal
        self._geometry_reader, self._identity_validator = geometry_reader, identity_validator
        self._lock = RLock()
        self._owner = None
        self._native = self._control = self._context = self._latest = self._timer = None
        self._status = SourceStatus(0, 'stopped')
        self._generation = 0
        self._sequence = 0
        self._terminal_sent = False
        self._monitor_timer = None

    def _check_owner(self):
        if get_ident() == main_thread().ident or (self._owner is not None and get_ident() != self._owner):
            raise RuntimeError('Native capture must be accessed on its non-GUI owner thread')

    def _fail(self, generation, code, message, *, phase='error', retryable=False):
        with self._lock:
            if generation != self._generation or self._status.phase not in ('opening', 'ready'):
                return
            self._latest = None
            self._status = status = SourceStatus(self._status.binding_epoch, phase,
                                                 EngineError(code, message, retryable))
            notify = not self._terminal_sent
            self._terminal_sent = True
            if self._timer is not None:
                self._timer.cancel()
            if self._monitor_timer is not None:
                self._monitor_timer.cancel()
        if notify and self._on_terminal is not None:
            # This callback is a signal relay only. Native stop/wait belongs to close().
            try:
                self._on_terminal(status)
            except Exception:
                pass

    def _opening_timeout(self, generation):
        with self._lock:
            if generation != self._generation or self._status.phase != 'opening':
                return
        self._fail(generation, 'capture_open_timeout', 'Không nhận được ảnh cửa sổ trong 2 giây.', retryable=True)

    def _monitor_native(self, generation):
        with self._lock:
            if generation != self._generation or self._status.phase not in ('opening', 'ready'):
                return
            control = self._control
        try:
            if control is not None and control.is_finished():
                self._fail(generation, 'capture_native_stopped', 'Luồng chụp cửa sổ đã dừng. Vui lòng chọn lại.')
                return
        except Exception:
            self._fail(generation, 'capture_native_failed', 'Không thể kiểm tra luồng chụp cửa sổ.')
            return
        with self._lock:
            if generation == self._generation and self._status.phase in ('opening', 'ready'):
                self._monitor_timer = Timer(.1, self._monitor_native, (generation,))
                self._monitor_timer.daemon = True
                self._monitor_timer.start()

    def open(self, context, *, roi_rects_px=None):
        self._check_owner()
        if self._control is not None or self._status.phase not in ('stopped', 'error'):
            raise RuntimeError('Capture source is already open; drain before reopening')
        if context.source_kind != 'window' or context.window is None:
            raise ValueError('WGC requires a concrete window identity')
        with self._lock:
            self._owner, self._context = get_ident(), context
            self._generation += 1
            generation = self._generation
            self._sequence, self._terminal_sent, self._latest = 0, False, None
            self._last_sample = float('-inf')
            self._opened_at = self._clock()
            self._status = SourceStatus(context.binding_epoch, 'opening')
        try:
            if not self._identity_validator(context.window):
                self._fail(generation, 'window_closed', 'Cửa sổ đã đóng hoặc thay đổi. Vui lòng chọn lại.')
                return
            factory = self._factory
            if factory is None:
                if sys.platform != 'win32' or sys.maxsize <= 2**32 or sys.getwindowsversion().build < 19041:
                    raise RuntimeError('WGC requires Windows x64 build 19041 or newer')
                from windows_capture import WindowsCapture
                factory = WindowsCapture
            self._native = native = factory(window_hwnd=context.window.hwnd, cursor_capture=False,
                                           draw_border=False, minimum_update_interval=100)

            @native.event
            def on_frame_arrived(frame, internal_control):
                self._frame_arrived(generation, context, frame)

            @native.event
            def on_closed():
                self._fail(generation, 'window_closed', 'Cửa sổ đã đóng. Vui lòng chọn lại.', phase='unavailable')

            self._control = native.start_free_threaded()
            self._monitor_native(generation)
            with self._lock:
                if self._status.phase == 'opening':
                    self._timer = Timer(max(0., 2.-(self._clock()-self._opened_at)), self._opening_timeout, (generation,))
                    self._timer.daemon = True
                    self._timer.start()
        except Exception:
            self._fail(generation, 'capture_open_failed', 'Không thể mở WGC. Kiểm tra quyền và thư viện Windows Capture.')

    def _frame_arrived(self, generation, context, native_frame):
        with self._lock:
            now = self._clock()
            if (generation != self._generation or self._status.phase not in ('opening', 'ready')
                    or now-self._last_sample < .1):
                return
            self._last_sample = now
        try:
            geometry = self._geometry_reader(context.window)
            if geometry.minimized or not geometry.visible:
                self._fail(generation, 'window_unavailable', 'Cửa sổ đang ẩn hoặc thu nhỏ.', phase='unavailable', retryable=True)
                return
            size = (int(geometry.client_bounds_px.width), int(geometry.client_bounds_px.height))
            if size != context.geometry.image_size_px:
                self._fail(generation, 'capture_geometry_changed', 'Kích thước cửa sổ đã thay đổi.', phase='unavailable', retryable=True)
                return
            pixels = _crop_client(native_frame.frame_buffer, geometry)
            with self._lock:
                if generation != self._generation or self._status.phase not in ('opening', 'ready'):
                    return
                # Release the older buffer before allocating its replacement;
                # the scanner may still own one previous immutable frame.
                self._latest = None
                frame = CapturedFrame(context.binding_epoch, self._sequence+1, pixels, (0, 0), size, now)
                self._latest, self._sequence = frame, frame.sequence
                self._status = SourceStatus(context.binding_epoch, 'ready')
                if self._timer is not None:
                    self._timer.cancel()
        except WindowUnavailableError:
            self._fail(generation, 'window_unavailable', 'Cửa sổ đang ẩn hoặc thu nhỏ.', phase='unavailable', retryable=True)
        except OSError:
            self._fail(generation, 'window_closed', 'Không còn truy cập được cửa sổ. Vui lòng chọn lại.', phase='unavailable')
        except Exception:
            self._fail(generation, 'capture_frame_failed', 'Không thể đọc ảnh BGRA của cửa sổ.')

    def read_latest(self, *, now_s):
        self._check_owner()
        with self._lock:
            timed_out = self._status.phase == 'opening' and self._clock()-self._opened_at >= 2.
            generation = self._generation
        if timed_out:
            self._opening_timeout(generation)
        with self._lock:
            return self._latest if self._status.phase == 'ready' else None

    def status(self):
        with self._lock:
            return self._status

    def close(self):
        self._check_owner()
        with self._lock:
            epoch = self._status.binding_epoch
            self._status = SourceStatus(epoch, 'stopping')
            self._generation += 1
            self._latest = None
            if self._timer is not None:
                self._timer.cancel()
            if self._monitor_timer is not None:
                self._monitor_timer.cancel()
            control = self._control
        # Both calls may block. The lifecycle GUI waits asynchronously and keeps
        # reporting stopping past its 3s drain watchdog; never terminate native.
        if control is not None:
            control.stop()
            control.wait()
        with self._lock:
            self._control = self._native = self._context = self._timer = None
            self._monitor_timer = None
            self._owner = None
            self._status = SourceStatus(epoch, 'stopped')
