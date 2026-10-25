"""GUI-owned Qt/Win32 monitor pairing by device name, including negative origins."""
import ctypes
import sys
from ctypes import wintypes
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication
from core.blocks.models import Rect, ScreenMapping


def _physical_monitors():
    if sys.platform != 'win32':
        return {}
    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD), ('szDevice', wintypes.WCHAR*32)]
    api = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    api.GetMonitorInfoW.restype = wintypes.BOOL
    api.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
    api.EnumDisplayMonitors.restype = wintypes.BOOL
    result = {}
    def collect(handle, dc, rect, param):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if api.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.rcMonitor
            result[info.szDevice.casefold()] = Rect(r.left, r.top, r.right-r.left, r.bottom-r.top)
        return True
    callback = callback_type(collect)
    if not api.EnumDisplayMonitors(None, None, callback, 0):
        return {}
    return result


class ScreenGeometryProvider(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._screens = set()
        app = QApplication.instance()
        app.screenAdded.connect(self._topology_changed)
        app.screenRemoved.connect(self._topology_changed)
        self._connect_screens()

    def _connect_screens(self):
        current = set(QApplication.screens())
        for screen in current-self._screens:
            screen.geometryChanged.connect(self.changed.emit)
            screen.logicalDotsPerInchChanged.connect(self.changed.emit)
            screen.physicalDotsPerInchChanged.connect(self.changed.emit)
        self._screens = current

    def _topology_changed(self, *args):
        self._connect_screens()
        self.changed.emit()

    def snapshot(self):
        try:
            monitors = _physical_monitors()
        except (OSError, ValueError, AttributeError):
            return ()
        result = []
        for screen in QApplication.screens():
            physical = monitors.get(screen.name().casefold())
            if physical is not None:
                r = screen.geometry()
                result.append(ScreenMapping(screen.name(), Rect(r.x(), r.y(), r.width(), r.height()), physical))
        return tuple(result)
