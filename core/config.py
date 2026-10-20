import json
import os

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


def load_config() -> dict:
    """Đọc toàn bộ cấu hình từ file config.json"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Lỗi đọc file config: {e}")
    return {}


def save_config(key: str, value):
    """Lưu từng trường cấu hình vào config.json"""
    try:
        data = load_config()
        data[key] = value
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Lỗi lưu config: {e}")


DEFAULT_BG_COLOR = "#1e1e2e"
DEFAULT_BG_OPACITY = 80
DEFAULT_TEXT_COLOR = "#ffffff"
DEFAULT_FONT_SIZE = 22
DEFAULT_OVERLAY_PRESET = "bottom_center"


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

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
            if k == "source":
                save_config("source_lang", v)
            elif k == "target":
                save_config("target_lang", v)
            elif k in ("bg_color", "bg_opacity", "text_color", "font_size", "overlay_preset", "overlay_x", "overlay_y"):
                save_config(k, v)


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
            "gemini-4-argon",
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
    env_vars = {}
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
        except Exception as e:
            print(f"⚠️ Lỗi đọc .env: {e}")
    return env_vars


def _write_env_var(key: str, value: str):
    try:
        lines = []
        key_found = False
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()

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

        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        os.environ[key] = value
    except Exception as e:
        print(f"⚠️ Lỗi ghi .env: {e}")


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
    models_map = load_config().get("provider_models", {})
    models_map[provider] = model_id
    save_config("provider_models", models_map)
    save_config("model_id", model_id)
    if provider == "OpenAI":
        _write_env_var("MODEL_ID", model_id)


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




