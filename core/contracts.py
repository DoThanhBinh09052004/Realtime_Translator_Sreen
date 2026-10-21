"""Immutable values exchanged between settings, engines and worker threads."""
from dataclasses import dataclass, field


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

    def __post_init__(self):
        if self.error is not None:
            object.__setattr__(self, "text", "")


@dataclass(frozen=True)
class OcrResult:
    text: str = ""
    error: EngineError | None = None

    def __post_init__(self):
        if self.error is not None:
            object.__setattr__(self, "text", "")


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
