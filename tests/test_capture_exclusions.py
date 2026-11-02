"""Exclusions mask owned OCR crops and filter results in source coordinates."""
import numpy as np

from core.blocks.models import Rect
from core.contracts import EngineError, OcrResult


def test_exclusion_mask_copies_crop_and_preserves_source_buffer():
    from core.capture.geometry import frame_crop
    from core.capture.models import CapturedFrame
    pixels = np.full((6, 9, 4), 173, dtype=np.uint8)
    frame = CapturedFrame(1, 1, pixels, (10, 20), (100, 100), 1.)
    crop = frame_crop(frame, Rect(12, 21, 7, 5), exclusions_px=(Rect(16, 24, 5, 5),))
    assert np.all(crop[:3] == 173)
    assert np.all(crop[3:, :4] == 173)
    assert np.all(crop[3:, 4:] == 0)
    assert np.all(frame.pixels == 173)
    assert np.all(pixels == 173)
    crop[0, 0] = 0
    assert np.all(frame.pixels == 173)


def test_overlapping_fractional_masks_cover_union_without_reintroducing_pixels():
    from core.capture.geometry import frame_crop
    from core.capture.models import CapturedFrame
    frame = CapturedFrame(1, 1, np.full((3, 7, 4), 255, np.uint8), (0, 0), (7, 3), 1.)
    crop = frame_crop(frame, Rect(0, 0, 7, 3),
                      exclusions_px=(Rect(.5, 0, 2, 3), Rect(2, 0, 2.5, 3)))
    assert np.all(crop[:, :5] == 0)
    assert np.all(crop[:, 5:] == 255)


def test_partial_span_intersection_filters_text_in_original_ocr_order(span_factory):
    from core.capture.geometry import filter_excluded_spans
    first = span_factory('first', x=20, y=0, width=5, height=5)
    removed = span_factory('removed', x=2, y=2, width=10, height=5)
    last = span_factory('last', x=0, y=20, width=5, height=5)
    original = OcrResult('unfiltered text must never escape', spans=(first, removed, last))
    filtered = filter_excluded_spans(original, roi_rect_px=Rect(100, 200, 50, 50),
                                     exclusions_px=(Rect(110, 205, 5, 5),))
    assert filtered.text == 'first last'
    assert filtered.spans == (first, last)
    assert original.spans == (first, removed, last)


def test_span_touching_exclusion_edge_is_kept(span_factory):
    from core.capture.geometry import filter_excluded_spans
    span = span_factory('kept', x=0, y=0, width=10, height=10)
    filtered = filter_excluded_spans(OcrResult('stale', spans=(span,)),
                                     roi_rect_px=Rect(100, 200, 50, 50),
                                     exclusions_px=(Rect(110, 200, 10, 10),))
    assert filtered == OcrResult('kept', spans=(span,))


def test_overlapping_exclusions_cannot_restore_removed_spans(span_factory):
    from core.capture.geometry import filter_excluded_spans
    span = span_factory('removed', x=5, y=5, width=10, height=10)
    filtered = filter_excluded_spans(OcrResult('removed', spans=(span,)),
                                     roi_rect_px=Rect(100, 200, 50, 50),
                                     exclusions_px=(Rect(102, 202, 10, 10), Rect(105, 205, 20, 20)))
    assert filtered == OcrResult()


def test_full_roi_exclusion_returns_valid_empty_ocr(span_factory):
    from core.capture.geometry import filter_excluded_spans
    span = span_factory('removed', x=5, y=5, width=10, height=10)
    result = filter_excluded_spans(OcrResult('removed', spans=(span,)),
                                   roi_rect_px=Rect(100, 200, 50, 50),
                                   exclusions_px=(Rect(99, 199, 52, 52),))
    assert result == OcrResult()


def test_ocr_failure_is_preserved_even_when_entire_roi_is_excluded():
    from core.capture.geometry import filter_excluded_spans
    error = EngineError('ocr', 'recognizer failed', True)
    original = OcrResult(error=error)
    result = filter_excluded_spans(original, roi_rect_px=Rect(0, 0, 50, 50),
                                   exclusions_px=(Rect(0, 0, 50, 50),))
    assert result is original
    assert result.error is error


def test_subtitle_text_is_rebuilt_from_spans_even_without_exclusions(span_factory):
    from core.capture.geometry import filter_excluded_spans
    span = span_factory('actual')
    result = filter_excluded_spans(OcrResult('stale text', spans=(span,)),
                                   roi_rect_px=Rect(0, 0, 200, 100), exclusions_px=())
    assert result == OcrResult('actual', spans=(span,))
