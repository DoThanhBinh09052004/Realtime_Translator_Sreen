"""Explicit application data allowlist for the one-folder release."""
from pathlib import Path
import hashlib
from core.ocr_models import validate_ocr_assets
from core.language_pack_catalog import load_pack_catalog
from core.language_pack_contracts import pack_error


def validate_pack_resources(model_root: Path):
    """Validate only pinned, small resources; weights use the legacy manifest."""
    root = Path(model_root).resolve()
    catalog = load_pack_catalog(root / 'language-packs.json')
    for resource in catalog.resources.values():
        path = (root / resource.path).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size != resource.size_bytes:
            raise pack_error('integrity')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != resource.sha256:
            raise pack_error('integrity')
    return catalog

def bundle_data(project_root: Path, model_root: Path) -> list[tuple[str, str]]:
    project_root, model_root = Path(project_root).resolve(), Path(model_root).resolve()
    manifest=validate_ocr_assets(model_root)
    catalog=validate_pack_resources(model_root)
    logo=project_root/'ui/logo.png'
    if not logo.is_file() or not logo.stat().st_size:
        raise ValueError('Missing application logo.')
    entries=[(str(model_root/name), (Path('assets/ocr')/Path(name).parent).as_posix())
             for name in sorted(manifest['files'])]
    for resource in catalog.resources.values():
        if resource.path not in manifest['files']:
            entries.append((str(model_root/resource.path), (Path('assets/ocr')/Path(resource.path).parent).as_posix()))
    return entries+[(str(model_root/'manifest.json'),'assets/ocr'),(str(model_root/'language-packs.json'),'assets/ocr'),(str(logo),'ui')]
