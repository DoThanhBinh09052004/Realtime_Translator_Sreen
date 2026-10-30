"""Physical Win32 geometry and process-lifetime HWND identity (no Qt/native wheel)."""
from dataclasses import dataclass
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import PureWindowsPath
import sys

from core.blocks.models import Rect
from core.capture.models import WindowIdentity


@dataclass(frozen=True)
class WindowChoice:
    identity: WindowIdentity
    title: str
    process_name: str
    available: bool


@dataclass(frozen=True)
class NativeWindowGeometry:
    capture_bounds_px: Rect
    client_bounds_px: Rect
    minimized: bool
    visible: bool
    dpi: int = 96


class WindowUnavailableError(OSError):
    """The identity is alive but currently has no capturable client raster."""


@contextmanager
def _physical_coordinates(user):
    """Temporarily use per-monitor-v2 coordinates without changing Qt's process."""
    previous = user.SetThreadDpiAwarenessContext(-4)
    if not previous:
        raise OSError('Cannot enter physical window coordinate context')
    try:
        yield
    finally:
        user.SetThreadDpiAwarenessContext(previous)


class _Win32Api:
    def __init__(self):
        if sys.platform != 'win32' or sys.maxsize <= 2**32:
            raise OSError('Window capture requires Windows x64')
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
        self.enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        signatures = (
            (self.user, 'EnumWindows', [self.enum_callback, wintypes.LPARAM], wintypes.BOOL),
            (self.user, 'IsWindow', [wintypes.HWND], wintypes.BOOL),
            (self.user, 'IsWindowVisible', [wintypes.HWND], wintypes.BOOL),
            (self.user, 'IsIconic', [wintypes.HWND], wintypes.BOOL),
            (self.user, 'SetThreadDpiAwarenessContext', [ctypes.c_void_p], ctypes.c_void_p),
            (self.user, 'GetDpiForWindow', [wintypes.HWND], wintypes.UINT),
            (self.user, 'GetWindowThreadProcessId', [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            (self.user, 'GetWindowTextLengthW', [wintypes.HWND], ctypes.c_int),
            (self.user, 'GetWindowTextW', [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user, 'GetClientRect', [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            (self.user, 'ClientToScreen', [wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            (self.kernel, 'OpenProcess', [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            (self.kernel, 'CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel, 'GetProcessTimes', [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)]*4, wintypes.BOOL),
            (self.kernel, 'QueryFullProcessImageNameW', [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.dwm, 'DwmGetWindowAttribute', [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD], ctypes.c_long),
        )
        for library, name, args, result in signatures:
            function = getattr(library, name)
            function.argtypes, function.restype = args, result

    def enum_hwnds(self):
        result = []
        callback = self.enum_callback(lambda hwnd, _: result.append(int(hwnd)) or True)
        if not self.user.EnumWindows(callback, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def _process(self, hwnd):
        pid = wintypes.DWORD()
        if not self.user.IsWindow(hwnd) or not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise OSError('Window no longer exists')
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return pid.value, handle

    def identity(self, hwnd):
        pid, handle = self._process(hwnd)
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            return WindowIdentity(int(hwnd), pid, created)
        finally:
            self.kernel.CloseHandle(handle)

    def title(self, hwnd):
        buffer = ctypes.create_unicode_buffer(self.user.GetWindowTextLengthW(hwnd) + 1)
        self.user.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def process_name(self, hwnd):
        _, handle = self._process(hwnd)
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            return PureWindowsPath(buffer.value).name
        finally:
            self.kernel.CloseHandle(handle)

    def selectable(self, hwnd):
        cloaked = wintypes.DWORD()
        result = self.dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return bool(self.user.IsWindowVisible(hwnd)) and result == 0 and not cloaked.value

    def geometry(self, hwnd):
        with _physical_coordinates(self.user):
            return self._physical_geometry(hwnd)

    def _physical_geometry(self, hwnd):
        # Minimized Win32 clients may report zero extent. Do not manufacture a
        # positive rectangle or misclassify this reversible state as HWND loss.
        if self.user.IsIconic(hwnd):
            raise WindowUnavailableError('Window is minimized')
        capture, client, origin = wintypes.RECT(), wintypes.RECT(), wintypes.POINT()
        if self.dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(capture), ctypes.sizeof(capture)):
            raise OSError('Cannot read DWM capture bounds')
        if not self.user.GetClientRect(hwnd, ctypes.byref(client)) or not self.user.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise ctypes.WinError(ctypes.get_last_error())
        return NativeWindowGeometry(
            Rect(capture.left, capture.top, capture.right-capture.left, capture.bottom-capture.top),
            Rect(origin.x+client.left, origin.y+client.top, client.right-client.left, client.bottom-client.top),
            bool(self.user.IsIconic(hwnd)), bool(self.user.IsWindowVisible(hwnd)),
            int(self.user.GetDpiForWindow(hwnd)))


def validate_window_identity(identity: WindowIdentity, *, _api=None) -> bool:
    try:
        return (_api or _Win32Api()).identity(identity.hwnd) == identity
    except (OSError, ValueError, KeyError):
        return False


def read_window_geometry(identity: WindowIdentity, *, _api=None) -> NativeWindowGeometry:
    api = _api or _Win32Api()
    if not validate_window_identity(identity, _api=api):
        raise OSError('Window identity changed or window closed')
    geometry = api.geometry(identity.hwnd)
    if not validate_window_identity(identity, _api=api):
        raise OSError('Window identity changed while reading geometry')
    return geometry


def enumerate_capture_windows(*, _api=None) -> tuple[WindowChoice, ...]:
    api = _api or _Win32Api()
    choices = []
    for hwnd in api.enum_hwnds():
        try:
            identity = api.identity(hwnd)
            if identity.pid == os.getpid() or not api.selectable(hwnd):
                continue
            title = api.title(hwnd)
            if title:
                choices.append(WindowChoice(identity, title, api.process_name(hwnd), True))
        except (OSError, ValueError, KeyError):
            continue  # A window can disappear during enumeration.
    return tuple(choices)
