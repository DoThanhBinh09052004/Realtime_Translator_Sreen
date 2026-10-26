"""Explicit application data allowlist for the one-folder release."""
from pathlib import Path
from core.ocr_models import validate_ocr_assets

def bundle_data(project_root: Path, model_root: Path) -> list[tuple[str, str]]:
    project_root, model_root = Path(project_root).resolve(), Path(model_root).resolve()
    manifest=validate_ocr_assets(model_root)
    logo=project_root/'ui/logo.png'
    if not logo.is_file() or not logo.stat().st_size:
        raise ValueError('Missing application logo.')
    entries=[(str(model_root/name), (Path('assets/ocr')/Path(name).parent).as_posix())
             for name in sorted(manifest['files'])]
    return entries+[(str(model_root/'manifest.json'),'assets/ocr'),(str(logo),'ui')]
