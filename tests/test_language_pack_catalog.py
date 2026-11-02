import copy
import pytest


def catalog_raw():
    component = dict(revision='v1', url='https://paddleocr.bj.bcebos.com/fixture.tar',
                     archive_size_bytes=10240, archive_sha256='a'*64, archive_root='fixture',
                     files=[dict(path=n, size_bytes=3, sha256='b'*64) for n in
                            ('inference.pdmodel', 'inference.pdiparams')])
    return dict(schema=1, paddleocr_version='2.10.0', ocr_version='PP-OCRv4',
                components={k: dict(id=k, **copy.deepcopy(component)) for k in
                            ('det-en','det-ml','det-ch','rec-en','rec-ja','rec-ch','rec-ko','cls')},
                resources={k: dict(path=('NOTICE.paddleocr.txt' if k=='notice' else k.replace('-', '/')+'.txt'),
                                   size_bytes=3, sha256='c'*64) for k in
                           ('dict-en','dict-ja','dict-ch','dict-ko','notice')})


def test_catalog_is_pure_and_has_bounded_locked_artifacts(monkeypatch):
    from core.language_pack_catalog import validate_pack_catalog
    import socket
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('network forbidden'))
    catalog=validate_pack_catalog(catalog_raw())
    assert catalog.components['rec-ko'].archive_size_bytes == 10240
    assert catalog.resources['dict-ch'].size_bytes == 3


@pytest.mark.parametrize('damage', ['version','missing_component','missing_dict','duplicate_id','http','digest','traversal','root','negative','unbounded'])
def test_catalog_rejects_untrusted_metadata(damage):
    from core.language_pack_catalog import validate_pack_catalog
    from core.language_pack_contracts import PackOperationError
    raw=catalog_raw(); c=raw['components']['rec-ko']
    if damage=='version': raw['paddleocr_version']='3.0'
    elif damage=='missing_component': del raw['components']['det-ch']
    elif damage=='missing_dict': del raw['resources']['dict-ko']
    elif damage=='duplicate_id': c['id']='cls'
    elif damage=='http': c['url']='http://paddleocr.bj.bcebos.com/a.tar'
    elif damage=='digest': c['archive_sha256']='fake'
    elif damage=='traversal': c['files'][0]['path']='../inference.pdmodel'
    elif damage=='root': c['archive_root']='../../outside'
    elif damage=='negative': c['archive_size_bytes']=-1
    else: c['archive_size_bytes']=2**50
    with pytest.raises(PackOperationError) as caught: validate_pack_catalog(raw)
    assert caught.value.error.code=='invalid_catalog'


def test_authoring_hashes_fixture_content_without_importing_paddle(tmp_path):
    import ast
    import hashlib
    import io
    import tarfile
    import httpx
    from tools.pin_language_pack_catalog import pin_catalog
    from types import SimpleNamespace
    package=tmp_path/'package'; package.mkdir()
    model={'det':{}, 'rec':{}, 'cls':{}}
    for kind, codes in [('det',['en','ml','ch']), ('rec',['en','japan','ch','korean']), ('cls',['ch'])]:
        for code in codes:
            model[kind][code]={'url':f'https://paddleocr.bj.bcebos.com/{kind}_{code}.tar'}
            if kind=='rec':
                name=f'{code}.txt'; (package/name).write_bytes(code.encode())
                model[kind][code]['dict_path']='./'+name
    (package/'paddleocr.py').write_text('MODEL_URLS = '+repr({'OCR':{'PP-OCRv4':model}}))
    (package/'LICENSE').write_bytes(b'fixture license')
    data=io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as tar:
        for name, content in [('inference.pdmodel', b'model'), ('inference.pdiparams',b'params')]:
            member=tarfile.TarInfo('fixture/'+name); member.size=len(content)
            tar.addfile(member,io.BytesIO(content))
    archive=data.getvalue()
    dist=SimpleNamespace(version='2.10.0',locate_file=lambda path:package/str(path), files=[])
    # Explicit package location allows authoring against synthetic distributions.
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=archive))) as client:
        raw=pin_catalog(tmp_path/'archives', distribution=dist, package_root=package, client=client)
    assert raw['components']['rec-ko']['archive_sha256']==hashlib.sha256(archive).hexdigest()
    assert raw['components']['rec-ko']['archive_size_bytes']==len(archive)
    assert raw['components']['rec-ko']['files'][0]['sha256'] in {hashlib.sha256(b'model').hexdigest(),hashlib.sha256(b'params').hexdigest()}
    assert raw['resources']['dict-ko']['sha256']==hashlib.sha256(b'korean').hexdigest()
