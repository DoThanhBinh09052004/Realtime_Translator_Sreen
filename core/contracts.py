"""Immutable values exchanged between settings, engines and worker threads."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ProviderCapabilities:
    requires_api_key: bool = True
    supports_models: bool = True
    supports_base_url: bool = False


@dataclass(frozen=True)
class ProviderSettings:
    name: str
    model_id: str
    api_key: str = field(repr=False)
    base_url: str | None


@dataclass(frozen=True)
class RuntimeSettings:
    source_lang: str
    target_lang: str
    provider: ProviderSettings
    interval_ms: int
    overlay_mode: Literal['subtitle', 'blocks'] = 'subtitle'


@dataclass(frozen=True)
class EngineError:
    code: str
    user_message: str
    retryable: bool
    retry_after_s: float | None = None


@dataclass(frozen=True)
class TranslationResult:
    text: str = ""
    error: EngineError | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    from_cache: bool = False

    def __post_init__(self):
        if self.error is not None:
            object.__setattr__(self, "text", "")


@dataclass(frozen=True)
class OcrSpan:
    text: str
    polygon: tuple[tuple[float, float], ...]
    confidence: float


@dataclass(frozen=True)
class OcrResult:
    text: str = ""
    error: EngineError | None = None
    spans: tuple[OcrSpan, ...] = ()

    def __post_init__(self):
        if self.error is not None:
            object.__setattr__(self, "text", "")
            object.__setattr__(self, "spans", ())


@dataclass(frozen=True)
class WorkerStatus:
    state: str
    message: str
    revision: int

    def __post_init__(self):
        if self.state not in {
            "stopped", "starting", "scanning", "translating",
            "retry_wait", "error", "stopping",
        }:
            raise ValueError("Unknown worker state")


@dataclass(frozen=True)
class TranslationStatus:
    provider: str
    revision: int
    session_id: int
    phase: Literal['active', 'retry_wait', 'paused', 'stopped']
    retries_issued: int = 0
    retry_at_s: float | None = None
