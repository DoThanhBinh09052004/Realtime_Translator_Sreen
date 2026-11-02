from dataclasses import replace
import weakref

import numpy as np
import pytest

from core.blocks.models import CaptureGeometry, Rect, ScreenMapping
from core.capture.models import CaptureContext, CapturedFrame, CaptureProfile, CaptureRegion, NormalizedRect
from core.contracts import EngineError, OcrResult, OcrSpan


class Clock:
    def __init__(self):
        self.now = 0.

    def __call__(self):
        return self.now


def profile(kind='desktop'):
    return CaptureProfile(1, kind, 'screen', None, tuple(
        CaptureRegion(name, name, NormalizedRect(x, 0, .2, 1), True)
        for name, x in [('a', 0), ('b', .4), ('c', .8)]), ())


def context(kind='desktop', size=(100, 20), epoch=7):
    bounds = Rect(-300, 40, *size)
    return CaptureContext(epoch, 1, kind, None, CaptureGeometry(bounds, ScreenMapping('screen', bounds, bounds), size))


def frame(at=0, pixels=None, epoch=7, origin=(0, 0), size=(100, 20)):
    if pixels is None:
        pixels = np.full((size[1], size[0], 4), 80, np.uint8)
    return CapturedFrame(epoch, 1, pixels, origin, size, at)


def result(text='hello', x=1, width=5):
    return OcrResult(text=text, spans=(OcrSpan(text, ((x, 1), (x+width, 1), (x+width, 10), (x, 10)), .99),))


def scanner(reader=None, p=None):
    from core.capture.scan import RegionScanner
    clock = Clock()
    calls = []
    def recognize(image, *, lang):
        calls.append((image.copy(), lang))
        return reader(image, lang=lang) if reader else result()
    return RegionScanner(p or profile(), ocr_reader=recognize, clock=clock), clock, calls


def observe(scan, settings, image=None, **kwargs):
    return scan.observe(image or frame(), settings=settings, context=kwargs.pop('context', context()), revision=3,
                        force_regions=kwargs.pop('force_regions', frozenset()),
                        dynamic_masks_px=kwargs.pop('dynamic_masks_px', ()),
                        is_current=kwargs.pop('is_current', lambda: True), **kwargs)


def ids(batch):
    return [region.region_id for region in batch.regions] if batch else []


def test_same_frame_crops_have_same_capture_time(runtime_settings):
    scan, clock, calls = scanner()
    batch = observe(scan, runtime_settings, frame(4.2))
    assert ids(batch) == ['a', 'b', 'c']
    assert [item.captured_at_s for item in batch.regions] == [4.2]*3
    assert all(image.shape == (20, 20) and lang == 'en' for image, lang in calls)
    assert batch.settings == runtime_settings and batch.revision == 3


def test_changes_outside_regions_do_not_schedule_ocr(runtime_settings):
    scan, clock, calls = scanner()
    observe(scan, runtime_settings)
    clock.now = .1
    observe(scan, runtime_settings)  # one confirmation after the first successful changed scan
    assert len(calls) == 6
    pixels = frame().pixels.copy()
    pixels[:, 25:35] = 255
    clock.now = .2
    assert observe(scan, runtime_settings, frame(.2, pixels)) is None
    assert len(calls) == 6


def test_each_region_has_own_retry_thumbnail_and_confirmation(runtime_settings):
    attempts = [0]
    def reader(image, **kwargs):
        attempts[0] += 1
        return OcrResult(error=EngineError('ocr', 'Failure', True)) if attempts[0] == 1 else result()
    scan, clock, calls = scanner(reader)
    first = observe(scan, runtime_settings)
    assert first.regions[0].ocr.error
    assert ids(first) == ['a', 'b', 'c']
    clock.now = .1
    assert ids(observe(scan, runtime_settings)) == ['b', 'c']
    clock.now = .2
    pixels = frame().pixels.copy()
    pixels[:, 40:60] = 200
    assert ids(observe(scan, runtime_settings, frame(.2, pixels))) == ['b']
    clock.now = 1
    assert 'a' in ids(observe(scan, runtime_settings, frame(1, pixels)))


def test_scan_budget_rotates_oldest_regions_without_starvation(runtime_settings):
    clock = Clock()
    from core.capture.scan import RegionScanner
    def slow(image, **kwargs):
        clock.now += .6
        return result()
    scan = RegionScanner(profile(), ocr_reader=slow, clock=clock)
    batches = [observe(scan, runtime_settings, force_regions=frozenset('abc')) for _ in range(6)]
    assert [ids(batch) for batch in batches] == [['a'], ['b'], ['c'], ['a'], ['b'], ['c']]
    assert [batch.scan_id for batch in batches] == sorted({batch.scan_id for batch in batches})


def test_static_region_due_after_one_second(runtime_settings):
    scan, clock, calls = scanner()
    observe(scan, runtime_settings)
    clock.now = .1
    observe(scan, runtime_settings)
    clock.now = 1.09
    assert observe(scan, runtime_settings) is None
    clock.now = 1.1
    assert ids(observe(scan, runtime_settings)) == ['a', 'b', 'c']


@pytest.mark.parametrize('cancel_after', [0, 1, 2])
def test_stop_or_revision_change_between_regions_discards_batch(runtime_settings, cancel_after):
    count = [0]
    def reader(image, **kwargs):
        count[0] += 1
        return result()
    scan, clock, calls = scanner(reader)
    assert observe(scan, runtime_settings, is_current=lambda: count[0] < cancel_after) is None
    assert len(calls) == cancel_after


