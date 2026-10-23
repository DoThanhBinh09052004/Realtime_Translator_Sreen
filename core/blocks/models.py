from dataclasses import dataclass
from math import isfinite
from core.contracts import RuntimeSettings, TranslationResult


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        if not all(isfinite(v) for v in (self.x, self.y, self.width, self.height)) or min(self.width, self.height) <= 0:
            raise ValueError('Rectangle must have finite coordinates and positive size')

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    def contains(self, other):
        return self.x <= other.x and self.y <= other.y and self.right >= other.right and self.bottom >= other.bottom

    def intersects(self, other):
        return self.x < other.right and self.right > other.x and self.y < other.bottom and self.bottom > other.y


@dataclass(frozen=True)
class ScreenMapping:
    name: str
    logical_rect: Rect
    physical_rect: Rect


@dataclass(frozen=True)
class CaptureGeometry:
    region_px: Rect
    screen: ScreenMapping
    image_size_px: tuple[int, int]


@dataclass(frozen=True)
class TextBlock:
    block_id: int
    source_text: str
    source_rect: Rect


@dataclass(frozen=True)
class BlockJob:
    revision: int
    block_id: int
    source_text: str
    settings: RuntimeSettings


@dataclass(frozen=True)
class BlockTranslationResult:
    revision: int
    block_id: int
    source_text: str
    result: TranslationResult


@dataclass(frozen=True)
class OverlayBlock:
    block_id: int
    source_text: str
    translated_text: str
    source_rect: Rect


@dataclass(frozen=True)
class OverlayFrame:
    revision: int
    frame_id: int
    geometry: CaptureGeometry
    blocks: tuple[OverlayBlock, ...]
