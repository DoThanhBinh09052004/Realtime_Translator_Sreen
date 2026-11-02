"""Tiny release resources independent of Paddle and upstream model data."""
import hashlib
import json
from pathlib import Path


def make_pack_resources(models: Path, package: Path) -> Path:
    package.mkdir(parents=True, exist_ok=True)
    (package / 'dict').mkdir(exist_ok=True)
    payloads = {
        'dict-en': ('dict/en_dict.txt', 'en_dict.txt', (models / 'dict/en_dict.txt').read_bytes()),
        'dict-ja': ('dict/japan_dict.txt', 'dict/japan_dict.txt', (models / 'dict/japan_dict.txt').read_bytes()),
        'dict-ch': ('pack_resources/ch_dict.txt', 'ppocr_keys_v1.txt', b'Chinese dictionary'),
        'dict-ko': ('pack_resources/korean_dict.txt', 'dict/korean_dict.txt', b'Korean dictionary'),
        'notice': ('NOTICE.paddleocr.txt', None, (models / 'NOTICE.paddleocr.txt').read_bytes()),
    }
    resources = {}
    for key, (destination, origin, data) in payloads.items():
        if origin:
            (package / origin).write_bytes(data)
        resources[key] = dict(path=destination, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    files = [dict(path=name, size_bytes=3, sha256=hashlib.sha256(b'abc').hexdigest())
             for name in ('inference.pdmodel', 'inference.pdiparams')]
    components = {key: dict(id=key, revision='v1', url='https://paddleocr.bj.bcebos.com/fixture.tar',
                            archive_size_bytes=10240, archive_sha256='a' * 64, archive_root='fixture', files=files)
                  for key in ('det-en', 'det-ml', 'det-ch', 'rec-en', 'rec-ja', 'rec-ch', 'rec-ko', 'cls')}
    raw = dict(schema=1, paddleocr_version='2.10.0', ocr_version='PP-OCRv4', components=components, resources=resources)
    catalog = package / 'language-packs.json'
    catalog.write_text(json.dumps(raw), encoding='utf-8')
    return catalog
