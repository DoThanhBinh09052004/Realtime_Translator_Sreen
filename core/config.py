import json
import os
import math
import re
import tempfile
import threading
from urllib.parse import urlsplit

from core.contracts import ProviderSettings, RuntimeSettings

_config_lock = threading.RLock()


class ConfigError(Exception):
    """A settings operation failed; messages must never contain secrets."""


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

SUPPORTED_LANGUAGES = {
    "English": "en",
    "Japanese": "japan",
    "Chinese": "ch",
    "Korean": "korean",
}

SUPPORTED_TARGETS = ["Vietnamese", "English"]

DEFAULT_REGION = {
    "top": 0,
    "left": 0,
    "width": 800,
    "height": 600
}


def _read_config(strict: bool = False) -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, ValueError):
        raw = {}
    except OSError:
        if strict:
            raise ConfigError("Không thể đọc cấu hình để lưu thiết lập.") from None
        raw = {}
    return normalize_config(raw)


def load_config() -> dict:
    """Read validated defaults without creating or repairing files on disk."""
    with _config_lock:
        return _read_config()


def _atomic_write(path: str, content: str) -> None:
    temporary = None
    try:
        # Close the temporary file before replace (required on Windows).
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(os.path.abspath(path)),
            prefix=".settings-", suffix=".tmp", delete=False,
        ) as f:
            temporary = f.name
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError):
        raise ConfigError("Không thể lưu thiết lập. Vui lòng kiểm tra quyền ghi và dung lượng ổ đĩa.") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def save_config_values(changes: dict) -> None:
    """Serialize a read/modify/write transaction, including multi-field updates."""
    with _config_lock:
        data = _read_config(strict=True)
        data.update(changes)
        try:
            content = json.dumps(normalize_config(data), ensure_ascii=False, indent=2, allow_nan=False)
        except (ValueError, TypeError):
            raise ConfigError("Dữ liệu thiết lập không hợp lệ.") from None
        _atomic_write(CONFIG_PATH, content)


def save_config(key: str, value):
    """Lưu từng trường cấu hình vào config.json"""
    save_config_values({key: value})


DEFAULT_BG_COLOR = "#1e1e2e"
DEFAULT_BG_OPACITY = 80
DEFAULT_TEXT_COLOR = "#ffffff"
DEFAULT_FONT_SIZE = 22
DEFAULT_OVERLAY_PRESET = "bottom_center"


def _bounded_int(value, default: int, low: int, high: int) -> int:
    if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
        return default
    return int(max(low, min(high, value)))


def normalize_config(raw: object) -> dict:
    """Validate known settings while retaining unrelated persisted fields."""
    cfg = dict(raw) if isinstance(raw, dict) else {}
    for field, default, low, high in (
        ("font_size", DEFAULT_FONT_SIZE, 14, 36),
        ("bg_opacity", DEFAULT_BG_OPACITY, 0, 100),
        ("interval_ms", 500, 100, 3000),
    ):
        cfg[field] = _bounded_int(cfg.get(field), default, low, high)
    for field, choices, default in (
        ("source_lang", SUPPORTED_LANGUAGES, "English"),
        ("target_lang", SUPPORTED_TARGETS, "Vietnamese"),
        ("current_provider", PROVIDERS, DEFAULT_PROVIDER),
        ("overlay_preset", ("bottom_center", "top_center", "bottom_left", "custom"), DEFAULT_OVERLAY_PRESET),
    ):
        value = cfg.get(field)
        cfg[field] = value if isinstance(value, str) and value in choices else default
    for field, default in (("bg_color", DEFAULT_BG_COLOR), ("text_color", DEFAULT_TEXT_COLOR)):
        value = cfg.get(field)
        cfg[field] = value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else default
    for field in ("overlay_x", "overlay_y"):
        value = cfg.get(field)
        cfg[field] = value if type(value) is int else None
    region = cfg.get("region")
    if (isinstance(region, dict)
            and all(type(region.get(k)) is int for k in DEFAULT_REGION)
            and region["width"] > 0 and region["height"] > 0):
        cfg["region"] = {k: region[k] for k in DEFAULT_REGION}
    else:
        cfg["region"] = DEFAULT_REGION.copy()
    models = cfg.get("provider_models")
    cfg["provider_models"] = {
        provider: model.strip() for provider, model in models.items()
        if provider in PROVIDERS and isinstance(model, str) and model.strip()
    } if isinstance(models, dict) else {}
    if not isinstance(cfg.get("model_id"), str) or not cfg["model_id"].strip():
        cfg.pop("model_id", None)
    try:
        cfg["custom_api_base_url"] = _normalize_custom_api_base_url(
            cfg.get("custom_api_base_url", ""), allow_empty=True,
        )
    except ConfigError:
        cfg["custom_api_base_url"] = ""
    return cfg


