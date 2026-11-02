from types import SimpleNamespace


def test_affinity_success_restore_and_failures(monkeypatch):
    from ui import capture_exclusion as policy
    calls = []
    class Fn:
        def __init__(self, fn): self.fn = fn
        def __call__(self, *args): return self.fn(*args)
    def get(hwnd, out):
        out._obj.value = calls[-1]
        return 1
    api = SimpleNamespace(SetWindowDisplayAffinity=Fn(lambda hwnd, value: calls.append(value) or 1),
                          GetWindowDisplayAffinity=Fn(get))
    monkeypatch.setattr(policy, '_windows_build', lambda: 19041)
    monkeypatch.setattr(policy, '_user32', lambda: api)
    assert policy.set_capture_excluded(123) is None
    assert policy.set_capture_excluded(123, False) is None
    assert calls == [0x11, 0]
    monkeypatch.setattr(policy, '_windows_build', lambda: 19040)
    assert policy.set_capture_excluded(123).code == 'capture_exclusion'
    monkeypatch.setattr(policy, '_windows_build', lambda: 19041)
    api.SetWindowDisplayAffinity = Fn(lambda *a: 0)
    assert policy.set_capture_excluded(123).code == 'capture_exclusion'
    api.SetWindowDisplayAffinity = Fn(lambda *a: 1)
    assert policy.set_capture_excluded(123).code == 'capture_exclusion'


def test_main_capture_mask_uses_physical_screen_coordinates():
    from main import sync_capture_overlay_mask
    from core.blocks.models import Rect, ScreenMapping, CaptureGeometry
    from core.capture.models import CaptureContext, CaptureProfile, CaptureRegion, NormalizedRect
    from unittest.mock import Mock
    screen = ScreenMapping('left', Rect(-1000, 0, 1000, 600), Rect(-1500, 0, 1500, 900))
    geometry = CaptureGeometry(screen.physical_rect, screen, (1500, 900))
    regions = (CaptureRegion('a', 'left', NormalizedRect(0, 0, .5, 1), True), CaptureRegion('b', 'right', NormalizedRect(.5, 0, .5, 1), True))
    worker = Mock(); worker.capture_profile = CaptureProfile(1, 'desktop', 'left', None, regions, ())
    worker.capture_context = CaptureContext(1, 1, 'desktop', None, geometry)
    sync_capture_overlay_mask(worker, (-600, 100, 200, 100), None)
    worker.set_overlay_rect.assert_called_with((-900, 150, 300, 150))
    worker.capture_profile = CaptureProfile(1, 'window', None, 'game', regions, ())
    sync_capture_overlay_mask(worker, (-600, 100, 200, 100), None)
    worker.set_overlay_rect.assert_called_with(None)
