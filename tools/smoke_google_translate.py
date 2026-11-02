"""Explicit live Google smoke; sends only the text provided on the CLI."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engines.google_translate import GoogleTranslateClient


def run_smoke(text, source_lang, target_lang, *, adapter_factory=GoogleTranslateClient):
    adapter = adapter_factory()
    try:
        return adapter.translate(text,source_lang,target_lang)
    finally:
        adapter.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='English')
    parser.add_argument('--target',default='Vietnamese')
    parser.add_argument('--text',default='Hello world')
    args=parser.parse_args()
    started=time.monotonic()
    result=run_smoke(args.text,args.source,args.target)
    print(json.dumps(dict(provider='Google Translate',source=args.source,target=args.target,
        translated_text=result.text,error_code=result.error.code if result.error else None,
        duration_s=round(time.monotonic()-started,3))))
    return 0 if result.text and result.error is None else 1


if __name__=='__main__':
    raise SystemExit(main())
