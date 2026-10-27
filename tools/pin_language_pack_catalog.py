"""Author release locks from the installed PaddleOCR 2.10.0 distribution.

This explicitly invoked release tool uses real HTTPS archives, never installs
models, and never imports Paddle. Keep --work-dir for an independent smoke run.
"""
import argparse
import ast
import hashlib
from importlib.metadata import distribution as installed_distribution
import json
from pathlib import Path
import sys
import tarfile
import tempfile

import httpx

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.language_pack_catalog import ALLOWED_ARCHIVE_FILES, MAX_ARCHIVE_BYTES, safe_relative, validate_pack_catalog

_MODELS = {'det-en':('det','en'), 'det-ml':('det','ml'), 'det-ch':('det','ch'),
           'rec-en':('rec','en'), 'rec-ja':('rec','japan'), 'rec-ch':('rec','ch'),
           'rec-ko':('rec','korean'), 'cls':('cls','ch')}


def _hash_stream(stream):
    digest=hashlib.sha256(); size=0
    for chunk in iter(lambda: stream.read(65536), b''):
        digest.update(chunk); size+=len(chunk)
    return size,digest.hexdigest()


def pin_catalog(work_dir: Path, *, distribution=None, package_root: Path | None = None, client=None) -> dict:
    package=distribution or installed_distribution('paddleocr')
    if package.version != '2.10.0':
        raise ValueError('Preparation requires PaddleOCR 2.10.0.')
    package_root=Path(package_root or package.locate_file('paddleocr'))
    tree=ast.parse((package_root/'paddleocr.py').read_text(encoding='utf-8'))
    assignments=[node for node in tree.body if isinstance(node, ast.Assign) and
                 any(isinstance(t,ast.Name) and t.id=='MODEL_URLS' for t in node.targets)]
    models=ast.literal_eval(assignments[0].value)['OCR']['PP-OCRv4']
    work_dir=Path(work_dir); work_dir.mkdir(parents=True,exist_ok=True)
    owned=client is None
    client=client or httpx.Client(follow_redirects=False, timeout=httpx.Timeout(15,connect=5), transport=httpx.HTTPTransport(retries=0))
    result=dict(schema=1,paddleocr_version='2.10.0',ocr_version='PP-OCRv4',components={},resources={})
    try:
        for id,(kind,code) in _MODELS.items():
            url=models[kind][code]['url']
            # Validate URL before issuing any release-authoring request.
            from urllib.parse import urlsplit
            parsed=urlsplit(url)
            if parsed.scheme!='https' or parsed.hostname!='paddleocr.bj.bcebos.com' or parsed.username or parsed.password:
                raise ValueError('Unexpected artifact host')
            archive=work_dir/(id+'.tar')
            with client.stream('GET',url,follow_redirects=False) as response:
                response.raise_for_status()
                if response.is_redirect: raise ValueError('Redirect forbidden')
                with archive.open('wb') as stream:
                    total=0
                    for chunk in response.iter_bytes(65536):
                        total+=len(chunk)
                        if total>MAX_ARCHIVE_BYTES: raise ValueError('Archive too large')
                        stream.write(chunk)
            with archive.open('rb') as stream: archive_size,archive_hash=_hash_stream(stream)
            files=[]; root=None; seen=set()
            with tarfile.open(archive,'r:*') as tar:
                for member in tar:
                    name=safe_relative(member.name.rstrip('/') if member.isdir() else member.name)
                    parts=name.split('/')
                    if name in seen: raise ValueError('Duplicate archive member')
                    seen.add(name)
                    if root is None: root=parts[0]
                    if parts[0]!=root: raise ValueError('Multiple roots')
                    if member.isdir() and len(parts)==1: continue
                    if not member.isfile() or len(parts)!=2 or parts[1] not in ALLOWED_ARCHIVE_FILES:
                        raise ValueError('Unexpected archive member')
                    stream=tar.extractfile(member)
                    with stream: size,digest=_hash_stream(stream)
                    files.append(dict(path=parts[1],size_bytes=size,sha256=digest))
            result['components'][id]=dict(id=id,revision='paddleocr210-'+archive_hash[:16],url=url,
                archive_size_bytes=archive_size,archive_sha256=archive_hash,archive_root=root,files=files)
        for id,code in [('dict-en','en'),('dict-ja','japan'),('dict-ch','ch'),('dict-ko','korean')]:
            source=package_root/models['rec'][code]['dict_path'].removeprefix('./')
            with source.open('rb') as stream: size,digest=_hash_stream(stream)
            target={'dict-en':'dict/en_dict.txt','dict-ja':'dict/japan_dict.txt',
                    'dict-ch':'pack_resources/ch_dict.txt','dict-ko':'pack_resources/korean_dict.txt'}[id]
            result['resources'][id]=dict(path=target,size_bytes=size,sha256=digest)
        with (package_root/'LICENSE').open('rb') as stream: size,digest=_hash_stream(stream)
        result['resources']['notice']=dict(path='NOTICE.paddleocr.txt',size_bytes=size,sha256=digest)
        validate_pack_catalog(result)
        return result
    finally:
        if owned: client.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--replace',action='store_true')
    parser.add_argument('--work-dir',type=Path)
    args=parser.parse_args()
    if args.output.exists() and not args.replace:
        parser.error('Output exists; use --replace to replace it explicitly.')
    with tempfile.TemporaryDirectory(prefix='ocr-release-') as temporary:
        raw=pin_catalog(args.work_dir or Path(temporary))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(raw,indent=2)+'\n',encoding='utf-8')
    print(args.output)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
