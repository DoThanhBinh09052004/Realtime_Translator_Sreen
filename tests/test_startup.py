import subprocess
import sys

from ui.startup import StartupLoader


def test_entry_import_does_not_load_ocr_runtime():
    result = subprocess.run([sys.executable, '-c',
        "import main, sys; assert 'paddleocr' not in sys.modules; assert 'core.worker' not in sys.modules"],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_loader_reports_stages_and_finishes_without_creating_models(qtbot, monkeypatch):
    imported = []
    monkeypatch.setattr('ui.startup.importlib.import_module', imported.append)
    loader = StartupLoader()
    stages = []
    loader.stage.connect(stages.append)
    with qtbot.waitSignal(loader.finished, timeout=2000):
        loader.start()
    assert not loader.error
    assert 'engines.ocr' in imported
    assert stages == ['Đang tải thiết lập…', 'Đang chuẩn bị OCR…', 'Đang tải giao diện…']


def test_loader_failure_finishes_instead_of_hanging(qtbot, monkeypatch):
    def fail(_):
        raise ImportError('missing runtime')
    monkeypatch.setattr('ui.startup.importlib.import_module', fail)
    loader = StartupLoader()
    with qtbot.waitSignal(loader.finished, timeout=2000):
        loader.start()
    assert loader.error
