import numpy as np
import pytest

from core import config
from core.worker import TranslationWorker
from ui.overlay import Overlay


@pytest.mark.parametrize('rect, bounds', [
    ((-110, -60, 20, 20), (0, 16, 0, 16)),
    ((-80, -30, 10, 10), (14, 36, 14, 36)),
    ((-8, 42, 20, 20), (86, 100, 86, 100)),
    ((-8, -60, 20, 20), (86, 100, 0, 16)),
    ((-110, 42, 20, 20), (0, 16, 86, 100)),
    ((-130, -80, 10, 10), None),
    ((10, 70, 10, 10), None),
    (None, None),
])
def test_padded_mask_clips_global_coordinates(rect, bounds):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    image = np.full((100, 100), 255, dtype=np.uint8)
    expected = image.copy()
    if bounds:
        x1, x2, y1, y2 = bounds
        expected[y1:y2, x1:x2] = 0
    result = worker._mask_overlay_numpy(image, {'left': -100, 'top': -50}, rect)
    np.testing.assert_array_equal(result, expected)


def test_overlay_publishes_live_geometry(qtbot):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    overlay.capture_geometry_changed.connect(worker.set_overlay_rect)
    overlay.show()
    assert worker._overlay_rect == overlay.get_geometry_rect()
    overlay.move(40, 50)
    assert worker._overlay_rect == (40, 50, overlay.width(), overlay.height())
    overlay.resize(350, 120)
    assert worker._overlay_rect == (40, 50, 350, 120)
    overlay.update_text('A much longer subtitle ' * 12)
    assert worker._overlay_rect == overlay.get_geometry_rect()
    overlay.hide()
    assert worker._overlay_rect is None


@pytest.mark.parametrize('rect', [
    (0, 0, 0, 20), (0, 0, 20, -1), (float('nan'), 0, 20, 20),
    (0, float('inf'), 20, 20), ('bad', 0, 20, 20), (1, 2, 3), 'bad',
])
def test_invalid_rectangles_leave_capture_unchanged(rect):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    image = np.full((40, 100), 255, dtype=np.uint8)
    worker._mask_overlay_numpy(image, {'left': 0, 'top': 0}, rect)
    assert np.all(image == 255)


def test_overlay_animation_is_masked_before_change_detection_and_ocr(monkeypatch, fake_ocr, qtbot):
    from core import worker as module
    config.save_active_provider('Google Gemini')

    region = {'left': -100, 'top': -50, 'width': 100, 'height': 40}
    worker = TranslationWorker(config.State(), region)
    worker.set_overlay_rect((-80, -40, 10, 10))
    config.save_provider_api_key('Google Gemini', 'fake-key')
    worker.configure(config.load_runtime_settings(worker.state, 500))

    class Capture:
        count = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def grab(self, monitor):
            assert monitor == region
            self.count += 1
            if self.count > 5:
                worker._is_running = False
            image = np.full((40, 100, 4), 255, dtype=np.uint8)
            image[4:26, 14:36] = self.count * 20
            return image

    monkeypatch.setattr(module.mss, 'mss', Capture)
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    emitted = []
    worker.text_translated.connect(emitted.append)
    worker.start_worker()
    try:qtbot.waitUntil(lambda:not worker.isRunning(),timeout=4000)
    finally:
        worker.stop_worker();assert worker.wait(2000);assert worker._block_translator.wait(2000)
    assert emitted == ['fake translation']
    assert 2 <= fake_ocr.call_count <= 3
    expected = np.full((40, 100, 3), 255, dtype=np.uint8)
    expected[4:26, 14:36] = 0
    for call in fake_ocr.call_args_list:
        np.testing.assert_array_equal(call.args[0], expected)
    assert not worker._coordinator._running
