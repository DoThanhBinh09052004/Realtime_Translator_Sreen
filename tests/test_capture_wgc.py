from dataclasses import replace
from queue import Queue
from threading import Thread, get_ident, Event
from types import SimpleNamespace

import numpy as np
import pytest

from core.blocks.models import CaptureGeometry, Rect, ScreenMapping
from core.capture.models import CaptureContext, WindowIdentity


def context(epoch=1):
    return CaptureContext(epoch, 1, 'window', WindowIdentity(0x100000002, 12, 99),
        CaptureGeometry(Rect(101, 138, 4, 3), ScreenMapping('s', Rect(0, 0, 1000, 800),
                        Rect(0, 0, 1000, 800)), (4, 3)))


class Owner:
    def __init__(self):
        self.queue = Queue()
        self.thread = Thread(target=self.run)
        self.thread.start()

    def run(self):
        while (task := self.queue.get()) is not None:
            call, result = task
            try:
                result.put((True, call()))
            except BaseException as exc:
                result.put((False, exc))

    def call(self, call):
        result = Queue()
        self.queue.put((call, result))
        ok, value = result.get(timeout=5)
        if not ok:
            raise value
        return value

    def close(self):
        self.queue.put(None)
        self.thread.join(5)


class Native:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.handlers = {}
        self.drains = []

    def event(self, handler):
        self.handlers[handler.__name__] = handler
        return handler

    def start_free_threaded(self):
        return self

    def stop(self):
        self.drains.append(('stop', get_ident()))

    def wait(self):
        self.drains.append(('wait', get_ident()))

    def is_finished(self):
        return False

    def frame(self, pixels):
        self.handlers['on_frame_arrived'](SimpleNamespace(frame_buffer=pixels), None)


@pytest.fixture
def source():
    from core.capture.wgc import WgcCaptureSource
    from core.capture.windows import NativeWindowGeometry
    now = [0.]
    geometry = [NativeWindowGeometry(Rect(100, 100, 6, 42), Rect(101, 138, 4, 3), False, True)]
    natives, terminals = [], []
    def factory(**kwargs):
        native = Native(**kwargs)
        natives.append(native)
        return native
    adapter = WgcCaptureSource(native_factory=factory, clock=lambda: now[0],
        geometry_reader=lambda identity: geometry[0], identity_validator=lambda identity: True,
        on_terminal=terminals.append)
    owner = Owner()
    owner.call(lambda: adapter.open(context()))
    yield SimpleNamespace(adapter=adapter, owner=owner, now=now, geometry=geometry,
                          natives=natives, terminal=terminals)
    owner.call(adapter.close)
    owner.close()


def pixels(value=7):
    padded = np.zeros((42, 8, 4), dtype=np.uint8)
    padded[38:41, 1:5] = value
    return padded[:, :6]


def test_capture_bounds_client_crop_and_padded_rows(source):
    source.natives[0].frame(pixels())
    result = source.owner.call(lambda: source.adapter.read_latest(now_s=0))
    assert result.pixels.shape == (3, 4, 4)
    assert np.all(result.pixels == 7)
    assert result.source_size_px == (4, 3) and result.image_origin_px == (0, 0)
    assert not result.pixels.flags.writeable and result.pixels.flags.c_contiguous
    assert source.natives[0].kwargs['window_hwnd'] == 0x100000002
    assert 'window_name' not in source.natives[0].kwargs


def test_static_content_without_callback_remains_valid(source):
    source.natives[0].frame(pixels())
    source.now[0] = 100.
    assert source.owner.call(lambda: source.adapter.read_latest(now_s=100)).sequence == 1
    assert source.adapter.status().phase == 'ready'


def test_timeout_before_first_frame_only(source):
    source.now[0] = 2.01
    assert source.owner.call(lambda: source.adapter.read_latest(now_s=2.01)) is None
    assert source.adapter.status().error.code == 'capture_open_timeout'
    assert len(source.terminal) == 1


@pytest.mark.parametrize('failure', ['minimize', 'hidden', 'closed', 'bad_frame', 'resize'])
def test_minimize_close_and_frame_errors_clear_ready_state(source, failure):
    source.natives[0].frame(pixels())
    source.now[0] = .11
    if failure == 'minimize':
        source.geometry[0] = replace(source.geometry[0], minimized=True)
    elif failure == 'hidden':
        source.geometry[0] = replace(source.geometry[0], visible=False)
    elif failure == 'resize':
        source.geometry[0] = replace(source.geometry[0], client_bounds_px=Rect(101, 138, 3, 3))
    if failure == 'closed':
        source.natives[0].handlers['on_closed']()
    else:
        source.natives[0].frame(np.zeros((2, 2, 4), dtype=np.uint8) if failure == 'bad_frame' else pixels())
    assert source.owner.call(lambda: source.adapter.read_latest(now_s=.11)) is None
    assert source.adapter.status().phase in ('error', 'unavailable')