def test_desktop_subtitle_dynamic_mask_covers_two_rois_without_self_capture(runtime_settings):
    scan, clock, calls = scanner()
    masks = (Rect(0, 0, 60, 20),)
    batch = observe(scan, runtime_settings, dynamic_masks_px=masks)
    assert all(np.all(image == 0) for image, _ in calls[:2])
    assert [item.ocr.text for item in batch.regions] == ['', '', 'hello']
    clock.now = .1
    observe(scan, runtime_settings, dynamic_masks_px=masks)
    clock.now = .2
    pixels = frame().pixels.copy()
    pixels[:, :60] = 255
    assert observe(scan, runtime_settings, frame(.2, pixels), dynamic_masks_px=masks) is None


def test_window_source_does_not_inherit_desktop_mask(runtime_settings):
    scan, clock, calls = scanner(p=profile('window'))
    batch = observe(scan, runtime_settings, context=context('window'), dynamic_masks_px=(Rect(0, 0, 100, 20),))
    assert all(np.all(image == 80) for image, _ in calls)
    assert all(item.ocr.text == 'hello' for item in batch.regions)


def test_persisted_exclusions_and_ownership_apply_before_ocr_and_filter_spans(runtime_settings):
    p = CaptureProfile(1, 'desktop', 'screen', None, (
        CaptureRegion('a', 'a', NormalizedRect(0, 0, .5, 1), True),
        CaptureRegion('b', 'b', NormalizedRect(.5, 0, .5, 1), True)), (NormalizedRect(0, 0, .2, 1),))
    scan, clock, calls = scanner(lambda image, **kwargs: result(x=0, width=1), p)
    batch = observe(scan, runtime_settings, frame(size=(7, 20)), context=context(size=(7, 20)))
    assert np.all(calls[0][0][:, :2] == 0)
    assert np.all(calls[1][0][:, 0] == 0)
    assert [item.ocr.text for item in batch.regions] == ['', '']


def test_exclusions_in_another_region_preserve_text_only_ocr(runtime_settings):
    p = replace(profile(), exclusions=(NormalizedRect(0, 0, .2, 1),))
    scan, clock, calls = scanner(lambda *args, **kwargs: OcrResult(text='readable'), p)
    batch = observe(scan, runtime_settings)
    assert [item.ocr.text for item in batch.regions] == ['', 'readable', 'readable']


def test_cancelled_batch_does_not_commit_region_thumbnail_or_retry(runtime_settings):
    calls = [0]
    def reader(image, **kwargs):
        calls[0] += 1
        return OcrResult(error=EngineError('ocr', 'Failure', False))
    scan, clock, images = scanner(reader)
    assert observe(scan, runtime_settings, is_current=lambda: calls[0] < 1) is None
    batch = observe(scan, runtime_settings)
    assert ids(batch) == ['a', 'b', 'c']
    assert len(images) == 4


def test_long_interval_sets_static_refresh_deadline(runtime_settings):
    scan, clock, calls = scanner()
    settings = replace(runtime_settings, interval_ms=2000)
    observe(scan, settings)
    clock.now = .1
    observe(scan, settings)
    clock.now = 1.2
    assert observe(scan, settings) is None
    clock.now = 2.1
    assert ids(observe(scan, settings)) == ['a', 'b', 'c']


def test_reader_exception_does_not_stop_other_regions(runtime_settings):
    count = [0]
    def reader(image, **kwargs):
        count[0] += 1
        if count[0] == 1:
            raise RuntimeError('native OCR details')
        return result()
    scan, clock, calls = scanner(reader)
    batch = observe(scan, runtime_settings)
    assert ids(batch) == ['a', 'b', 'c']
    assert batch.regions[0].ocr.error.code == 'ocr'
    assert batch.regions[1].ocr.text == 'hello'


def test_retry_exhaustion_only_resets_for_changed_region(runtime_settings):
    scan, clock, calls = scanner(lambda *args, **kwargs: OcrResult(error=EngineError('ocr', 'Failure', True)))
    for at in (0, 1, 3, 7):
        clock.now = at
        observe(scan, runtime_settings)
    assert len(calls) == 12
    clock.now = 30
    assert observe(scan, runtime_settings) is None
    assert observe(scan, runtime_settings, force_regions=frozenset({'b'})) is None
    pixels = frame().pixels.copy()
    pixels[:, 40:60] = 200
    assert ids(observe(scan, runtime_settings, frame(30, pixels))) == ['b']


def test_forced_scan_after_error_respects_retry_deadline(runtime_settings):
    scan, clock, calls = scanner(lambda *args, **kwargs: OcrResult(error=EngineError('ocr', 'Failure', True)))
    observe(scan, runtime_settings)
    clock.now = .1
    assert observe(scan, runtime_settings, force_regions=frozenset('abc')) is None
    assert len(calls) == 3
    clock.now = 1
    assert ids(observe(scan, runtime_settings, force_regions=frozenset('abc'))) == ['a', 'b', 'c']
    clock.now = 1.1
    assert observe(scan, runtime_settings, force_regions=frozenset('abc')) is None
    assert len(calls) == 6


def test_crop_metadata_and_binding_must_match_context(runtime_settings):
    scan, clock, calls = scanner()
    assert observe(scan, runtime_settings, frame(epoch=8)) is None
    with pytest.raises(ValueError):
        observe(scan, runtime_settings, frame(size=(99, 20)))
    assert calls == []


def test_scanner_does_not_retain_source_buffers_and_reset_forgets_state(runtime_settings):
    scan, clock, calls = scanner()
    image = frame()
    reference = weakref.ref(image.pixels)
    observe(scan, runtime_settings, image)
    del image
    assert reference() is None
    scan.reset(profile())
    assert ids(observe(scan, runtime_settings)) == ['a', 'b', 'c']
