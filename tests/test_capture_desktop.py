from dataclasses import replace
from threading import Thread

import numpy as np
import pytest

from core.blocks.models import CaptureGeometry, Rect, ScreenMapping
from core.capture.models import CaptureContext


def context():
    bounds = Rect(-300, 40, 120, 80)
    screen = ScreenMapping('left', bounds, bounds)
    return CaptureContext(7, 1, 'desktop', None, CaptureGeometry(bounds, screen, (120, 80)))


class FakeMss:
    def __init__(self):
        self.grabs = []
        self.closed = 0
        self.buffer = None

    def grab(self, region):
        self.grabs.append(region)
        self.buffer = np.full((region['height'], region['width'], 4), 51, np.uint8)
        return self.buffer

    def close(self):
        self.closed += 1


def source(fake=None, **kwargs):
    from core.capture.desktop import DesktopCaptureSource
    fake = fake or FakeMss()
    return DesktopCaptureSource(mss_factory=lambda: fake, **kwargs), fake


def test_one_grab_for_three_regions():
    adapter, fake = source()
    adapter.open(context(), roi_rects_px=(Rect(10, 10, 15, 10), Rect(40, 20, 10, 10), Rect(90, 50, 10, 10)))
    frame = adapter.read_latest(now_s=12.5)
    assert fake.grabs == [dict(left=-290, top=50, width=90, height=50)]
    assert frame.image_origin_px == (10, 10)
    assert frame.source_size_px == (120, 80)
    assert frame.captured_at_s == 12.5
    assert frame.binding_epoch == 7
    assert frame.pixels.shape == (50, 90, 4)
    assert adapter.status().phase == 'ready'
    adapter.close()
    assert fake.closed == 1
    assert adapter.status().phase == 'stopped'


def test_preview_reads_full_source_instead_of_runtime_union():
    adapter, fake = source()
    adapter.open(context(), roi_rects_px=None)
    frame = adapter.read_latest(now_s=1)
    assert fake.grabs == [dict(left=-300, top=40, width=120, height=80)]
    assert frame.image_origin_px == (0, 0)
    adapter.close()


@pytest.mark.parametrize('rects', [(), (Rect(-1, 0, 5, 5),), (Rect(119, 0, 5, 5),), (Rect(.5, 0, 5, 5),)])
def test_invalid_runtime_regions_do_not_open_native_capture(rects):
    from core.capture.desktop import DesktopCaptureSource
    calls = []
    adapter = DesktopCaptureSource(mss_factory=lambda: calls.append(True))
    with pytest.raises(ValueError):
        adapter.open(context(), roi_rects_px=rects)
    assert calls == []


def test_frames_are_owned_readonly_and_sequences_increase():
    adapter, fake = source()
    adapter.open(context())
    first = adapter.read_latest(now_s=1)
    fake.buffer[:] = 0
    second = adapter.read_latest(now_s=2)
    assert np.all(first.pixels == 51)
    assert not first.pixels.flags.writeable
    assert second.sequence > first.sequence
    adapter.close()
    assert adapter.read_latest(now_s=3) is None


def test_mss_native_failure_is_terminal_without_fallback():
    class Broken(FakeMss):
        def grab(self, region):
            raise RuntimeError('private native details')
    terminal = []
    adapter, fake = source(Broken(), on_terminal=terminal.append)
    adapter.open(context())
    assert adapter.read_latest(now_s=1) is None
    assert adapter.status().phase == 'error'
    assert adapter.status().error.code == 'capture_failed'
    assert len(terminal) == 1
    assert adapter.read_latest(now_s=2) is None
    adapter.close()
    assert fake.closed == 1


def test_capture_access_stays_on_open_owner_thread():
    adapter, fake = source()
    adapter.open(context())
    errors = []
    def wrong_thread():
        for call in (lambda: adapter.read_latest(now_s=1), adapter.close):
            try:
                call()
            except RuntimeError as error:
                errors.append(error)
    thread = Thread(target=wrong_thread)
    thread.start()
    thread.join()
    assert len(errors) == 2
    assert fake.grabs == []
    adapter.close()


def test_factory_desktop_is_lazy_and_window_never_falls_back(monkeypatch):
    import mss
    from core.capture.source import create_capture_source
    calls = []
    monkeypatch.setattr(mss, 'mss', lambda: calls.append(True))
    adapter = create_capture_source(context())
    assert calls == []
    assert adapter.status().phase == 'stopped'
    from core.capture.wgc import WgcCaptureSource
    window_adapter = create_capture_source(replace(context(), source_kind='window'))
    assert isinstance(window_adapter, WgcCaptureSource)
    assert window_adapter.status().phase == 'stopped'
    assert calls == []
