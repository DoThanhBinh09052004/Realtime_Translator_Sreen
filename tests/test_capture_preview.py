from threading import Event, get_ident
import numpy as np
from core.capture.models import CapturedFrame, SourceStatus
from test_capture_app_integration import capture_values


def test_preview_reads_full_source_and_finishes_only_after_native_close(qtbot, monkeypatch, capture_geometry):
    from ui.capture_preview import CapturePreviewWorker
    import ui.capture_preview as module
    closing, release = Event(), Event(); ready = []; finished = []; calls = []
    profile, context = capture_values(capture_geometry)
    class Source:
        def open(self, ctx, **kwargs): calls.append((get_ident(), kwargs['roi_rects_px']))
        def read_latest(self, **kwargs): return CapturedFrame(1, 1, np.zeros((600, 800, 4), dtype=np.uint8), (0, 0), (800, 600), 0)
        def status(self): return SourceStatus(1, 'ready')
        def close(self): closing.set(); release.wait(3); calls.append((get_ident(), 'close'))
    monkeypatch.setattr(module, 'create_capture_source', lambda *a, **k: Source())
    w = CapturePreviewWorker(profile, context)
    w.preview_ready.connect(lambda *args: ready.append(args)); w.shutdown_finished.connect(lambda: finished.append(1))
    w.start()
    try:
        qtbot.waitUntil(closing.is_set)
        qtbot.waitUntil(lambda: bool(ready))
        assert calls[0][1] is None and not finished and w.isRunning()
    finally:
        release.set(); qtbot.waitUntil(lambda: bool(finished))
    assert calls[0][0] == calls[-1][0] != get_ident()
