"""Tool contracts; synthetic arrays here are not native WGC evidence."""
import builtins
import importlib.util
from pathlib import Path

import numpy as np
import pytest


PROBE = Path(__file__).resolve().parents[1] / "tools" / "probe_window_capture.py"


def load_probe(monkeypatch):
    assert PROBE.is_file(), "Task 0 probe tool has not been implemented"
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] == "windows_capture":
            raise AssertionError("Native capture must not import during tool import/argument parsing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    spec = importlib.util.spec_from_file_location("capture_probe_contract", PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_defaults_do_not_save_images_and_import_is_lazy(monkeypatch):
    probe = load_probe(monkeypatch)
    args = probe.parse_args([])
    assert args.seconds == 10
    assert args.output == Path("scratch/window-capture-probe.json")
    assert args.save_images is False


@pytest.mark.parametrize("seconds", ["0", "-1", "nan", "inf", "abc"])
def test_invalid_duration_is_clear_cli_error(monkeypatch, seconds, capsys):
    probe = load_probe(monkeypatch)
    with pytest.raises(SystemExit) as error:
        probe.parse_args(["--seconds", seconds])
    assert error.value.code == 2
    assert "seconds" in capsys.readouterr().err


def test_output_directory_is_rejected_before_native_import(monkeypatch, tmp_path, capsys):
    probe = load_probe(monkeypatch)
    with pytest.raises(SystemExit) as error:
        probe.parse_args(["--output", str(tmp_path)])
    assert error.value.code == 2
    assert "output" in capsys.readouterr().err


def test_crop_uses_client_offset_and_preserves_bgra(monkeypatch):
    probe = load_probe(monkeypatch)
    # A 6x5 DWM surface with the 3x2 client starting at (2, 1).
    frame = np.zeros((5, 6, 4), dtype=np.uint8)
    frame[1:3, 2:5] = (17, 31, 47, 255)
    crop = probe.crop_client(frame, (100, 200, 106, 205), (102, 201, 105, 203))
    assert crop.shape == (2, 3, 4)
    assert crop[0, 0].tolist() == [17, 31, 47, 255]


@pytest.mark.parametrize("shape,dtype", [((5, 6, 3), np.uint8), ((5, 6, 4), np.float32)])
def test_unsupported_frame_format_fails_instead_of_claiming_mapping(monkeypatch, shape, dtype):
    probe = load_probe(monkeypatch)
    with pytest.raises(ValueError, match="BGRA8"):
        probe.crop_client(np.zeros(shape, dtype=dtype), (0, 0, 6, 5), (0, 0, 3, 2))


def test_client_outside_surface_does_not_silently_clip(monkeypatch):
    probe = load_probe(monkeypatch)
    with pytest.raises(ValueError, match="outside"):
        probe.crop_client(np.zeros((5, 6, 4), dtype=np.uint8), (0, 0, 6, 5), (4, 3, 8, 7))
