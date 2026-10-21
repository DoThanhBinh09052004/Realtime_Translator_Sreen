# Isolated application tests

Use Python 3.10 and the runtime dependencies in requirements.txt, then install
requirements-dev.txt into the same environment. For an existing uv environment:

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
```

pytest.ini limits default discovery to tests/. Do not run the legacy scratch
scripts: some write application settings and API keys beside the source.

conftest.py installs guards before test collection imports application modules:
config and env paths point to temporary files, provider keys and MODEL_ID are
removed from the process environment, socket connections/DNS and desktop capture
raise explicit errors, OpenAI construction uses a fake completion client, and
PaddleOCR imports use a fake module without loading Paddle or downloading models.
Qt uses the offscreen platform. Each test then gets fresh tmp_path files and fake
engine state. No real provider key is required or read.

Fixtures: isolated_config (autouse), fake_translator, fake_ocr, fake_clock, qtbot.
Set fake_translator.return_value or fake_ocr.return_value to control text; inspect
call_args_list for calls. fake_clock.now() starts at zero; advance(seconds) moves
it without sleeping. These fakes currently match the application's string engine
API; update them with the structured engine contracts in S03.

S01 verification covers temporary persistence, separate fake provider keys/models,
collection-time guards, blocked network/capture, fake engine calls, no Paddle
import, clock advancement and offscreen Qt. It does not exercise real OCR, HTTP,
or desktop capture.
