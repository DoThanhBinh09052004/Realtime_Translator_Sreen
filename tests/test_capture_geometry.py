"""Source raster geometry stays independent of desktop/Qt coordinates."""
from uuid import UUID

import numpy as np
import pytest

from core.blocks.models import CaptureGeometry, Rect, ScreenMapping


def _profile(*rectangles):
    from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect
    regions = tuple(CaptureRegion(str(UUID(int=i + 1)), str(i), NormalizedRect(*r), True)
                    for i, r in enumerate(rectangles))
    return CaptureProfile(1, 'desktop', 'monitor', None, regions, ())


def _frame(pixels, *, origin=(0, 0), size=None):
    from core.capture.models import CapturedFrame
    return CapturedFrame(1, 1, pixels, origin, size or (pixels.shape[1], pixels.shape[0]), 1.0)


def test_normalized_region_uses_whole_source_raster():
    from core.capture.geometry import region_rect_px
    from core.capture.models import NormalizedRect
    assert region_rect_px(NormalizedRect(.25, .5, .5, .25), (1920, 1080)) == Rect(480, 540, 960, 270)


def test_fractional_outer_edges_round_outward_and_clip():
    from core.capture.geometry import region_rect_px
    from core.capture.models import NormalizedRect
    assert region_rect_px(NormalizedRect(.19, .21, .81, .79), (7, 11)) == Rect(1, 2, 6, 9)


@pytest.mark.parametrize('size', [(0, 10), (10, -1), (5.5, 10), (True, 10)])
def test_raster_size_must_contain_positive_integer_dimensions(size):
    from core.capture.geometry import region_rect_px
    from core.capture.models import NormalizedRect
    with pytest.raises(ValueError):
        region_rect_px(NormalizedRect(0, 0, 1, 1), size)


@pytest.mark.parametrize('scale', [1.25, 1.5])
def test_negative_monitor_origin_and_qt_scale_only_affect_overlay_mapping(scale):
    from core.capture.geometry import region_rect_px, to_source_rect
    from core.capture.models import NormalizedRect
    from core.blocks.geometry import ocr_rect_to_overlay, overlay_window_rect
    source_size = (1000, 750)
    screen = ScreenMapping('left', Rect(-1000 / scale, 0, 1000 / scale, 750 / scale),
                           Rect(-1000, 0, 1000, 750))
    geometry = CaptureGeometry(screen.physical_rect, screen, source_size)
    roi = region_rect_px(NormalizedRect(.25, .4, .5, .4), source_size)
    assert roi == Rect(250, 300, 500, 300)
    source_rect = to_source_rect(Rect(10, 20, 50, 30), roi)
    assert source_rect == Rect(260, 320, 50, 30)
    overlay = ocr_rect_to_overlay(source_rect, geometry)
    assert (overlay.x, overlay.y, overlay.width, overlay.height) == pytest.approx(
        (260 / scale, 320 / scale, 50 / scale, 30 / scale))
    assert overlay_window_rect(geometry).x == -1000 / scale


@pytest.mark.parametrize('rectangles,expected', [
    (((0, 0, .5, 1), (.5, 0, .5, 1)), (Rect(0, 0, 4, 5), Rect(3, 0, 4, 5))),
    (((.5, 0, .5, 1), (0, 0, .5, 1)), (Rect(3, 0, 4, 5), Rect(0, 0, 4, 5))),
    (((0, 0, 1, .5), (0, .5, 1, .5)), (Rect(0, 0, 7, 3), Rect(0, 2, 7, 3))),
    (((0, .5, 1, .5), (0, 0, 1, .5)), (Rect(0, 2, 7, 3), Rect(0, 0, 7, 3))),
])
def test_fractional_touching_edges_belong_to_first_profile_region(rectangles, expected):
    from core.capture.geometry import frame_crop, raster_ownership_masks, resolve_region_crops
    profile = _profile(*rectangles)
    crops = tuple(resolve_region_crops(profile, (7, 5)).values())
    assert crops == expected
    masks = raster_ownership_masks(profile, (7, 5))
    occupancy = np.zeros((5, 7), dtype=np.uint8)
    frame = _frame(np.full((5, 7, 4), 255, np.uint8))
    for region, rect in zip(profile.regions, crops):
        crop = frame_crop(frame, rect, exclusions_px=masks[region.id])
        occupancy[rect.y:rect.bottom, rect.x:rect.right] += (crop[:, :, 0] > 0)
    assert np.all(occupancy == 1)


