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

