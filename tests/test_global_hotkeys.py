"""Tests for GlobalHotkeys – Windows system-wide shortcuts.

Covers:
 - Pointer-safe Win32 function signatures.
 - F8/F9 registration with Ctrl+Alt+MOD_NOREPEAT.
 - WM_HOTKEY message routing to toggle_requested and region_requested.
 - Unknown hotkey IDs ignored.
 - Conflicts leave the non-conflicting action available and emit actionable error.
 - Partial success cleanup on unregistration.
 - Repeat close is idempotent.
 - Unsupported-platform behavior (non-Windows).
 - Never registers real global keys in tests.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import pytest
from PyQt5.QtCore import QCoreApplication

from ui.global_hotkeys import (
    GlobalHotkeys,
    Win32NativeApi,
    HOTKEY_ID_TOGGLE,
    HOTKEY_ID_REGION,
    MOD_CONTROL,
    MOD_ALT,
    MOD_NOREPEAT,
    VK_F8,
    VK_F9,
    WM_HOTKEY,
)


# ---------------------------------------------------------------------------
# Test Fakes
# ---------------------------------------------------------------------------

class FakeNativeApi:
    """Injected Win32 API stub that never touches real Windows hotkey tables."""

    def __init__(self, conflict_vks: set[int] | None = None) -> None:
        self.conflict_vks = set(conflict_vks or [])
        self.registered: dict[tuple[int | None, int], tuple[int, int]] = {}
        self.unregistered: list[tuple[int | None, int]] = []

    def RegisterHotKey(self, hwnd: int | None, hk_id: int, fsModifiers: int, vk: int) -> bool:
        if vk in self.conflict_vks or hk_id in self.conflict_vks:
            return False
        self.registered[(hwnd, hk_id)] = (fsModifiers, vk)
        return True

    def UnregisterHotKey(self, hwnd: int | None, hk_id: int) -> bool:
        key = (hwnd, hk_id)
        if key in self.registered:
            del self.registered[key]
            self.unregistered.append(key)
            return True
        return False


def _simulate_msg(hotkey_obj: GlobalHotkeys, msg_code: int, w_param: int, l_param: int = 0):
    """Deliver a simulated Windows MSG directly to the installed native event filter."""
    msg = wintypes.MSG(None, msg_code, w_param, l_param, 0, wintypes.POINT(0, 0))
    filt = hotkey_obj._event_filter
    if filt is None:
        return False, 0
    return filt.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWin32Signatures:
    """Win32 API signatures must be pointer-safe and strongly typed."""

    def test_win32_native_api_argtypes_and_restype(self):
        api = Win32NativeApi()
        user32 = api._user32

        # RegisterHotKey(HWND, int, UINT, UINT) -> BOOL
        assert user32.RegisterHotKey.restype == wintypes.BOOL
        assert user32.RegisterHotKey.argtypes == [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]

        # UnregisterHotKey(HWND, int) -> BOOL
        assert user32.UnregisterHotKey.restype == wintypes.BOOL
        assert user32.UnregisterHotKey.argtypes == [
            wintypes.HWND,
            ctypes.c_int,
        ]


class TestGlobalHotkeysRegistration:
    """Registration of F8/F9 with modifiers and native filter setup."""

    def test_registration_with_ctrl_alt_norepeat(self, qtbot):
        fake_api = FakeNativeApi()
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")

        success = hotkeys.start()
        assert success is True
        assert len(fake_api.registered) == 2

        expected_mods = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
        assert fake_api.registered[(None, HOTKEY_ID_TOGGLE)] == (expected_mods, VK_F8)
        assert fake_api.registered[(None, HOTKEY_ID_REGION)] == (expected_mods, VK_F9)
        assert hotkeys._event_filter is not None

        hotkeys.close()

    def test_wm_hotkey_routing(self, qtbot):
        fake_api = FakeNativeApi()
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")
        hotkeys.start()

        toggle_calls = []
        region_calls = []
        hotkeys.toggle_requested.connect(lambda: toggle_calls.append(True))
        hotkeys.region_requested.connect(lambda: region_calls.append(True))

        # Deliver F8 (toggle)
        consumed, _ = _simulate_msg(hotkeys, WM_HOTKEY, HOTKEY_ID_TOGGLE)
        assert consumed is True
        assert len(toggle_calls) == 1
        assert len(region_calls) == 0

        # Deliver F9 (region)
        consumed, _ = _simulate_msg(hotkeys, WM_HOTKEY, HOTKEY_ID_REGION)
        assert consumed is True
        assert len(toggle_calls) == 1
        assert len(region_calls) == 1

        hotkeys.close()

    def test_unknown_hotkey_id_ignored(self, qtbot):
        fake_api = FakeNativeApi()
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")
        hotkeys.start()

        toggle_calls = []
        region_calls = []
        hotkeys.toggle_requested.connect(lambda: toggle_calls.append(True))
        hotkeys.region_requested.connect(lambda: region_calls.append(True))

        # Unknown ID 9999
        consumed, _ = _simulate_msg(hotkeys, WM_HOTKEY, 9999)
        assert consumed is False
        assert len(toggle_calls) == 0
        assert len(region_calls) == 0

        # Non-WM_HOTKEY message (e.g. WM_KEYDOWN 0x0100)
        consumed, _ = _simulate_msg(hotkeys, 0x0100, HOTKEY_ID_TOGGLE)
        assert consumed is False
        assert len(toggle_calls) == 0

        hotkeys.close()

    def test_conflict_leaves_other_available_and_emits_error(self, qtbot):
        # VK_F8 conflicts (fails), VK_F9 succeeds
        fake_api = FakeNativeApi(conflict_vks={VK_F8})
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")

        errors = []
        hotkeys.error_occurred.connect(lambda err: errors.append(err))

        success = hotkeys.start()
        # Still returns True because one action succeeded
        assert success is True
        assert len(fake_api.registered) == 1
        assert (None, HOTKEY_ID_REGION) in fake_api.registered

        # Actionable error reported for F8 in Vietnamese
        assert len(errors) == 1
        assert "Ctrl+Alt+F8" in errors[0]
        assert "trùng" in errors[0].lower() or "không thể" in errors[0].lower()

        # F9 is still routed properly
        region_calls = []
        hotkeys.region_requested.connect(lambda: region_calls.append(True))
        consumed, _ = _simulate_msg(hotkeys, WM_HOTKEY, HOTKEY_ID_REGION)
        assert consumed is True
        assert len(region_calls) == 1

        hotkeys.close()

    def test_both_conflicted_fails_start(self, qtbot):
        fake_api = FakeNativeApi(conflict_vks={VK_F8, VK_F9})
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")

        errors = []
        hotkeys.error_occurred.connect(lambda err: errors.append(err))

        success = hotkeys.start()
        assert success is False
        assert len(fake_api.registered) == 0
        assert len(errors) == 2

        hotkeys.close()


class TestGlobalHotkeysTeardown:
    """Cleanup, partial success cleanup, repeat close, and platform checks."""

    def test_partial_success_cleanup(self, qtbot):
        # Only F9 registered
        fake_api = FakeNativeApi(conflict_vks={VK_F8})
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")
        hotkeys.start()
        assert (None, HOTKEY_ID_REGION) in fake_api.registered

        hotkeys.close()
        # Only F9 unregistered
        assert fake_api.unregistered == [(None, HOTKEY_ID_REGION)]
        assert len(fake_api.registered) == 0

    def test_repeat_close_is_idempotent(self, qtbot):
        fake_api = FakeNativeApi()
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")
        hotkeys.start()

        hotkeys.close()
        assert len(fake_api.unregistered) == 2

        # Second close should do nothing and not raise
        hotkeys.close()
        assert len(fake_api.unregistered) == 2

    def test_unsupported_platform_behavior(self, qtbot):
        fake_api = FakeNativeApi()
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="linux")

        errors = []
        hotkeys.error_occurred.connect(lambda err: errors.append(err))

        success = hotkeys.start()
        assert success is False
        assert len(fake_api.registered) == 0
        assert len(errors) == 1
        assert "Windows" in errors[0]

        hotkeys.close()
