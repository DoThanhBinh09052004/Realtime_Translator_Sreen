import numpy as np
import pytest
from core.contracts import OcrResult, EngineError
from engines.ocr import SimplePaddleOCR


def test_paddle_preserves_polygon_confidence_and_flat_text():
    engine = SimplePaddleOCR()
    box = [[1, 2], [31, 2], [31, 12], [1, 12]]
    engine.ocr.ocr = lambda *a, **k: [[[box, ('Hello', .95)], [box, ('World', .8)]]]
    result = engine.extract_text(np.zeros((50, 50), dtype='uint8'))
    assert result.text == 'Hello World'
    assert result.spans[0].polygon == ((1., 2.), (31., 2.), (31., 12.), (1., 12.))
    assert result.spans[0].confidence == .95


@pytest.mark.parametrize('box', [None, [[0, 0]] * 3, [[float('nan'), 0]] * 4, [[0, 0]] * 4])
def test_bad_polygon_keeps_legacy_text_but_has_no_span(box):
    engine = SimplePaddleOCR()
    engine.ocr.ocr = lambda *a, **k: [[[box, ('Hello', .9)], None]]
    result = engine.extract_text(np.zeros((50, 50), dtype='uint8'))
    assert result.text == 'Hello'
    assert result.spans == ()


def test_ocr_error_clears_text_and_spans():
    from core.contracts import OcrSpan
    result = OcrResult('bad', EngineError('ocr', 'error', True), (OcrSpan('bad', (), 1),))
    assert result.text == '' and result.spans == ()


def test_legacy_contract_and_rect_validation(runtime_settings):
    from core.blocks.models import Rect
    assert OcrResult('Hello').spans == ()
    assert runtime_settings.overlay_mode == 'subtitle'
    assert 'fake-key' not in repr(runtime_settings)
    with pytest.raises(ValueError):
        Rect(0, 0, 0, 1)
    assert not Rect(0, 0, 10, 10).intersects(Rect(10, 0, 10, 10))


@pytest.mark.parametrize('confidence', [float('nan'), float('inf'), -.1, 1.1, None])
def test_invalid_confidence_keeps_text_without_span(confidence):
    engine = SimplePaddleOCR()
    box = [[1, 2], [31, 2], [31, 12], [1, 12]]
    engine.ocr.ocr = lambda *a, **k: [[[box, ('Hello', confidence)]]]
    result = engine.extract_text(np.zeros((50, 50), dtype='uint8'))
    assert result.text == 'Hello'
    assert not result.spans
