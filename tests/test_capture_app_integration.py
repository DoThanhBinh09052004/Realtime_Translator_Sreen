from dataclasses import replace
from threading import Event, get_ident
from uuid import uuid4
import numpy as np
import pytest
from core import config
from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect, CaptureContext, CapturedFrame, SourceStatus, WindowIdentity
from core.contracts import OcrResult, TranslationResult, EngineError
from core.worker import TranslationWorker


def capture_values(geometry, kind='desktop'):
    profile = CaptureProfile(1, kind, 'test' if kind == 'desktop' else None,
                             'Game' if kind == 'window' else None,
                             (CaptureRegion(str(uuid4()), 'Vùng 1', NormalizedRect(0, 0, 1, 1), True),), ())
    return profile, CaptureContext(1, 1, kind, WindowIdentity(1, 2, 3) if kind == 'window' else None, geometry)


@pytest.mark.parametrize('kind', ['desktop', 'window'])
@pytest.mark.parametrize('mode', ['subtitle', 'blocks'])
def test_capture_runtime_routes_to_real_overlay(qtbot, monkeypatch, runtime_settings, capture_geometry, span_factory, kind, mode):
    import core.worker as module
    from ui.overlay import Overlay
    import ui.block_overlay as block_module
    owners = []; opened = []
    profile, context = capture_values(capture_geometry, kind)
    class Source:
        def open(self, value, **kwargs): owners.append(get_ident()); opened.append(kwargs['roi_rects_px'])
        def read_latest(self, **kwargs):
            return CapturedFrame(1, 1, np.zeros((600, 800, 4), dtype=np.uint8), (0, 0), (800, 600), kwargs['now_s'])
        def status(self): return SourceStatus(1, 'ready')
        def close(self): owners.append(get_ident())
    class Service:
        def __init__(self, **kwargs): pass
        def translate(self, *args): return TranslationResult('Xin chào')
        def close(self): pass
    monkeypatch.setattr(module, 'create_capture_source', lambda *args, **kwargs: Source(), raising=False)
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    monkeypatch.setattr(block_module, 'set_capture_excluded', lambda *args: None)
    w = TranslationWorker(config.State(), config.DEFAULT_REGION, ocr_reader=lambda *a, **k: OcrResult('Hello', spans=(span_factory(),)))
    o = Overlay(); qtbot.addWidget(o)
    w.revision_changed.connect(lambda revision: o.set_mode(mode, revision))
    w.subtitle_updated.connect(o.update_subtitle); w.blocks_updated.connect(o.update_blocks)
    w.configure(replace(runtime_settings, overlay_mode=mode, interval_ms=100))
    w.configure_capture(profile, context); w.start_worker()
    try:
        qtbot.waitUntil(lambda: o.text() == 'Xin chào' if mode == 'subtitle' else bool(o.block_overlay.placed_blocks), timeout=3000)
        assert opened[0] is not None
    finally:
        w.stop_worker(); qtbot.waitUntil(lambda: w.is_drained, timeout=3000)
    assert len(owners) == 2 and owners[0] == owners[1] and owners[0] != get_ident()


def test_terminal_signal_arrives_while_ocr_held(qtbot, monkeypatch, capture_geometry):
    import core.worker as module
    entered, release = Event(), Event(); callbacks = []; terminal = []
    profile, context = capture_values(capture_geometry)
    class Source:
        def open(self, *a, **k): pass
        def read_latest(self, **k): return CapturedFrame(1, 1, np.zeros((600, 800, 4), dtype=np.uint8), (0, 0), (800, 600), k['now_s'])
        def status(self): return SourceStatus(1, 'ready')
        def close(self): pass
    def factory(*a, **k): callbacks.append(k['on_terminal']); return Source()
    def reader(*a, **k): entered.set(); release.wait(10); return OcrResult('late')
    monkeypatch.setattr(module, 'create_capture_source', factory, raising=False)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), config.DEFAULT_REGION, ocr_reader=reader)
    w.configure_capture(profile, context); w.capture_terminal_status.connect(terminal.append); w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        callbacks[0](SourceStatus(1, 'error', EngineError('capture', 'gone', False)))
        qtbot.waitUntil(lambda: bool(terminal))
        assert not release.is_set()
    finally:
        release.set(); w.stop_worker(); qtbot.waitUntil(lambda: w.is_drained, timeout=3000)

