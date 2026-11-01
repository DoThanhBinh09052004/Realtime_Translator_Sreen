import json
from pathlib import Path

import pytest

from core import config


@pytest.mark.parametrize("raw", [[], None, 42, "bad", {
    "font_size": "bad", "bg_opacity": None, "current_provider": [],
    "source_lang": {}, "target_lang": False, "overlay_preset": [],
    "provider_models": [], "region": {"width": -1},
}])
def test_bad_config_values_use_defaults(raw):
    Path(config.CONFIG_PATH).write_text(json.dumps(raw), encoding="utf-8")
    state = config.State()
    assert (state.font_size, state.bg_opacity) == (22, 80)
    assert (state.source, state.target) == ("English", "Vietnamese")
    assert config.load_region() == config.DEFAULT_REGION
    assert config.load_active_provider() == config.DEFAULT_PROVIDER
    assert isinstance(config.load_provider_model_id(), str)


def test_normalize_config_contract():
    cfg = config.normalize_config({"font_size": "bad", "bg_opacity": None})
    assert (cfg["font_size"], cfg["bg_opacity"]) == (22, 80)
    assert config.normalize_config([])["region"]["width"] == 800


@pytest.mark.parametrize("field, value, expected", [
    ("font_size", 2, 14), ("font_size", 99, 36),
    ("bg_opacity", -1, 0), ("bg_opacity", 200, 100),
    ("interval_ms", 1, 100), ("interval_ms", 9000, 3000),
    ("font_size", True, 22), ("bg_opacity", False, 80),
    ("interval_ms", "500", 500), ("interval_ms", None, 500),
    ("font_size", float("nan"), 22), ("font_size", float("inf"), 22),
    ("bg_color", "red", "#1e1e2e"), ("text_color", "#fff", "#ffffff"),
    ("overlay_x", True, None), ("overlay_y", "12", None),
])
def test_normalizes_numeric_and_color_values(field, value, expected):
    assert config.normalize_config({field: value})[field] == expected


@pytest.mark.parametrize("region", [None, [], {},
    {"left": 0, "top": 0, "width": 0, "height": 20},
    {"left": False, "top": 0, "width": 20, "height": 20},
    {"left": 0, "top": 0, "width": 20.0, "height": 20},
])
def test_invalid_region_uses_defaults(region):
    assert config.normalize_config({"region": region})["region"] == config.DEFAULT_REGION


def test_negative_screen_coordinates_and_custom_models_are_preserved():
    region = {"left": -1920, "top": -1080, "width": 800, "height": 600}
    raw = {"region": region, "overlay_x": -900, "overlay_y": -20,
           "overlay_preset": "custom", "provider_models": {"OpenAI": "custom-model"},
           "other_setting": "preserve"}
    normalized = config.normalize_config(raw)
    for key, value in raw.items():
        assert normalized[key] == value
    assert raw["region"] == region


@pytest.mark.parametrize("content", ["{", "null", "[]"])
def test_loading_invalid_json_does_not_rewrite_file(content):
    path = Path(config.CONFIG_PATH)
    path.write_text(content, encoding="utf-8")
    assert config.load_config()["font_size"] == 22
    assert path.read_text(encoding="utf-8") == content


def test_missing_config_is_not_created_on_load():
    assert config.load_config()["interval_ms"] == 500
    assert not Path(config.CONFIG_PATH).exists()


def test_ocr_performance_config_defaults_and_normalization():
    cfg = config.normalize_config({})
    assert cfg["ocr_performance_mode"] == "high"
    assert cfg["ocr_auto_threads"] is True
    assert cfg["ocr_threads"] == 4

    # Valid values
    custom = config.normalize_config({
        "ocr_performance_mode": "eco",
        "ocr_auto_threads": False,
        "ocr_threads": 2,
    })
    assert custom["ocr_performance_mode"] == "eco"
    assert custom["ocr_auto_threads"] is False
    assert custom["ocr_threads"] == 2

    # Invalid values fallback to defaults or bounds
    invalid = config.normalize_config({
        "ocr_performance_mode": "invalid_mode",
        "ocr_auto_threads": "not_bool",
        "ocr_threads": -5,
    })
    assert invalid["ocr_performance_mode"] == "high"
    assert invalid["ocr_auto_threads"] is True
    assert invalid["ocr_threads"] == 1


def test_resolve_ocr_threads():
    import os
    total_cores = os.cpu_count() or 4
    # Auto mode: allocates ~50% cores, bounded between 2 and 6
    expected_auto = max(2, min(6, total_cores // 2))
    assert config.resolve_ocr_threads(auto=True, custom_threads=8) == expected_auto

    # Manual mode: bounds within [1, total_cores]
    assert config.resolve_ocr_threads(auto=False, custom_threads=1) == 1
    assert config.resolve_ocr_threads(auto=False, custom_threads=999) == total_cores
    assert config.resolve_ocr_threads(auto=False, custom_threads=-2) == 1

def test_context_config_is_opt_in_strict_bool():
    from core.config import normalize_config
    assert normalize_config({})['context_enabled'] is False
    assert normalize_config({'context_enabled':'false'})['context_enabled'] is False
    assert normalize_config({'context_enabled':True})['context_enabled'] is True

