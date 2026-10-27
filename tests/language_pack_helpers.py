"""Tiny hermetic model fixtures; no Paddle import, cache or network."""
from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
import tarfile


def make_component_archive(component_id='rec-ko', files=None, *, members=None):
    files=files or {'inference.pdmodel':(component_id+' model').encode(), 'inference.pdiparams':(component_id+' params').encode()}
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as archive:
        if members is not None:
            for member,content in members: archive.addfile(member,io.BytesIO(content) if content else None)
        else:
            for name,content in files.items():
                member=tarfile.TarInfo(component_id+'/'+name); member.size=len(content)
                archive.addfile(member,io.BytesIO(content))
    return output.getvalue()


def make_pack_store(tmp_path: Path):
    from core.language_pack_catalog import validate_pack_catalog
    from core.language_pack_store import PackStore, BUNDLED_COMPONENT_PATHS
    bundled=tmp_path/'bundle'; bundled.mkdir(parents=True)
    raw=dict(schema=1,paddleocr_version='2.10.0',ocr_version='PP-OCRv4',components={},resources={})
    manifest_files={}
    for id in ('det-en','det-ml','det-ch','rec-en','rec-ja','rec-ch','rec-ko','cls'):
        files={name:(id+' '+name).encode() for name in ('inference.pdmodel','inference.pdiparams')}
        data=make_component_archive(id,files)
        raw['components'][id]=dict(id=id,revision='v1',url=f'https://paddleocr.bj.bcebos.com/{id}.tar',archive_size_bytes=len(data),
            archive_sha256=hashlib.sha256(data).hexdigest(),archive_root=id,
            files=[dict(path=name,size_bytes=len(content),sha256=hashlib.sha256(content).hexdigest()) for name,content in files.items()])
        if id in BUNDLED_COMPONENT_PATHS:
            for name,content in files.items():
                relative=BUNDLED_COMPONENT_PATHS[id]+'/'+name
                target=bundled/relative; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content)
                manifest_files[relative]=hashlib.sha256(content).hexdigest()
    for id,path in [('dict-en','dict/en_dict.txt'),('dict-ja','dict/japan_dict.txt'),('dict-ch','pack_resources/ch_dict.txt'),
                    ('dict-ko','pack_resources/korean_dict.txt'),('notice','NOTICE.paddleocr.txt')]:
        content=(id+' dictionary').encode()
        target=bundled/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content)
        raw['resources'][id]=dict(path=path,size_bytes=len(content),sha256=hashlib.sha256(content).hexdigest())
        if id in ('dict-en','dict-ja','notice'): manifest_files[path]=hashlib.sha256(content).hexdigest()
    (bundled/'manifest.json').write_text(json.dumps(dict(schema=1,paddleocr_version='2.10.0',ocr_version='PP-OCRv4',
        languages=['en','japan'],files=manifest_files,provenance={key:key for key in ('det/en','det/ml','rec/en','rec/japan','cls')})))
    return PackStore(user_root=tmp_path/'user',bundled_root=bundled,catalog=validate_pack_catalog(raw))


def stage_component(store, component_id):
    artifact=store.catalog.components[component_id]
    staging=store.user_root/'.staging'/('fixture-'+component_id); staging.mkdir(parents=True,exist_ok=True)
    for file in artifact.files: (staging/file.path).write_bytes((component_id+' '+file.path).encode())
    store.publish_component(artifact,staging)


def install_fixture(store, language_id):
    plan=store.plan_install(language_id)
    for artifact in plan.components: stage_component(store,artifact.id)
    store.commit_pack(plan)


def archive_for(store, id):
    return make_component_archive(id,{file.path:(id+' '+file.path).encode() for file in store.catalog.components[id].files})
