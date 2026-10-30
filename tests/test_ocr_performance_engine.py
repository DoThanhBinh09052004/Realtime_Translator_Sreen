import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from engines import ocr


def test_normalize_ocr_crop_bucket_padding():
    # Width 50 -> padded to 64 (next multiple of 32)
    img = np.ones((48, 50, 3), dtype=np.uint8) * 255
    padded = ocr.normalize_ocr_crop(img, bucket_step=32)
    assert padded.shape == (48, 64, 3)
    # The original pixels are intact
    assert np.array_equal(padded[:, :50], img)
    # The padded pixels on the right are zero
    assert np.all(padded[:, 50:] == 0)

    # Width already multiple of 32 -> untouched
    img32 = np.ones((48, 64, 3), dtype=np.uint8) * 128
    assert ocr.normalize_ocr_crop(img32, bucket_step=32) is img32

    # Grayscale image
    img_gray = np.ones((48, 70), dtype=np.uint8)
    padded_gray = ocr.normalize_ocr_crop(img_gray, bucket_step=32)
    assert padded_gray.shape == (48, 96)

    # Invalid input
    assert ocr.normalize_ocr_crop(None) is None
    assert ocr.normalize_ocr_crop("invalid") == "invalid"


@patch("engines.ocr.PaddleOCR")
def test_simple_paddle_ocr_passes_performance_flags(mock_paddle):
    # High performance: enable_mkldnn=True, cpu_threads=4
    engine = ocr.SimplePaddleOCR(lang="en", enable_mkldnn=True, cpu_threads=4)
    assert mock_paddle.call_args.kwargs["enable_mkldnn"] is True
    assert mock_paddle.call_args.kwargs["cpu_threads"] == 4
    engine.close()

    mock_paddle.reset_mock()
    # Eco mode: enable_mkldnn=False, cpu_threads=2
    engine_eco = ocr.SimplePaddleOCR(lang="en", enable_mkldnn=False, cpu_threads=2)
    assert mock_paddle.call_args.kwargs["enable_mkldnn"] is False
    assert mock_paddle.call_args.kwargs["cpu_threads"] == 2
    engine_eco.close()


@patch("engines.ocr.PaddleOCR")
def test_get_ocr_engine_cache_identity_changes_recreates_engine(mock_paddle):
    ocr.release_ocr_engine()
    e1 = ocr.get_ocr_engine(lang="en", enable_mkldnn=True, cpu_threads=4)
    # Same settings -> cache hit
    e2 = ocr.get_ocr_engine(lang="en", enable_mkldnn=True, cpu_threads=4)
    assert e1 is e2
    assert mock_paddle.call_count == 1

    # Change to Eco mode -> cache miss, re-instantiates
    e3 = ocr.get_ocr_engine(lang="en", enable_mkldnn=False, cpu_threads=2)
    assert e3 is not e1
    assert mock_paddle.call_count == 2

    # Change threads -> cache miss, re-instantiates
    e4 = ocr.get_ocr_engine(lang="en", enable_mkldnn=False, cpu_threads=6)
    assert e4 is not e3
    assert mock_paddle.call_count == 3
    ocr.release_ocr_engine()
