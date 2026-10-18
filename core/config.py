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


class State:
    """Quản lý trạng thái ứng dụng (ngôn ngữ, kiểu dáng phụ đề) có tự động lưu"""
    def __init__(self):
        cfg = load_config()
        self.source = cfg.get("source_lang", "English")
        self.target = cfg.get("target_lang", "Vietnamese")
        self.bg_color = cfg.get("bg_color", DEFAULT_BG_COLOR)
        self.bg_opacity = int(cfg.get("bg_opacity", DEFAULT_BG_OPACITY))
        self.text_color = cfg.get("text_color", DEFAULT_TEXT_COLOR)

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
            if k == "source":
                save_config("source_lang", v)
            elif k == "target":
                save_config("target_lang", v)
            elif k in ("bg_color", "bg_opacity", "text_color"):
                save_config(k, v)


def load_region() -> dict:
    """Đọc tọa độ vùng chụp từ file config.json"""
    return load_config().get("region", DEFAULT_REGION.copy())


def save_region(region: dict):
    """Lưu tọa độ vùng chụp vào file config.json"""
    save_config("region", region)


ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

DEFAULT_MODEL_ID = "gpt-4o-mini"

AVAILABLE_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
]


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


def load_api_key() -> str:
    """Đọc API key từ file .env (hoặc biến môi trường)"""
    val = _read_env().get("OPENAI_API_KEY", "")
    if not val:
        val = os.environ.get("OPENAI_API_KEY", "")
    if val == "key_ở_đây":
        return ""
    return val


def save_api_key(key: str):
    """Lưu API key vào file .env (tự động tạo .env nếu chưa có)"""
    _write_env_var("OPENAI_API_KEY", key)


def load_model_id() -> str:
    """Đọc model ID từ file .env hoặc config.json"""
    val = _read_env().get("MODEL_ID")
    if not val:
        val = load_config().get("model_id", DEFAULT_MODEL_ID)
    return val or DEFAULT_MODEL_ID


def save_model_id(model_id: str):
    """Lưu model ID vào file .env"""
    _write_env_var("MODEL_ID", model_id)
    save_config("model_id", model_id)



