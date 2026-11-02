from dataclasses import replace
from types import SimpleNamespace
import os

from core.capture.models import WindowIdentity


def api():
    identities = {2: WindowIdentity(2, 12, 120), 3: WindowIdentity(3, 13, 130)}
    return SimpleNamespace(enum_hwnds=lambda: (2, 3), identity=lambda h: identities[h],
        title=lambda h: 'duplicate', process_name=lambda h: 'game.exe',
        selectable=lambda h: True, identities=identities)


def test_duplicate_titles_and_title_change_keep_hwnd_identity():
    from core.capture.windows import enumerate_capture_windows
    native = api()
    first = enumerate_capture_windows(_api=native)
    assert [c.identity.hwnd for c in first] == [2, 3]
    native.title = lambda h: 'renamed' if h == 2 else 'duplicate'
    second = enumerate_capture_windows(_api=native)
    assert first[0].identity == second[0].identity
    assert second[0].title == 'renamed'


def test_reused_hwnd_rejected():
    from core.capture.windows import validate_window_identity
    native = api()
    old = native.identity(2)
    assert validate_window_identity(old, _api=native)
    native.identities[2] = replace(old, process_started_100ns=121)
    assert not validate_window_identity(old, _api=native)
    native.identities.pop(2)
    assert not validate_window_identity(old, _api=native)


def test_hidden_cloaked_and_application_windows_excluded():
    from core.capture.windows import enumerate_capture_windows
    native = api()
    native.identities[3] = WindowIdentity(3, os.getpid(), 99)
    assert [c.identity.hwnd for c in enumerate_capture_windows(_api=native)] == [2]
    native.selectable = lambda h: False
    assert enumerate_capture_windows(_api=native) == ()


def test_geometry_revalidates_identity_before_read():
    from core.capture.windows import read_window_geometry
    native = api()
    native.geometry = lambda h: 'geometry'
    identity = native.identity(2)
    assert read_window_geometry(identity, _api=native) == 'geometry'
    native.identities[2] = replace(identity, pid=999)
    import pytest
    with pytest.raises(OSError):
        read_window_geometry(identity, _api=native)


def test_physical_coordinate_context_restored_on_geometry_failure():
    from core.capture.windows import _physical_coordinates
    import pytest
    calls = []
    def context(value):
        calls.append(value)
        return 12345
    with pytest.raises(ValueError):
        with _physical_coordinates(SimpleNamespace(SetThreadDpiAwarenessContext=context)):
            raise ValueError('failed read')
    assert calls == [-4, 12345]


def test_minimized_native_window_has_no_client_raster():
    from core.capture.windows import _Win32Api, WindowUnavailableError
    import pytest
    native = object.__new__(_Win32Api)
    native.user = SimpleNamespace(IsIconic=lambda hwnd: True)
    # No DWM/client API is available: minimized Win32 clients can have zero size.
    with pytest.raises(WindowUnavailableError):
        native._physical_geometry(2)
