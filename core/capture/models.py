"""Immutable values shared by capture adapters, scanning and presentation."""
from dataclasses import dataclass
from math import isfinite
from typing import Literal

import numpy as np

from core.blocks.models import CaptureGeometry
from core.contracts import EngineError, OcrResult, RuntimeSettings


@dataclass(frozen=True)
class NormalizedRect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        values = (self.x, self.y, self.width, self.height)
        if (any(type(v) not in (int, float) or not isfinite(v) for v in values)
                or not (0 <= self.x <= 1 and 0 <= self.y <= 1)
                or not (0 < self.width <= 1 and 0 < self.height <= 1)
                or self.x + self.width > 1 or self.y + self.height > 1):
            raise ValueError('Rectangle must have finite normalized coordinates and positive size')


@dataclass(frozen=True)
class CaptureRegion:
    id: str
    name: str
    rect: NormalizedRect
    enabled: bool


@dataclass(frozen=True)
class CaptureProfile:
    version: int
    source_kind: Literal['desktop', 'window']
    monitor_name: str | None
    window_hint: str | None
    regions: tuple[CaptureRegion, ...]
    exclusions: tuple[NormalizedRect, ...]

    def __post_init__(self):
        object.__setattr__(self, 'regions', tuple(self.regions))
        object.__setattr__(self, 'exclusions', tuple(self.exclusions))


@dataclass(frozen=True)
class WindowIdentity:
    hwnd: int
    pid: int
    process_started_100ns: int


@dataclass(frozen=True)
class CaptureContext:
    binding_epoch: int
    geometry_sequence: int
    source_kind: Literal['desktop', 'window']
    window: WindowIdentity | None
    geometry: CaptureGeometry


@dataclass(frozen=True)
class CapturedFrame:
    binding_epoch: int
    sequence: int
    pixels: np.ndarray
    image_origin_px: tuple[int, int]
    source_size_px: tuple[int, int]
    captured_at_s: float

    def __post_init__(self):
        if (not isinstance(self.pixels, np.ndarray) or self.pixels.dtype != np.uint8
                or self.pixels.ndim != 3 or self.pixels.shape[2] != 4
                or min(self.pixels.shape[:2]) <= 0):
            raise ValueError('Captured pixels must be a nonempty BGRA uint8 image')
        pixels = np.array(self.pixels, copy=True, order='C')
        pixels.flags.writeable = False
        object.__setattr__(self, 'pixels', pixels)
        object.__setattr__(self, 'image_origin_px', tuple(self.image_origin_px))
        object.__setattr__(self, 'source_size_px', tuple(self.source_size_px))


@dataclass(frozen=True)
class RegionOcrObservation:
    region_id: str
    captured_at_s: float
    completed_at_s: float
    ocr: OcrResult


@dataclass(frozen=True)
class CaptureObservation:
    revision: int
    scan_id: int
    settings: RuntimeSettings
    context: CaptureContext
    regions: tuple[RegionOcrObservation, ...]

    def __post_init__(self):
        object.__setattr__(self, 'regions', tuple(self.regions))


@dataclass(frozen=True)
class SourceStatus:
    binding_epoch: int
    phase: Literal['opening', 'ready', 'unavailable', 'error', 'stopping', 'stopped']
    error: EngineError | None = None


@dataclass(frozen=True)
class CaptureStatus:
    revision: int
    binding_epoch: int
    phase: Literal['opening', 'ready', 'unavailable', 'error', 'stopping', 'stopped']
    error: EngineError | None = None
