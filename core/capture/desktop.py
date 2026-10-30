"""Synchronous MSS capture, constructed and drained by its worker owner."""
from threading import get_ident
from typing import Callable

import numpy as np

from core.blocks.models import Rect
from core.capture.models import CaptureContext, CapturedFrame, SourceStatus
from core.contracts import EngineError


class DesktopCaptureSource:
    def __init__(self, *, mss_factory=None,
                 on_terminal: Callable[[SourceStatus], None] | None = None):
        self._mss_factory = mss_factory
        self._on_terminal = on_terminal
        self._native = None
        self._owner = None
        self._context = None
        self._region = None
        self._origin = (0, 0)
        self._sequence = 0
        self._status = SourceStatus(0, 'stopped')

    def _check_owner(self):
        if self._owner is not None and get_ident() != self._owner:
            raise RuntimeError('Capture must be accessed on its owner thread')

    def _fail(self):
        self._status = SourceStatus(self._context.binding_epoch, 'error',
            EngineError('capture_failed', 'Không thể chụp nguồn màn hình.', False))
        if self._on_terminal is not None:
            self._on_terminal(self._status)

    def open(self, context: CaptureContext, *, roi_rects_px: tuple[Rect, ...] | None = None) -> None:
        self._check_owner()
        if self._native is not None or self._status.phase not in ('stopped', 'error'):
            raise RuntimeError('Capture source is already open')
        if context.source_kind != 'desktop':
            raise ValueError('MSS requires a desktop source')
        width, height = context.geometry.image_size_px
        bounds = Rect(0, 0, width, height)
        if (any(isinstance(value, bool) or int(value) != value for value in (width, height))
                or min(width, height) <= 0):
            raise ValueError('Source dimensions must be positive integer pixels')
        if roi_rects_px is None:
            crop = bounds
        else:
            if not roi_rects_px:
                raise ValueError('Runtime capture requires at least one ROI')
            for rect in roi_rects_px:
                if (not bounds.contains(rect) or any(isinstance(value, bool) or int(value) != value
                        for value in (rect.x, rect.y, rect.width, rect.height))):
                    raise ValueError('ROI must lie within the source in integer pixels')
            left = min(rect.x for rect in roi_rects_px)
            top = min(rect.y for rect in roi_rects_px)
            right = max(rect.right for rect in roi_rects_px)
            bottom = max(rect.bottom for rect in roi_rects_px)
            crop = Rect(left, top, right-left, bottom-top)
        source_rect = context.geometry.region_px
        if (source_rect.width != width or source_rect.height != height
                or int(source_rect.x) != source_rect.x or int(source_rect.y) != source_rect.y):
            raise ValueError('Desktop geometry must describe the full physical source raster')
        self._context = context
        self._owner = get_ident()
        self._origin = (int(crop.x), int(crop.y))
        self._region = dict(left=int(source_rect.x+crop.x), top=int(source_rect.y+crop.y),
                            width=int(crop.width), height=int(crop.height))
        self._status = SourceStatus(context.binding_epoch, 'opening')
        try:
            factory = self._mss_factory
            if factory is None:
                import mss
                factory = mss.mss
            self._native = factory()
        except Exception:
            self._fail()

    def read_latest(self, *, now_s: float) -> CapturedFrame | None:
        self._check_owner()
        if self._native is None or self._status.phase not in ('opening', 'ready'):
            return None
        try:
            pixels = np.asarray(self._native.grab(self._region))
            if pixels.shape != (self._region['height'], self._region['width'], 4):
                raise ValueError('MSS returned an unexpected raster size')
            sequence = self._sequence + 1
            frame = CapturedFrame(self._context.binding_epoch, sequence, pixels, self._origin,
                                  self._context.geometry.image_size_px, now_s)
        except Exception:
            self._fail()
            return None
        self._sequence = sequence
        self._status = SourceStatus(self._context.binding_epoch, 'ready')
        return frame

    def status(self) -> SourceStatus:
        return self._status

    def close(self) -> None:
        self._check_owner()
        epoch = self._status.binding_epoch
        self._status = SourceStatus(epoch, 'stopping')
        native = self._native
        if native is not None:
            # Keep ownership if draining raises; never report a false stop.
            native.close()
        self._native = None
        self._context = None
        self._region = None
        self._owner = None
        self._status = SourceStatus(epoch, 'stopped')
