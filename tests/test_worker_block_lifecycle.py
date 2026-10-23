from dataclasses import replace
from threading import Event, get_ident
import numpy as np
from core import config
from core.contracts import TranslationResult
from core.worker import TranslationWorker


def test_moving_blocks_update_while_translation_is_in_flight(qtbot, monkeypatch, runtime_settings, capture_geometry, span_factory):
    import core.worker as module
    from core.contracts import OcrResult
    entered, release = Event(), Event()
    counts = {'capture': 0, 'request': 0}
    class Service:
        def translate(self, text, settings):
            counts['request'] += 1
            entered.set()
            release.wait(4)
            return TranslationResult('Xin chào')
        def close(self): pass
    class Capture:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def grab(self, region):
            counts['capture'] += 1
            return np.full((600, 800, 4), min(250, counts['capture']*20), dtype='uint8')
    def recognize(image, **kwargs):
        # Mask would turn the overlapping source region black.
        assert image[15, 15] > 0
        x = 10 if counts['capture'] <= 2 else 30
        return OcrResult('Hello', spans=(span_factory(x=x),))
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module.mss, 'mss', Capture)
    monkeypatch.setattr(module, 'ocr_image', recognize)
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
        qtbot.waitUntil(lambda: counts['capture'] >= 4)
        assert counts['request'] == 1
        release.set()
        qtbot.waitUntil(lambda: any(f.blocks for f in frames))
        assert next(f for f in reversed(frames) if f.blocks).blocks[0].source_rect.x == 30
        assert counts['request'] == 1
    finally:
        release.set()
        w.stop_worker()
        assert w.wait(2000)
        assert w._block_translator.wait(2000)


def test_mode_switch_waits_for_active_request_before_subtitle_request(qtbot, monkeypatch, runtime_settings, capture_geometry):
    import core.worker as module
    entered, release = Event(), Event()
    calls = []
    class Service:
        def translate(self, text, settings):
            calls.append(settings.overlay_mode)
            if settings.overlay_mode == 'blocks':
                entered.set()
                release.wait(4)
            return TranslationResult('translated')
        def close(self): pass
    class Capture:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def grab(self, region): return np.full((600, 800, 4), 100, dtype='uint8')
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module.mss, 'mss', Capture)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    w = TranslationWorker(config.State(), dict(left=100, top=100, width=800, height=600))
    w.configure(replace(runtime_settings, overlay_mode='blocks', interval_ms=100))
    w.set_capture_geometry(capture_geometry)
    w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        w.configure(replace(runtime_settings, interval_ms=100))
        assert calls == ['blocks']
        release.set()
        qtbot.waitUntil(lambda: calls == ['blocks', 'subtitle'], timeout=3000)
    finally:
        release.set()
        w.stop_worker()
        assert w.wait(2000)
        assert w._block_translator.wait(2000)


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


def test_window_close_waits_for_held_translation_before_shutdown_finished(qtbot, monkeypatch, runtime_settings, capture_geometry):
    import core.worker as module
    from ui.controller import ControllerWindow
    entered, release = Event(), Event()
    shutdown, close_calls = [], []
    class Service:
        def translate(self, *args):
            entered.set()
            release.wait(4)
            return TranslationResult('old')
        def close(self): pass
    class Capture:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, region): return np.full((600, 800, 4), 100, dtype='uint8')
    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module.mss, 'mss', Capture)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    state = config.State()
    w = TranslationWorker(state, dict(left=100, top=100, width=800, height=600))
    window = None
    def quit_requested():
        close_calls.append(1)
        window.hide()
        w.stop_worker()
    window = ControllerWindow(w, state, lambda: None, quit_requested)
    qtbot.addWidget(window)
    w.configure(replace(runtime_settings, overlay_mode='blocks', interval_ms=100))
    w.set_capture_geometry(capture_geometry)
    w.shutdown_finished.connect(lambda: shutdown.append((w.isRunning(), w._block_translator.isRunning())))
    w.start_worker()
    try:
        qtbot.waitUntil(entered.is_set)
        window.close()
        assert close_calls == [1]
        assert not shutdown
        release.set()
        qtbot.waitUntil(lambda: bool(shutdown))
        assert shutdown == [(False, False)]
    finally:
        release.set()
        w.stop_worker()
        assert w.wait(2000)
        assert w._block_translator.wait(2000)
