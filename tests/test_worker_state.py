"""Coherent detached capture-thread snapshots and runtime invalidation."""
from dataclasses import FrozenInstanceError, replace

import pytest
import numpy as np

from core import config
from core.contracts import OcrResult
from core.runtime.worker import TranslationWorker
from test_capture_app_integration import capture_values


def test_runtime_snapshot_is_detached_immutable_and_keeps_captured_source(qtbot, runtime_settings, capture_geometry):
    worker = TranslationWorker(config.State(), {'left': 1, 'top': 2, 'width': 8, 'height': 9})
    profile, context = capture_values(capture_geometry)
    worker.configure(runtime_settings)
    worker.configure_capture(profile, context)
    worker.set_overlay_rect([1, 2, 3, 4])
    worker.request_capture_scan(worker.revision, ['one'])
    worker._is_running = True
    snapshot = worker._take_snapshot()
    with pytest.raises(TypeError):
        snapshot.region['left'] = 90
    with pytest.raises(FrozenInstanceError):
        snapshot.revision = 90
    assert snapshot.profile is profile and snapshot.context is context
    assert snapshot.force_regions == frozenset({'one'})
    assert snapshot.overlay_rect == (1, 2, 3, 4)
    old_revision = snapshot.revision
    worker.configure(replace(runtime_settings, target_lang='Japanese'))
    worker.configure_capture(profile, replace(context, binding_epoch=2))
    worker.set_region({'left': 30, 'top': 40, 'width': 10, 'height': 11})
    worker.request_capture_scan(worker.revision, ['two'])
    assert snapshot.revision == old_revision
    assert snapshot.context.binding_epoch == 1
    assert snapshot.settings.target_lang == 'Vietnamese'
    assert snapshot.region['left'] == 1
    assert snapshot.force_regions == frozenset({'one'})
    worker._is_running = False


def test_runtime_invalidation_consumed_once_and_workers_are_isolated(qtbot):
    first = TranslationWorker(config.State(), config.DEFAULT_REGION)
    second = TranslationWorker(config.State(), config.DEFAULT_REGION)
    first._is_running = second._is_running = True
    a, b = first._take_snapshot(), second._take_snapshot()
    assert a.invalidated and b.invalidated
    assert not first._take_snapshot().invalidated
    first.set_region({'left': 3})
    assert first._take_snapshot().invalidated
    assert not first._take_snapshot().invalidated
    assert not second._take_snapshot().invalidated
    assert second._take_snapshot().region == config.DEFAULT_REGION
    first._is_running = second._is_running = False


def test_runtime_geometry_move_keeps_revision_and_old_snapshot(qtbot, capture_geometry):
    from core.blocks.models import Rect
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    profile, context = capture_values(capture_geometry, 'window')
    worker.configure_capture(profile, context)
    worker._is_running = True
    before = worker._take_snapshot()
    moved = replace(context, geometry_sequence=2,
        geometry=replace(capture_geometry, region_px=Rect(70, 80, 800, 600)))
    worker.update_capture_geometry(moved)
    after = worker._take_snapshot()
    assert after.revision == before.revision
    assert after.context is moved and after.geometry == moved.geometry
    assert before.context is context and before.geometry == capture_geometry
    assert not after.invalidated
    worker._is_running = False

def test_profile_runner_reads_settings_source_and_forced_regions_from_one_snapshot(qtbot, monkeypatch, runtime_settings, capture_geometry):
    import core.runtime.worker as module
    from core.capture.models import SourceStatus
    profile, context = capture_values(capture_geometry)
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker.configure(runtime_settings)
    worker.configure_capture(profile, context)
    worker.request_capture_scan(worker.revision, ['old'])
    worker._is_running = True
    take = worker._take_snapshot
    observed = []
    opened = []

    def take_then_publish_next_revision():
        snapshot = take()
        worker.configure(replace(runtime_settings, target_lang='Japanese'))
        worker.configure_capture(profile, replace(context, binding_epoch=2))
        worker.request_capture_scan(worker.revision, ['new'])
        return snapshot

    class Source:
        def __init__(self, value): self.context = value
        def open(self, value, **kwargs): opened.append(value.binding_epoch)
        def read_latest(self, **kwargs): return object()
        def status(self): return SourceStatus(self.context.binding_epoch, 'ready')
        def close(self): pass

    class Scanner:
        def __init__(self, *a, **k): pass
        def observe(self, frame, *, settings, context, force_regions, **kwargs):
            observed.append((settings.target_lang, context.binding_epoch, force_regions))
            worker._is_running = False
            return None

    monkeypatch.setattr(worker, '_take_snapshot', take_then_publish_next_revision)
    monkeypatch.setattr(module, 'create_capture_source', lambda value, **kwargs: Source(value))
    monkeypatch.setattr(module, 'RegionScanner', Scanner)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker._run_capture()
    assert opened == [1]
    assert observed == [('Vietnamese', 1, frozenset({'old'}))]


def test_legacy_loop_uses_captured_force_scan_policy(qtbot, monkeypatch, runtime_settings):
    import core.runtime.worker as module
    reads = []
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION,
        ocr_reader=lambda *a, **k: reads.append(1) or OcrResult(''))
    worker.configure(runtime_settings)
    worker._is_running = True
    monkeypatch.setattr(module.time, 'monotonic', lambda: 10.)
    monkeypatch.setattr(worker, '_is_frame_changed', lambda image: False)

    class Source:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def grab(self, region):
            # A GUI policy update after capture's atomic snapshot belongs to the next frame.
            worker.request_dialogue_scan(worker.revision, True)
            worker._dialogue_last_ocr = 10.
            return np.zeros((8, 8, 4), dtype='uint8')

    def sleep(seconds): worker._is_running = False
    monkeypatch.setattr(module.mss, 'mss', Source)
    monkeypatch.setattr(module.time, 'sleep', sleep)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker.run()
    assert reads == []