class State:
    """Quản lý trạng thái ứng dụng (ngôn ngữ, kiểu dáng phụ đề, vị trí) có tự động lưu"""
    def __init__(self):
        cfg = load_config()
        self.source = cfg.get("source_lang", "English")
        self.target = cfg.get("target_lang", "Vietnamese")
        self.bg_color = cfg.get("bg_color", DEFAULT_BG_COLOR)
        self.bg_opacity = int(cfg.get("bg_opacity", DEFAULT_BG_OPACITY))
        self.text_color = cfg.get("text_color", DEFAULT_TEXT_COLOR)
        self.font_size = int(cfg.get("font_size", DEFAULT_FONT_SIZE))
        self.overlay_preset = cfg.get("overlay_preset", DEFAULT_OVERLAY_PRESET)
        self.overlay_x = cfg.get("overlay_x", None)
        self.overlay_y = cfg.get("overlay_y", None)

    def update(self, **kwargs) -> None:
        names = {"source": "source_lang", "target": "target_lang"}
        names.update({k: k for k in (
            "bg_color", "bg_opacity", "text_color", "font_size",
            "overlay_preset", "overlay_x", "overlay_y",
        )})
        if any(k not in names for k in kwargs):
            raise ConfigError("Trường thiết lập không hợp lệ.")
        values = normalize_config({names[k]: v for k, v in kwargs.items()})
        changes = {names[k]: values[names[k]] for k in kwargs}
        save_config_values(changes)
        for k in kwargs:
            setattr(self, k, changes[names[k]])


def load_region() -> dict:
    """Đọc tọa độ vùng chụp từ file config.json"""
    return load_config().get("region", DEFAULT_REGION.copy())


def save_region(region: dict):
    """Lưu tọa độ vùng chụp vào file config.json"""
    save_config("region", region)


ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

PROVIDERS = {
    "Google Gemini": {
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-3.1-flash-lite",
        "models": [
            "gemini-3.8-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
        ],
        "placeholder": "AIzaSy...",
    },
    "OpenAI": {
        "env_key": "OPENAI_API_KEY",
        "base_url": None,
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano"],
        "placeholder": "sk-proj-...",
    },
    "DeepSeek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-flash",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "placeholder": "sk-...",
    },
    "Custom API": {
        "env_key": "CUSTOM_API_KEY",
        "base_url": None,
        "default_model": "model-name",
        "models": ["model-name"],
        "placeholder": "Nhập API key...",
    },
}

DEFAULT_PROVIDER = "Google Gemini"
DEFAULT_MODEL_ID = PROVIDERS[DEFAULT_PROVIDER]["default_model"]
AVAILABLE_MODELS = PROVIDERS[DEFAULT_PROVIDER]["models"]


def get_available_providers() -> list:
    """Trả về danh sách tên các LLM Provider được hỗ trợ"""
    return list(PROVIDERS.keys())


def load_active_provider() -> str:
    """Đọc provider hiện đang được chọn từ config.json"""
    val = load_config().get("current_provider")
    if val in PROVIDERS:
        return val
    return DEFAULT_PROVIDER