def test_terminal_lifecycle_clears_and_drops_ocr_held_result(qtbot, monkeypatch, capture_geometry):
    import time
    import core.worker as module
    from ui.overlay import Overlay
    from ui.region_selection import RegionSelectionLifecycle
    from PyQt5.QtCore import Qt
    from unittest.mock import Mock
    entered, release = Event(), Event(); callbacks = []; batches = []
    profile, context = capture_values(capture_geometry)
    class Source:
        def open(self, *a, **k): pass
        def read_latest(self, **k): return CapturedFrame(1, 1, np.zeros((600, 800, 4), dtype=np.uint8), (0, 0), (800, 600), k['now_s'])
        def status(self): return SourceStatus(1, 'ready')
        def close(self): pass
    def factory(*a, **k): callbacks.append(k['on_terminal']); return Source()
    def reader(*a, **k): entered.set(); release.wait(10); return OcrResult('late')
    monkeypatch.setattr(module, 'create_capture_source', factory)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), config.DEFAULT_REGION, ocr_reader=reader)
    o = Overlay(); qtbot.addWidget(o); o.setText('stale')
    c = Mock(); c.capture_run_requested = True
    lifecycle = RegionSelectionLifecycle(c, w, o, Mock())
    w.revision_changed.connect(lambda revision: o.set_mode('subtitle', revision))
    w.capture_terminal_status.connect(lifecycle.on_capture_terminal, Qt.QueuedConnection)
    w.capture_observation_ready.connect(batches.append)
    w.configure_capture(profile, context); w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        qtbot.wait(20)
        o.setText('stale')
        old_revision = w.revision
        started = time.monotonic()
        callbacks[0](SourceStatus(1, 'unavailable', EngineError('capture', 'gone', True)))
        qtbot.waitUntil(lambda: o.text() == '')
        assert time.monotonic() - started < 1.0
        assert w.revision > old_revision
        assert o.text() == '' and c.capture_run_requested is True and not release.is_set()
    finally:
        release.set(); w.stop_worker(); qtbot.waitUntil(lambda: w.is_drained, timeout=3000)
    assert not batches


def test_move_while_ocr_held_keeps_latest_block_geometry(qtbot, monkeypatch, runtime_settings, capture_geometry, span_factory):
    import core.worker as module
    from core.blocks.models import Rect
    entered, release = Event(), Event(); frames = []; translated = []
    profile, context = capture_values(capture_geometry, 'window')
    class Source:
        def open(self, *a, **k): pass
        def read_latest(self, **k): return CapturedFrame(1, 1, np.zeros((600, 800, 4), dtype=np.uint8), (0, 0), (800, 600), k['now_s'])
        def status(self): return SourceStatus(1, 'ready')
        def close(self): pass
    class Service:
        def __init__(self, **k): pass
        def translate(self, *a): translated.append(a); return TranslationResult('Xin chao')
        def close(self): pass
    def reader(*a, **k): entered.set(); release.wait(3); return OcrResult('Hello', spans=(span_factory(),))
    monkeypatch.setattr(module, 'create_capture_source', lambda *a, **k: Source())
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), config.DEFAULT_REGION, ocr_reader=reader)
    w.configure(replace(runtime_settings, overlay_mode='blocks', interval_ms=100))
    w.configure_capture(profile, context); w.blocks_updated.connect(frames.append); w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        revision = w.revision
        moved = replace(context, geometry_sequence=2, geometry=replace(capture_geometry, region_px=Rect(70, 80, 800, 600)))
        w.update_capture_geometry(moved)
        assert w.revision == revision
        release.set()
        qtbot.waitUntil(lambda: any(f.blocks for f in frames), timeout=3000)
        assert next(f for f in reversed(frames) if f.blocks).geometry == moved.geometry
        assert len(translated) == 1
    finally:
        release.set(); w.stop_worker(); qtbot.waitUntil(lambda: w.is_drained, timeout=3000)


def test_desktop_mask_from_main_reaches_both_rois(qtbot, monkeypatch, runtime_settings):
    from main import sync_capture_overlay_mask
    from core.blocks.models import Rect, ScreenMapping, CaptureGeometry
    import core.worker as module
    screen = ScreenMapping('left', Rect(-1000, 0, 1000, 600), Rect(-1500, 0, 1500, 900))
    geometry = CaptureGeometry(screen.physical_rect, screen, (1500, 900))
    regions = (CaptureRegion(str(uuid4()), 'left', NormalizedRect(0, 0, .5, 1), True),
               CaptureRegion(str(uuid4()), 'right', NormalizedRect(.5, 0, .5, 1), True))
    profile = CaptureProfile(1, 'desktop', 'left', None, regions, ())
    context = CaptureContext(1, 1, 'desktop', None, geometry)
    images = []
    class Source:
        def open(self, *a, **k): pass
        def read_latest(self, **k): return CapturedFrame(1, 1, np.full((900, 1500, 4), 255, dtype=np.uint8), (0, 0), (1500, 900), k['now_s'])
        def status(self): return SourceStatus(1, 'ready')
        def close(self): pass
    def reader(image, **kwargs): images.append(image.copy()); return OcrResult('')
    monkeypatch.setattr(module, 'create_capture_source', lambda *a, **k: Source())
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), config.DEFAULT_REGION, ocr_reader=reader)
    w.configure(replace(runtime_settings, interval_ms=100)); w.configure_capture(profile, context)
    sync_capture_overlay_mask(w, (-600, 100, 200, 100), None)
    w.start_worker()
    try:
        qtbot.waitUntil(lambda: len(images) >= 2, timeout=3000)
        assert images[0][160, 650] == 0 and images[1][160, 50] == 0
        assert images[0][20, 20] == 255 and images[1][20, 20] == 255
    finally:
        w.stop_worker(); qtbot.waitUntil(lambda: w.is_drained, timeout=3000)
