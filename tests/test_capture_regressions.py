"""Bounded lifetime and stale-callback regression checks for release."""
from dataclasses import replace
import gc
import weakref

import numpy as np


def test_one_hundred_native_rebinds_release_buffers_and_ignore_retired_callbacks():
    from core.capture.wgc import WgcCaptureSource
    from core.capture.windows import NativeWindowGeometry
    from core.blocks.models import Rect
    from test_capture_wgc import Native, Owner, context, pixels
    natives, terminals, frames = [], [], []
    now = [0.]
    def factory(**kwargs):
        native = Native(**kwargs)
        natives.append(native)
        return native
    adapter = WgcCaptureSource(native_factory=factory, clock=lambda: now[0],
        geometry_reader=lambda identity: NativeWindowGeometry(Rect(100, 100, 6, 42), Rect(101, 138, 4, 3), False, True),
        identity_validator=lambda identity: True, on_terminal=terminals.append)
    owner = Owner()
    try:
        for epoch in range(1, 101):
            owner.call(lambda: adapter.open(context(epoch)))
            for retired in natives[:-1]:
                retired.frame(pixels(99))
                retired.handlers['on_closed']()
            assert adapter.status().phase == 'opening'
            natives[-1].frame(pixels(epoch))
            frame = owner.call(lambda: adapter.read_latest(now_s=now[0]))
            assert frame.binding_epoch == epoch and np.all(frame.pixels == epoch)
            frames.append(weakref.ref(frame))
            del frame
            owner.call(adapter.close)
            natives[-1].frame(pixels(99))
            natives[-1].handlers['on_closed']()
            assert adapter.status().phase == 'stopped'
            assert owner.call(lambda: adapter.read_latest(now_s=now[0])) is None
            now[0] += 1
        gc.collect()
        assert all(reference() is None for reference in frames)
        assert not terminals
        assert all(native.drains == [('stop', owner.thread.ident), ('wait', owner.thread.ident)] for native in natives)
    finally:
        owner.call(adapter.close)
        owner.close()


def test_one_hundred_runtime_start_stop_cycles_drain_both_owners(qtbot, monkeypatch, capture_geometry, runtime_settings):
    from core import config
    import core.worker as module
    from core.capture.models import CapturedFrame, SourceStatus
    from core.contracts import OcrResult
    from test_capture_app_integration import capture_values
    profile, context = capture_values(capture_geometry)
    sources, refs = [], []
    class Source:
        def __init__(self): self.closed = False; self.epoch = None
        def open(self, value, **kwargs): self.epoch = value.binding_epoch
        def read_latest(self, **kwargs):
            frame = CapturedFrame(self.epoch, 1, np.zeros((600, 800, 4), dtype=np.uint8), (0, 0), (800, 600), kwargs['now_s'])
            refs.append(weakref.ref(frame))
            return frame
        def status(self): return SourceStatus(self.epoch, 'ready')
        def close(self): self.closed = True
    def factory(*args, **kwargs):
        source = Source(); sources.append(source); return source
    monkeypatch.setattr(module, 'create_capture_source', factory)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker = module.TranslationWorker(config.State(), config.DEFAULT_REGION, ocr_reader=lambda *args, **kwargs: OcrResult(''))
    worker.configure(replace(runtime_settings, interval_ms=100))
    observations = []
    worker.capture_observation_ready.connect(observations.append)
    try:
        for epoch in range(1, 101):
            worker.configure_capture(profile, replace(context, binding_epoch=epoch))
            worker.start_worker()
            qtbot.waitUntil(lambda: bool(observations) and observations[-1].context.binding_epoch == epoch, timeout=2000)
            worker.stop_worker()
            qtbot.waitUntil(lambda: worker.is_drained, timeout=2000)
            assert sources[-1].closed and not worker.restart_pending
            assert worker._block_translator.pending_count == 0
            assert worker._block_translator.drain_results() == ()
        assert worker.translation_session_id == 100 and len(sources) == 100
        gc.collect()
        assert all(reference() is None for reference in refs)
    finally:
        worker.stop_worker()
        qtbot.waitUntil(lambda: worker.is_drained, timeout=3000)
