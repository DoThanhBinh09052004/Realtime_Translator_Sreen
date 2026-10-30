"""Convert source-local regions, copy OCR crops, and apply exclusions.

Raster coordinates never include a monitor's global origin or Qt scale. Shared
rounding pixels belong to the first enabled region in profile order; callers
must combine ``raster_ownership_masks`` with user exclusions before OCR and
``filter_excluded_spans`` afterwards.
"""
from math import ceil, floor, ulp
from numbers import Integral

import numpy as np

from core.blocks.models import Rect
from core.capture.models import CapturedFrame, CaptureProfile, NormalizedRect
from core.contracts import OcrResult


def _source_size(size: tuple[int, int]) -> tuple[int, int]:
    if (len(size) != 2 or any(isinstance(v, bool) or not isinstance(v, Integral) or v <= 0
                             for v in size)):
        raise ValueError('Source size must contain two positive pixel dimensions')
    return int(size[0]), int(size[1])


def _intersection(first: Rect, second: Rect) -> Rect | None:
    left, top = max(first.x, second.x), max(first.y, second.y)
    right, bottom = min(first.right, second.right), min(first.bottom, second.bottom)
    return Rect(left, top, right - left, bottom - top) if right > left and bottom > top else None


def region_rect_px(rect: NormalizedRect, source_size_px: tuple[int, int]) -> Rect:
    """Round normalized bounds outward and clip them to the full source."""
    width, height = _source_size(source_size_px)
    # A legacy integer edge normalized and multiplied back may drift a few
    # floating-point ULPs (e.g. .29 * 100). Preserve that pixel boundary while
    # still rounding genuinely fractional selections outward.
    def edge(value):
        nearest = round(value)
        return nearest if abs(value - nearest) <= 4 * ulp(value) else value
    left, top = max(0, floor(edge(rect.x * width))), max(0, floor(edge(rect.y * height)))
    right = min(width, ceil(edge((rect.x + rect.width) * width)))
    bottom = min(height, ceil(edge((rect.y + rect.height) * height)))
    return Rect(left, top, right - left, bottom - top)


def resolve_region_crops(profile: CaptureProfile, source_size_px: tuple[int, int]) -> dict[str, Rect]:
    """Return enabled ROI bounding crops in display order.

    Crops retain every unshared pixel, including partial shared-edge cases that
    cannot be represented by a smaller rectangle. Apply ownership masks too.
    """
    _source_size(source_size_px)
    return {region.id: region_rect_px(region.rect, source_size_px)
            for region in profile.regions if region.enabled}


def raster_ownership_masks(profile: CaptureProfile,
                           source_size_px: tuple[int, int]) -> dict[str, tuple[Rect, ...]]:
    """Return source-local shared-pixel rectangles masked from each later ROI."""
    crops = resolve_region_crops(profile, source_size_px)
    masks = {}
    earlier = []
    for region_id, crop in crops.items():
        masks[region_id] = tuple(overlap for previous in earlier
                                if (overlap := _intersection(crop, previous)) is not None)
        earlier.append(crop)
    return masks


def frame_crop(frame: CapturedFrame, rect: Rect, *, exclusions_px: tuple[Rect, ...] = (),
               source_size_px: tuple[int, int] | None = None) -> np.ndarray:
    """Return an owned contiguous BGRA crop with source-local exclusions blacked.

    ``source_size_px`` is the expected context size when available. Coverage
    failures and stale source dimensions are errors; crops are never clipped.
    """
    size = _source_size(frame.source_size_px)
    if source_size_px is not None and _source_size(source_size_px) != size:
        raise ValueError('Frame source size does not match capture context')
    if any(isinstance(v, bool) or int(v) != v for v in (rect.x, rect.y, rect.width, rect.height)):
        raise ValueError('Crop must use integer pixel coordinates')
    origin = frame.image_origin_px
    if (len(origin) != 2 or any(isinstance(v, bool) or not isinstance(v, Integral) or v < 0
                                 for v in origin)):
        raise ValueError('Frame origin must contain nonnegative pixel coordinates')
    origin_x, origin_y = map(int, origin)
    height, width = frame.pixels.shape[:2]
    bounds = Rect(origin_x, origin_y, width, height)
    if not Rect(0, 0, *size).contains(bounds):
        raise ValueError('Frame lies outside its source canvas')
    if not bounds.contains(rect):
        raise ValueError('Frame does not cover the requested ROI')
    left, top = int(rect.x) - origin_x, int(rect.y) - origin_y
    crop = frame.pixels[top:top + int(rect.height), left:left + int(rect.width)].copy(order='C')
    for exclusion in exclusions_px:
        overlap = _intersection(rect, exclusion)
        if overlap is None:
            continue
        x, y = floor(overlap.x) - int(rect.x), floor(overlap.y) - int(rect.y)
        right, bottom = ceil(overlap.right) - int(rect.x), ceil(overlap.bottom) - int(rect.y)
        crop[y:bottom, x:right] = 0
    return crop


def to_source_rect(rect: Rect, roi_rect_px: Rect) -> Rect:
    """Translate an OCR-local rectangle into source-local pixels."""
    return Rect(rect.x + roi_rect_px.x, rect.y + roi_rect_px.y, rect.width, rect.height)


def filter_excluded_spans(ocr: OcrResult, *, roi_rect_px: Rect,
                          exclusions_px: tuple[Rect, ...]) -> OcrResult:
    """Discard spans whose source bounding rectangles overlap exclusions."""
    if ocr.error is not None:
        return ocr
    kept = []
    for span in ocr.spans:
        xs, ys = zip(*span.polygon)
        left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
        if right > left and bottom > top:
            bounds = to_source_rect(Rect(left, top, right - left, bottom - top), roi_rect_px)
            if any(bounds.intersects(exclusion) for exclusion in exclusions_px):
                continue
        kept.append(span)
    return OcrResult(text=' '.join(span.text for span in kept).strip(), spans=tuple(kept))
