"""Global Windows hotkeys using RegisterHotKey and Qt native event filter."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from typing import Any

from PyQt5.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, pyqtSignal

# Windows constants
WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

VK_F8 = 0x77
VK_F9 = 0x78

HOTKEY_ID_TOGGLE = 1001
HOTKEY_ID_REGION = 1002


class Win32NativeApi:
    """Wrapper around ctypes user32 functions with pointer-safe signatures."""

    def __init__(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        # BOOL RegisterHotKey(HWND hWnd, int id, UINT fsModifiers, UINT vk)
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL

        # BOOL UnregisterHotKey(HWND hWnd, int id)
        user32.UnregisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
        ]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        self._user32 = user32

    def RegisterHotKey(self, hwnd: Any, hk_id: int, fsModifiers: int, vk: int) -> bool:
        return bool(self._user32.RegisterHotKey(hwnd, hk_id, fsModifiers, vk))

    def UnregisterHotKey(self, hwnd: Any, hk_id: int) -> bool:
        return bool(self._user32.UnregisterHotKey(hwnd, hk_id))


class HotkeyNativeEventFilter(QAbstractNativeEventFilter):
    """Dispatches WM_HOTKEY events to GlobalHotkeys on Qt GUI thread."""

    def __init__(self, hotkeys: GlobalHotkeys) -> None:
        super().__init__()
        self._hotkeys = hotkeys

    def nativeEventFilter(
        self, eventType: bytes | str, message: Any
    ) -> tuple[bool, int]:
        if not message:
            return False, 0
        if eventType in (
            b"windows_generic_MSG",
            "windows_generic_MSG",
            b"windows_dispatcher_MSG",
            "windows_dispatcher_MSG",
        ):
            try:
                addr = int(message)
                msg = wintypes.MSG.from_address(addr)
                if msg.message == WM_HOTKEY:
                    if self._hotkeys._handle_hotkey(int(msg.wParam)):
                        return True, 0
            except Exception:
                pass
        return False, 0


class GlobalHotkeys(QObject):
    """Manages system-wide shortcuts via RegisterHotKey and GUI event filter."""

    toggle_requested = pyqtSignal()
    region_requested = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        native_api: Any = None,
        platform: str | None = None,
        hwnd: Any = None,
    ) -> None:
        super().__init__(parent)
        self._platform = platform if platform is not None else sys.platform
        self._hwnd = hwnd
        self._native_api = native_api
        self._registered_ids: set[int] = set()
        self._event_filter: HotkeyNativeEventFilter | None = None
        self._is_closed = False

    def _get_api(self) -> Any:
        if self._native_api is None:
            self._native_api = Win32NativeApi()
        return self._native_api

    def start(self) -> bool:
        """Register shortcuts and install Qt native event filter."""
        if self._platform != "win32":
            self.error_occurred.emit(
                "Phím tắt toàn hệ thống chỉ hỗ trợ trên hệ điều hành Windows."
            )
            return False

        if self._registered_ids:
            return True

        self._is_closed = False
        api = self._get_api()
        modifiers = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT

        hotkey_defs = [
            (HOTKEY_ID_TOGGLE, VK_F8, "bật/tắt dịch", "Ctrl+Alt+F8"),
            (HOTKEY_ID_REGION, VK_F9, "chọn vùng", "Ctrl+Alt+F9"),
        ]

        any_success = False
        for hk_id, vk, action_desc, key_str in hotkey_defs:
            ok = False
            try:
                ok = api.RegisterHotKey(self._hwnd, hk_id, modifiers, vk)
            except Exception:
                ok = False

            if ok:
                self._registered_ids.add(hk_id)
                any_success = True
            else:
                self.error_occurred.emit(
                    f"Không thể đăng ký phím tắt {key_str} ({action_desc}). "
                    "Phím tắt có thể đang bị trùng với ứng dụng khác."
                )

        if any_success:
            app = QCoreApplication.instance()
            if app is not None and self._event_filter is None:
                self._event_filter = HotkeyNativeEventFilter(self)
                app.installNativeEventFilter(self._event_filter)

        return any_success

    def _handle_hotkey(self, hotkey_id: int) -> bool:
        """Dispatch received hotkey ID. Returns True if handled."""
        if hotkey_id not in self._registered_ids:
            return False
        if hotkey_id == HOTKEY_ID_TOGGLE:
            self.toggle_requested.emit()
            return True
        elif hotkey_id == HOTKEY_ID_REGION:
            self.region_requested.emit()
            return True
        return False

    def close(self) -> None:
        """Unregister shortcuts and remove native event filter. Idempotent."""
        if self._is_closed and not self._registered_ids and self._event_filter is None:
            return

        app = QCoreApplication.instance()
        if app is not None and self._event_filter is not None:
            try:
                app.removeNativeEventFilter(self._event_filter)
            except Exception:
                pass
            self._event_filter = None

        if self._native_api is not None and self._registered_ids:
            for hk_id in list(self._registered_ids):
                try:
                    self._native_api.UnregisterHotKey(self._hwnd, hk_id)
                except Exception:
                    pass
                self._registered_ids.discard(hk_id)

        self._registered_ids.clear()
        self._is_closed = True
