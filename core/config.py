import json
import os
import math
import re
import tempfile
import threading
import sys
from pathlib import Path

from core.contracts import ProviderSettings, RuntimeSettings, ProviderCapabilities
from core.paths import get_app_paths
from core.secrets import SecretStore, SecretStoreError
from core.endpoint_policy import EndpointPolicyError, normalize_custom_api_endpoint

_config_lock = threading.RLock()


class ConfigError(Exception):
    """A settings operation failed; messages must never contain secrets."""


LEGACY_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config.json'
CONFIG_PATH = str(get_app_paths().config_dir / 'config.json')
_secret_store = None


def get_secret_store():
    global _secret_store
    with _config_lock:
        if _secret_store is None:
            _secret_store = SecretStore(get_app_paths().config_dir / 'credentials')
        return _secret_store


def initialize_user_storage(*, legacy_config=None):
    """Copy legacy settings once; never mutate the original or import its keys."""
    if Path(CONFIG_PATH).exists():
        return
    legacy = Path(legacy_config) if legacy_config is not None else LEGACY_CONFIG_PATH
    try:
        raw = json.loads(legacy.read_text(encoding='utf-8')) if legacy.is_file() else {}
    except (OSError, ValueError, UnicodeError):
        raw = {}
    _atomic_write(CONFIG_PATH, json.dumps(normalize_config(raw), ensure_ascii=False, indent=2))

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
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Close the temporary file before replace (required on Windows).
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(os.path.abspath(path)),
            prefix=".settings-", suffix=".tmp", delete=False, newline='',
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
    def without_secrets(value):
        if isinstance(value, dict):
            return {k: without_secrets(v) for k, v in value.items()
                    if isinstance(k, str) and k.casefold() not in ('api_key', 'credentials', 'secrets', 'access_token')
                    and not k.casefold().endswith('_api_key')}
        if isinstance(value, list):
            return [without_secrets(v) for v in value]
        return value
    cfg = without_secrets(cfg)
    cfg['schema_version'] = 1
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
        ("overlay_mode", ("subtitle", "blocks"), "subtitle"),
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
        self.overlay_mode = cfg.get("overlay_mode", "subtitle")

    def update(self, **kwargs) -> None:
        names = {"source": "source_lang", "target": "target_lang"}
        names.update({k: k for k in (
            "bg_color", "bg_opacity", "text_color", "font_size",
            "overlay_preset", "overlay_x", "overlay_y", "overlay_mode",
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
    "Google Translate": {
        "env_key": None, "base_url": None, "default_model": "",
        "models": [], "placeholder": "",
    },
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

DEFAULT_PROVIDER = "Google Translate"
DEFAULT_MODEL_ID = PROVIDERS[DEFAULT_PROVIDER]["default_model"]
AVAILABLE_MODELS = PROVIDERS[DEFAULT_PROVIDER]["models"]


def get_available_providers() -> list:
    """Trả về danh sách tên các LLM Provider được hỗ trợ"""
    return list(PROVIDERS.keys())


def get_provider_capabilities(provider: str | None = None) -> ProviderCapabilities:
    provider = provider if provider in PROVIDERS else load_active_provider()
    return ProviderCapabilities(False, False, False) if provider == 'Google Translate' else ProviderCapabilities(True, True, provider == 'Custom API')


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


def load_provider_api_key(provider: str = None) -> str:
    """Read protected/session credentials; development env access is opt-in."""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    env_key = PROVIDERS[provider]["env_key"]
    if env_key is None:
        return ""
    try:
        val = get_secret_store().get(provider)
    except SecretStoreError:
        return ''
    if val is None and not getattr(sys, 'frozen', False) and os.environ.get('TRANSLATE_HUD_DEV_ENV') == '1':
        val = os.environ.get(env_key) or _read_env().get(env_key)
    return '' if not val or val == 'key_ở_đây' else val


def save_provider_api_key(provider: str, key: str, *, persist: bool = True):
    """Never write credentials into configuration, .env or os.environ."""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    env_key = PROVIDERS[provider]["env_key"]
    if env_key is None:
        return
    try:
        if key == '':
            get_secret_store().delete(provider)
        else:
            get_secret_store().set(provider, key, persist=persist)
    except SecretStoreError as error:
        raise ConfigError(str(error)) from None


def provider_key_storage(provider: str) -> str:
    if not get_provider_capabilities(provider).requires_api_key:
        return 'none'
    try:
        return get_secret_store().storage(provider)
    except SecretStoreError:
        return 'unavailable'


def import_legacy_provider_key(provider: str, *, persist: bool):
    env_key = PROVIDERS.get(provider, {}).get('env_key')
    key = _read_env().get(env_key, '') if env_key else ''
    if not key or key == 'key_ở_đây':
        raise ConfigError('Không tìm thấy key cũ cho công cụ đã chọn.')
    save_provider_api_key(provider, key, persist=persist)


def remove_legacy_provider_key(provider: str):
    """Explicit cleanup only after the same legacy key was protected successfully."""
    env_key = PROVIDERS.get(provider, {}).get('env_key')
    with _config_lock:
        legacy = _read_env().get(env_key, '')
        if not legacy or provider_key_storage(provider) != 'saved' or load_provider_api_key(provider) != legacy:
            raise ConfigError('Chỉ xóa key cũ sau khi đã lưu chính key đó bằng mã hóa Windows.')
        try:
            with open(ENV_PATH, encoding='utf-8', newline='') as stream:
                lines = stream.readlines()
        except (OSError, UnicodeError):
            raise ConfigError('Không thể đọc tệp key cũ.') from None
        kept = [line for line in lines if line.strip().split('=', 1)[0].strip() != env_key]
        _atomic_write(ENV_PATH, ''.join(kept))


def load_provider_model_id(provider: str = None) -> str:
    """Đọc model ID đã lưu của provider từ config.json"""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    cfg = PROVIDERS[provider]
    if not get_provider_capabilities(provider).supports_models:
        return ""
    models_map = load_config().get("provider_models", {})
    val = models_map.get(provider)
    if not val and provider == "OpenAI":
        val = load_config().get("model_id")
        if not val and not getattr(sys, 'frozen', False) and os.environ.get('TRANSLATE_HUD_DEV_ENV') == '1':
            val = _read_env().get('MODEL_ID')
    return val or cfg["default_model"]


def save_provider_model_id(provider: str, model_id: str):
    """Lưu model ID của provider vào config.json"""
    if not provider or provider not in PROVIDERS:
        provider = load_active_provider()
    if not get_provider_capabilities(provider).supports_models:
        return
    with _config_lock:
        models_map = _read_config(strict=True)["provider_models"]
        models_map[provider] = model_id
        save_config_values({"provider_models": models_map, "model_id": model_id})


def _normalize_custom_api_base_url(value: str, *, allow_empty: bool = False) -> str:
    try:
        return normalize_custom_api_endpoint(value, allow_empty=allow_empty)
    except EndpointPolicyError as error:
        raise ConfigError(str(error)) from None


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
            overlay_mode=state.overlay_mode,
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
