"""Sequential per-ROI OCR scheduling without retaining capture frames."""
from copy import deepcopy
from dataclasses import dataclass, field

import cv2
import numpy as np

from core.capture.geometry import (filter_excluded_spans, frame_crop, raster_ownership_masks,
                                   region_rect_px, resolve_region_crops)
from core.capture.models import CaptureObservation, RegionOcrObservation
from core.contracts import EngineError, OcrResult
from core.languages import language_by_config_name
from core.retry import RetryState


@dataclass
class _RegionState:
    thumbnail: np.ndarray | None = None
    last_scan_s: float = float('-inf')
    last_order: int = -1
    confirm: bool = False
    retry: RetryState = field(default_factory=RetryState)
    retry_due_s: float = 0.
    exhausted: bool = False


class RegionScanner:
    def __init__(self, profile, *, ocr_reader, clock):
        self._ocr_reader = ocr_reader
        self._clock = clock
        self._scan_id = 0
        self._order = 0
        self.reset(profile)

    def reset(self, profile) -> None:
        self._profile = profile
        self._states = {region.id: _RegionState() for region in profile.regions if region.enabled}
        self._source_key = None

    def observe(self, frame, *, settings, context, revision, force_regions,
                dynamic_masks_px, is_current):
        if frame is None or not is_current() or frame.binding_epoch != context.binding_epoch:
            return None
        if frame.source_size_px != context.geometry.image_size_px:
            raise ValueError('Frame source size does not match capture context')
        if context.source_kind != self._profile.source_kind:
            raise ValueError('Capture context does not match the region profile')
        source_key = (context.binding_epoch, context.source_kind, frame.source_size_px, settings.source_lang)
        # Work transactionally: cancelled OCR never commits partial batch state.
        states = ({region_id: _RegionState() for region_id in self._states}
                  if source_key != self._source_key else deepcopy(self._states))
        crops = resolve_region_crops(self._profile, frame.source_size_px)
        ownership = raster_ownership_masks(self._profile, frame.source_size_px)
        exclusions = tuple(region_rect_px(rect, frame.source_size_px) for rect in self._profile.exclusions)
        if context.source_kind == 'desktop':
            exclusions += tuple(dynamic_masks_px)
        started = self._clock()
        observations = []
        order = self._order
        try:
            language = language_by_config_name(settings.source_lang).ocr_code
        except ValueError:
            language = None
        # Last completion and a monotonic tie-breaker rotate even when a fake or
        # very fast OCR completes several regions at the same clock instant.
        for region_id in sorted(states, key=lambda name: (states[name].last_scan_s, states[name].last_order)):
            if not is_current():
                return None
            state = states[region_id]
            masks = tuple(mask for mask in exclusions + ownership[region_id]
                          if crops[region_id].intersects(mask))
            crop = frame_crop(frame, crops[region_id], exclusions_px=masks,
                              source_size_px=context.geometry.image_size_px)
            gray = cv2.cvtColor(crop, cv2.COLOR_BGRA2GRAY)
            del crop
            thumb = cv2.resize(gray, (100, 40), interpolation=cv2.INTER_LINEAR)
            changed = (state.thumbnail is None
                       or float(np.mean(cv2.absdiff(state.thumbnail, thumb))) > 1.2)
            forced = region_id in force_regions
            now = self._clock()
            if changed:
                state.retry.reset()
                state.retry_due_s = 0.
                state.exhausted = False
            retrying = state.retry_due_s > 0
            due = (changed or forced or state.confirm or retrying
                   or now-state.last_scan_s >= max(1000, settings.interval_ms)/1000)
            if not due or state.exhausted or now < state.retry_due_s:
                continue
            if not is_current():
                return None
            try:
                if language is None:
                    ocr = OcrResult(error=EngineError('ocr_model_missing', 'Ngôn ngữ nguồn không được hỗ trợ.', False))
                else:
                    ocr = self._ocr_reader(gray, lang=language)
            except Exception:
                ocr = OcrResult(error=EngineError('ocr', 'Không thể nhận diện chữ trong ảnh.', True))
            completed = self._clock()
            if not is_current():
                return None
            # Preserve text-only reader output when no masks can exclude it.
            if masks:
                ocr = filter_excluded_spans(ocr, roi_rect_px=crops[region_id], exclusions_px=masks)
            state.thumbnail = thumb
            state.last_scan_s = completed
            state.last_order = order
            order += 1
            if ocr.error is None:
                state.confirm = changed
                state.retry.reset()
                state.retry_due_s = 0.
                state.exhausted = False
            else:
                state.confirm = False
                retry_due = state.retry.next_due(completed, ocr.error)
                state.retry_due_s = retry_due or 0.
                state.exhausted = retry_due is None
            observations.append(RegionOcrObservation(region_id, frame.captured_at_s, completed, ocr))
            if completed-started >= max(0, settings.interval_ms)/1000:
                break
        if not is_current():
            return None
        self._states = states
        self._source_key = source_key
        self._order = order
        if not observations:
            return None
        self._scan_id += 1
        return CaptureObservation(revision, self._scan_id, settings, context, tuple(observations))
