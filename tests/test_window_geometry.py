from dataclasses import replace
from types import SimpleNamespace

from core.blocks.models import Rect, ScreenMapping
from core.capture.models import CaptureProfile, WindowIdentity


def provider(qtbot):
    from ui.window_geometry import WindowGeometryProvider
    from core.capture.windows import NativeWindowGeometry
    now = [0.]
    native = [NativeWindowGeometry(Rect(10, 10, 120, 130), Rect(20, 40, 100, 90), False, True)]
    screens = [ScreenMapping('s', Rect(0, 0, 800, 640), Rect(0, 0, 1000, 800))]
    def read(identity):
        if isinstance(native[0], Exception):
            raise native[0]
        return native[0]
    result = WindowGeometryProvider(screen_provider=SimpleNamespace(snapshot=lambda: tuple(screens)),
                                    geometry_reader=read, clock=lambda: now[0])
    contexts, errors = [], []
    result.context_changed.connect(contexts.append)
    result.source_unavailable.connect(errors.append)
    result.set_binding(CaptureProfile(1, 'window', None, 'title', (), ()), WindowIdentity(2, 3, 4), 7)
    return result, native, screens, now, contexts, errors


def test_move_emits_geometry_without_new_binding_epoch(qtbot):
    p, native, screens, now, contexts, errors = provider(qtbot)
    try:
        assert contexts[0].binding_epoch == 7
        native[0] = replace(native[0], client_bounds_px=Rect(30, 50, 100, 90))
        p.poll()
        assert contexts[-1].binding_epoch == 7
        assert contexts[-1].geometry_sequence == 2
        assert contexts[-1].geometry.region_px == Rect(30, 50, 100, 90)
        assert not errors
    finally:
        p.clear_binding()


def test_resize_or_dpi_requires_new_binding(qtbot):
    p, native, screens, now, contexts, errors = provider(qtbot)
    try:
        native[0] = replace(native[0], client_bounds_px=Rect(20, 40, 110, 90))
        p.poll()
        assert len(errors) == 1 and len(contexts) == 1
        now[0] = .1
        native[0] = replace(native[0], client_bounds_px=Rect(20, 40, 120, 90))
        p.poll()
        now[0] = .25
        p.poll()
        assert len(contexts) == 1
        now[0] = .31
        p.poll()
        assert contexts[-1].binding_epoch == 8
        screens[0] = replace(screens[0], logical_rect=Rect(0, 0, 1000, 800))
        p.poll()
        assert len(errors) == 2
        now[0] = .52
        p.poll()
        assert contexts[-1].binding_epoch == 9
    finally:
        p.clear_binding()


def test_cross_monitor_window_is_unavailable(qtbot):
    p, native, screens, now, contexts, errors = provider(qtbot)
    try:
        native[0] = replace(native[0], client_bounds_px=Rect(950, 40, 100, 90))
        p.poll()
        p.poll()
        assert len(errors) == 1 and errors[0].code == 'window_cross_monitor'
        assert len(contexts) == 1
    finally:
        p.clear_binding()


def test_minimize_restore_rebinds_and_close_never_reselects(qtbot):
    p, native, screens, now, contexts, errors = provider(qtbot)
    try:
        original = native[0]
        native[0] = replace(original, minimized=True)
        p.poll()
        p.poll()
        assert len(errors) == 1
        native[0] = original
        p.poll()
        now[0] = .21
        p.poll()
        assert contexts[-1].binding_epoch == 8
        native[0] = OSError('closed')
        p.poll()
        native[0] = original
        now[0] = 5
        p.poll()
        assert contexts[-1].binding_epoch == 8
        assert errors[-1].code == 'window_closed'
    finally:
        p.clear_binding()


def test_window_dpi_change_invalidates_even_if_screen_mapping_unchanged(qtbot):
    p, native, screens, now, contexts, errors = provider(qtbot)
    try:
        native[0] = replace(native[0], dpi=120)
        p.poll()
        assert errors[-1].code == 'capture_geometry_changed'
        now[0] = .21
        p.poll()
        assert contexts[-1].binding_epoch == 8
    finally:
        p.clear_binding()


def test_real_minimized_zero_raster_error_allows_restore(qtbot):
    from core.capture.windows import WindowUnavailableError
    p, native, screens, now, contexts, errors = provider(qtbot)
    try:
        original = native[0]
        native[0] = WindowUnavailableError('minimized')
        p.poll()
        assert errors[-1].code == 'window_unavailable'
        native[0] = original
        p.poll()
        now[0] = .21
        p.poll()
        assert contexts[-1].binding_epoch == 8
    finally:
        p.clear_binding()