def test_terminal_failure_relays_once_per_epoch_while_ocr_is_held(source):
    # No owner reads occur: native source loss must reach lifecycle immediately.
    source.natives[0].handlers['on_closed']()
    source.natives[0].handlers['on_closed']()
    source.natives[0].frame(pixels())
    assert len(source.terminal) == 1
    assert source.terminal[0].binding_epoch == 1


def test_old_callback_cannot_overwrite_new_epoch(source):
    old = source.natives[0]
    source.owner.call(source.adapter.close)
    source.owner.call(lambda: source.adapter.open(context(2)))
    old.frame(pixels(99))
    old.handlers['on_closed']()
    assert source.adapter.status().phase == 'opening'
    source.natives[1].frame(pixels(8))
    result = source.owner.call(lambda: source.adapter.read_latest(now_s=0))
    assert result.binding_epoch == 2 and np.all(result.pixels == 8)


def test_callback_buffer_has_capacity_one_and_throttles(source):
    first = pixels(1)
    source.natives[0].frame(first)
    first[:] = 99
    source.now[0] = .01
    source.natives[0].frame(pixels(2))
    assert np.all(source.owner.call(lambda: source.adapter.read_latest(now_s=.01)).pixels == 1)
    source.now[0] = .11
    source.natives[0].frame(pixels(3))
    result = source.owner.call(lambda: source.adapter.read_latest(now_s=.11))
    assert result.sequence == 2 and np.all(result.pixels == 3)


def test_native_stop_and_join_run_outside_gui_and_callback(source):
    with pytest.raises(RuntimeError):
        source.adapter.close()
    callback = Thread(target=lambda: source.natives[0].handlers['on_closed']())
    callback.start()
    callback.join()
    assert source.natives[0].drains == []
    source.owner.call(source.adapter.close)
    assert source.natives[0].drains == [('stop', source.owner.thread.ident), ('wait', source.owner.thread.ident)]


def test_first_frame_timer_relays_without_owner_read():
    from core.capture.wgc import WgcCaptureSource
    adapter = WgcCaptureSource(native_factory=Native, identity_validator=lambda i: True)
    notified = Event()
    adapter._on_terminal = lambda status: notified.set()
    owner = Owner()
    try:
        owner.call(lambda: adapter.open(context()))
        assert notified.wait(2.5)
        assert adapter.status().error.code == 'capture_open_timeout'
    finally:
        owner.call(adapter.close)
        owner.close()


def test_native_thread_death_relays_without_owner_read(source):
    source.natives[0].frame(pixels())
    source.natives[0].is_finished = lambda: True
    from time import monotonic, sleep
    deadline = monotonic()+1.
    while not source.terminal and monotonic() < deadline:
        sleep(.01)
    assert source.terminal[0].error.code == 'capture_native_stopped'


def test_native_terminal_relay_while_owner_is_actually_blocked(source):
    entered, release, notified = Event(), Event(), Event()
    source.adapter._on_terminal = lambda status: (source.terminal.append(status), notified.set())
    def blocked_ocr():
        entered.set()
        assert release.wait(2)
    result = Queue()
    source.owner.queue.put((blocked_ocr, result))
    try:
        assert entered.wait(1)
        source.natives[0].is_finished = lambda: True
        assert notified.wait(1)
        assert not release.is_set()
        assert source.terminal[0].error.code == 'capture_native_stopped'
        assert source.adapter.status().phase == 'error'
    finally:
        release.set()
        assert result.get(timeout=2)[0]


def test_missing_native_dependency_is_terminal_without_desktop_fallback(monkeypatch):
    import builtins
    import mss
    from core.capture.wgc import WgcCaptureSource
    original_import = builtins.__import__
    def importing(name, *args, **kwargs):
        if name == 'windows_capture':
            raise ImportError('missing native wheel')
        return original_import(name, *args, **kwargs)
    desktop_calls, terminal = [], []
    monkeypatch.setattr(builtins, '__import__', importing)
    monkeypatch.setattr(mss, 'mss', lambda: desktop_calls.append(True))
    adapter = WgcCaptureSource(identity_validator=lambda identity: True, on_terminal=terminal.append)
    owner = Owner()
    try:
        owner.call(lambda: adapter.open(context()))
        assert adapter.status().error.code == 'capture_open_failed'
        assert len(terminal) == 1 and not desktop_calls
    finally:
        owner.call(adapter.close)
        owner.close()


def test_slow_native_drain_stays_stopping_and_blocks_reopen(source):
    entered, release = Event(), Event()
    def wait():
        entered.set()
        assert release.wait(5)
    source.natives[0].wait = wait
    completed = Event()
    Thread(target=lambda: (source.owner.call(source.adapter.close), completed.set())).start()
    assert entered.wait(1)
    assert source.adapter.status().phase == 'stopping'
    assert not completed.is_set()
    release.set()
    assert completed.wait(1)