def save_active_provider(provider: str):
    """Lưu provider được chọn vào config.json"""
    if provider in PROVIDERS:
        save_config("current_provider", provider)


def _read_env() -> dict:
    with _config_lock:
        env_vars = {}
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
        except (OSError, UnicodeError):
            pass
        return env_vars


def _write_env_var(key: str, value: str):
    if not isinstance(value, str) or any(char in value for char in ("\n", "\r", "\0")):
        raise ConfigError("Giá trị thiết lập không hợp lệ.")
    with _config_lock:
        lines = []
        key_found = False
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            raise ConfigError("Không thể đọc tệp API key để lưu thiết lập.") from None

        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped == key:
                new_lines.append(f"{key}={value}\n")
                key_found = True
            else:
                new_lines.append(line)

        if not key_found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(f"{key}={value}\n")

        _atomic_write(ENV_PATH, "".join(new_lines))
        os.environ[key] = value


def load_provider_api_key(provider: str = None) -> str:
    """Đọc API key của provider từ file .env (hoặc biến môi trường)"""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    env_key = PROVIDERS[provider]["env_key"]
    val = _read_env().get(env_key, "")
    if not val:
        val = os.environ.get(env_key, "")
    if val == "key_ở_đây":
        return ""
    return val


def save_provider_api_key(provider: str, key: str):
    """Lưu API key của provider vào file .env"""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    env_key = PROVIDERS[provider]["env_key"]
    _write_env_var(env_key, key)


def load_provider_model_id(provider: str = None) -> str:
    """Đọc model ID đã lưu của provider từ config.json"""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    cfg = PROVIDERS[provider]
    models_map = load_config().get("provider_models", {})
    val = models_map.get(provider)
    if not val and provider == "OpenAI":
        val = _read_env().get("MODEL_ID") or load_config().get("model_id")
    return val or cfg["default_model"]


def save_provider_model_id(provider: str, model_id: str):
    """Lưu model ID của provider vào config.json"""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    with _config_lock:
        models_map = _read_config(strict=True)["provider_models"]
        models_map[provider] = model_id
        save_config_values({"provider_models": models_map, "model_id": model_id})


def _normalize_custom_api_base_url(value: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigError("Base URL phải bắt đầu bằng http:// hoặc https://.")
    value = value.strip().rstrip("/")
    if not value and allow_empty:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError("Base URL phải bắt đầu bằng http:// hoặc https://.")
    return value


def load_custom_api_base_url() -> str:
    return load_config().get("custom_api_base_url", "")


def save_custom_api_base_url(base_url: str) -> None:
    save_config("custom_api_base_url", _normalize_custom_api_base_url(base_url))


def load_provider_settings(provider: str | None = None) -> ProviderSettings:
    with _config_lock:
        if provider not in PROVIDERS:
            provider = load_active_provider()
        base_url = (load_custom_api_base_url() if provider == "Custom API"
                    else PROVIDERS[provider]["base_url"])
        return ProviderSettings(
            name=provider, model_id=load_provider_model_id(provider),
            api_key=load_provider_api_key(provider), base_url=base_url,
        )


def load_runtime_settings(state: State, interval_ms: int) -> RuntimeSettings:
    with _config_lock:
        return RuntimeSettings(
            source_lang=state.source, target_lang=state.target,
            provider=load_provider_settings(),
            interval_ms=_bounded_int(interval_ms, 500, 100, 3000),
        )


# ===== Backward Compatibility Aliases =====
def load_api_key() -> str:
    """[Alias] Đọc API key của active provider"""
    return load_provider_api_key(load_active_provider())


def save_api_key(key: str):
    """[Alias] Lưu API key cho active provider"""
    save_provider_api_key(load_active_provider(), key)


def load_model_id() -> str:
    """[Alias] Đọc model ID của active provider"""
    return load_provider_model_id(load_active_provider())


def save_model_id(model_id: str):
    """[Alias] Lưu model ID cho active provider"""
    save_provider_model_id(load_active_provider(), model_id)
