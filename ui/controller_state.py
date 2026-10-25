"""Immutable values used to render controller views."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AiPageState:
    provider: str
    model_id: str
    models: tuple[str, ...]
    api_key: str = field(repr=False)
    placeholder: str
    base_url: str = ""
    requires_api_key: bool = True
    supports_models: bool = True
    supports_base_url: bool = False
    key_storage: str = 'none'


@dataclass(frozen=True)
class OcrPageState:
    source: str
    target: str
    interval_ms: int
    region: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class SubtitlePageState:
    bg_color: str
    text_color: str
    bg_opacity: int
    font_size: int
    preset: str
    x: int | None
    y: int | None
    overlay_mode: str = 'subtitle'


@dataclass(frozen=True)
class ControllerSnapshot:
    ai: AiPageState
    ocr: OcrPageState
    subtitle: SubtitlePageState
