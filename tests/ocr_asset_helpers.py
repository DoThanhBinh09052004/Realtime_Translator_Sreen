from pathlib import Path
import hashlib
import json

SOURCES = {
 'det/en': 'whl/det/en/en_PP-OCRv3_det_infer',
 'det/ml': 'whl/det/ml/Multilingual_PP-OCRv3_det_infer',
 'rec/en': 'whl/rec/en/en_PP-OCRv4_rec_infer',
 'rec/japan': 'whl/rec/japan/japan_PP-OCRv4_rec_infer',
 'cls': 'whl/cls/ch_ppocr_mobile_v2.0_cls_infer',
}

def make_source_cache(root):
    cache, dictionaries, license_path = root/'cache', root/'utils', root/'LICENSE'
    for target, source in SOURCES.items():
        for name in ('inference.pdmodel', 'inference.pdiparams', 'inference.pdiparams.info'):
            path = cache/source/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((target+name).encode())
    for name in ('en_dict.txt', 'dict/japan_dict.txt'):
        path = dictionaries/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    license_path.write_bytes(b'Apache license fixture')
    return cache, dictionaries, license_path

def make_assets(root):
    root.mkdir(parents=True)
    names = [f'{d}/{n}' for d in SOURCES for n in ('inference.pdmodel','inference.pdiparams')]
    names += ['dict/en_dict.txt','dict/japan_dict.txt','NOTICE.paddleocr.txt']
    files = {}
    for name in names:
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(schema=1, paddleocr_version='2.10.0', ocr_version='PP-OCRv4', languages=['en','japan'], files=files, provenance=SOURCES)
    (root/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return root
