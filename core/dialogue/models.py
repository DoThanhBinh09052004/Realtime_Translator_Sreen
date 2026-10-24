from dataclasses import dataclass
from core.contracts import RuntimeSettings, OcrResult
from core.blocks.models import CaptureGeometry

RequestKey = tuple[int, int, int, int]
ActiveTurnKey = tuple[int, int, int]


@dataclass(frozen=True)
class DialogueObservation:
    revision: int
    scan_id: int
    captured_at_s: float
    completed_at_s: float
    settings: RuntimeSettings
    ocr: OcrResult
    geometry: CaptureGeometry | None


@dataclass(frozen=True)
class TrackPresentation:
    turn_id: int
    text_version: int
    source_text: str
    text: str
