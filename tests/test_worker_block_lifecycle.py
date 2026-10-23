from dataclasses import replace
from threading import Event, get_ident
import numpy as np
from core import config
from core.contracts import TranslationResult
from core.worker import TranslationWorker


def test_stop_is_nonblocking_and_restart_waits_for_both_threads(qtbot, monkeypatch, runtime_settings, capture_geometry):
    import core.worker as module
    entered, release, closed = Event(), Event(), Event()
    threads, capture_count = [], []
    class Service:
        def translate(self, *a):
            threads.append(get_ident())
            entered.set()
            release.wait(4)
            return TranslationResult('translated')
        def close(self):
            if threads:
                assert get_ident() == threads[0]
                closed.set()
    class Capture:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def grab(self, region):
            capture_count.append(1)
            return np.full((600, 800, 4), 100, dtype='uint8')
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module.mss, 'mss', Capture)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), dict(left=100, top=100, width=800, height=600))
    w.configure(replace(runtime_settings, overlay_mode='blocks', interval_ms=100))
    w.set_capture_geometry(capture_geometry)
    w.set_overlay_rect((100, 100, 800, 600))
    frames = []
    w.blocks_updated.connect(frames.append)
    w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set, timeout=2000)
        qtbot.waitUntil(lambda: len(capture_count) >= 3)
        assert len(threads) == 1
        w.stop_worker()
        assert not closed.is_set()
        w.start_worker()
        w.stop_worker()  # Cancels pending restart.
        release.set()
        qtbot.waitUntil(lambda: not w.isRunning() and not w._block_translator.isRunning())
        qtbot.waitUntil(closed.is_set)
        assert not any(f.blocks for f in frames)
    finally:
        release.set()
        w.stop_worker()
        assert w.wait(2000)
        assert w._block_translator.wait(2000)
