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
class LanguageChoice:
    id: str
    config_name: str
    label: str


@dataclass(frozen=True)
class OcrPageState:
    source: str
    target: str
    interval_ms: int
    region: tuple[int, int, int, int] | None
    source_choices: tuple[LanguageChoice, ...] | None = None
    source_notice: str = ''
    performance_mode: str = 'high'
    auto_threads: bool = True
    threads: int = 4


@dataclass(frozen=True)
class PackageRowState:
    language_id: str
    title: str
    phase: str
    status_text: str
    detail_text: str
    downloaded_bytes: int
    total_bytes: int
    reclaimable_bytes: int
    action: str | None
    action_enabled: bool
    action_reason: str = ''


@dataclass(frozen=True)
class LanguagePacksState:
    rows: tuple[PackageRowState, ...]
    busy: bool
    message: str = ''


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


@dataclass(frozen=True)
class DailyReadiness:
    ready: bool
    reason: str
    action: str | None = None  # select_source/select_regions/manage_packs/configure_provider


@dataclass(frozen=True)
class DailyRunState:
    phase: str  # stopped/starting/running/stopping/waiting_source
    message: str
    can_toggle: bool
    preview_enabled: bool


@dataclass(frozen=True)
class PresentedPair:
    source_text: str
    translated_text: str
    region_id: str | None = None


@dataclass(frozen=True)
class PresentedTranslation:
    revision: int
    mode: str
    sequence: int
    pairs: tuple[PresentedPair, ...] = ()
