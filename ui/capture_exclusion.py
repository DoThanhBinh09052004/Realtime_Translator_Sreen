"""Windows display affinity; never silently replace exclusion with a black mask."""
import ctypes
import sys
from ctypes import wintypes
from core.contracts import EngineError

ERROR_MESSAGE = 'Không thể bật overlay theo vị trí chữ. Hãy chọn Phụ đề nổi hoặc kiểm tra phiên bản Windows.'


def _windows_build():
    return sys.getwindowsversion().build if sys.platform == 'win32' else 0


def _user32():
    return ctypes.WinDLL('user32', use_last_error=True)


def set_capture_excluded(hwnd, excluded=True):
    try:
        if _windows_build() < 19041 or not hwnd:
            raise ValueError('Unsupported display affinity')
        api = _user32()
        setter, getter = api.SetWindowDisplayAffinity, api.GetWindowDisplayAffinity
        setter.argtypes, setter.restype = [wintypes.HWND, wintypes.DWORD], wintypes.BOOL
        getter.argtypes, getter.restype = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL
        flag = 0x11 if excluded else 0
        actual = wintypes.DWORD()
        if not setter(hwnd, flag) or not getter(hwnd, ctypes.byref(actual)) or actual.value != flag:
            raise ValueError('Display affinity rejected')
        return None
    except Exception:
        return EngineError('capture_exclusion', ERROR_MESSAGE, False)