def test_disabled_region_does_not_claim_shared_edge_pixels():
    from dataclasses import replace
    from core.capture.geometry import resolve_region_crops
    profile = _profile((0, 0, .5, 1), (.5, 0, .5, 1))
    profile = replace(profile, regions=(replace(profile.regions[0], enabled=False), profile.regions[1]))
    assert resolve_region_crops(profile, (7, 5)) == {profile.regions[1].id: Rect(3, 0, 4, 5)}


def test_one_pixel_source_assigns_all_shared_pixels_to_first_region():
    from core.capture.geometry import raster_ownership_masks, resolve_region_crops
    profile = _profile((0, 0, .5, 1), (.5, 0, .5, 1))
    first_id, last_id = (r.id for r in profile.regions)
    assert resolve_region_crops(profile, (1, 5)) == {first_id: Rect(0, 0, 1, 5), last_id: Rect(0, 0, 1, 5)}
    assert raster_ownership_masks(profile, (1, 5)) == {first_id: (), last_id: (Rect(0, 0, 1, 5),)}


@pytest.mark.parametrize('rectangles,first_rect,last_rect,mask', [
    (((0, 0, .5, .5), (.5, 0, .5, 1)), Rect(0, 0, 4, 3), Rect(3, 0, 4, 5), Rect(3, 0, 1, 3)),
    (((0, 0, .5, .5), (.5, .5, .5, .5)), Rect(0, 0, 4, 3), Rect(3, 2, 4, 3), Rect(3, 2, 1, 1)),
])
def test_partial_shared_edges_mask_only_overlap_and_keep_unshared_pixels(rectangles, first_rect, last_rect, mask):
    from core.capture.geometry import frame_crop, raster_ownership_masks, resolve_region_crops
    profile = _profile(*rectangles)
    first_id, last_id = (r.id for r in profile.regions)
    assert resolve_region_crops(profile, (7, 5)) == {first_id: first_rect, last_id: last_rect}
    masks = raster_ownership_masks(profile, (7, 5))
    assert masks == {first_id: (), last_id: (mask,)}
    frame = _frame(np.full((5, 7, 4), 173, np.uint8))
    crop = frame_crop(frame, last_rect, exclusions_px=masks[last_id])
    assert np.all(crop[-1, 0] == 173)
    assert np.all(crop[0, 0] == 0)
    assert np.all(crop[:, -1] == 173)


def test_mss_bounding_origin_is_subtracted_before_cropping():
    from core.capture.geometry import frame_crop
    pixels = np.arange(5 * 9 * 4, dtype=np.uint8).reshape(5, 9, 4)
    frame = _frame(pixels, origin=(100, 200), size=(1920, 1080))
    crop = frame_crop(frame, Rect(102, 201, 7, 4))
    np.testing.assert_array_equal(crop, pixels[1:5, 2:9])
    assert crop.shape == (4, 7, 4)
    assert crop.flags.c_contiguous and crop.flags.writeable
    assert not np.shares_memory(crop, frame.pixels)


@pytest.mark.parametrize('rect', [Rect(99, 200, 2, 2), Rect(108, 200, 2, 2),
                                 Rect(100, 199, 2, 2), Rect(100, 204, 2, 2),
                                 Rect(100.5, 200, 2, 2)])
def test_frame_crop_rejects_uncovered_or_nonraster_roi(rect):
    from core.capture.geometry import frame_crop
    frame = _frame(np.zeros((5, 9, 4), dtype=np.uint8), origin=(100, 200), size=(1920, 1080))
    with pytest.raises(ValueError):
        frame_crop(frame, rect)


def test_frame_crop_rejects_source_size_from_stale_context():
    from core.capture.geometry import frame_crop
    frame = _frame(np.zeros((5, 9, 4), dtype=np.uint8))
    with pytest.raises(ValueError):
        frame_crop(frame, Rect(0, 0, 9, 5), source_size_px=(10, 5))
def test_migrated_legacy_pixel_edges_do_not_expand_from_float_noise():
    from core.capture.profile import migrate_legacy_region
    from core.capture.geometry import region_rect_px
    from core.blocks.models import Rect, ScreenMapping
    screen = ScreenMapping('test', Rect(0, 0, 100, 100), Rect(0, 0, 100, 100))
    profile = migrate_legacy_region(dict(left=29, top=0, width=1, height=1), (screen,))
    assert region_rect_px(profile.regions[0].rect, (100, 100)) == Rect(29, 0, 1, 1)
