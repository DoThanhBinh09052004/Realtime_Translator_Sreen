from dataclasses import replace
import hashlib
import io
import tarfile
import threading
import httpx
import pytest
from language_pack_helpers import make_pack_store, archive_for, make_component_archive


def run_transfer(store, *, handler=None, cancelled=lambda:False, progress=lambda p:None, operation_id='fixture'):
    from core.language_pack_transfer import install_pack
    requests=[]; clients=[]; threads=[]
    def default(request):
        requests.append(request)
        return httpx.Response(200,content=archive_for(store,request.url.path.split('/')[-1].removesuffix('.tar')))
    def factory():
        threads.append(threading.get_ident())
        client=httpx.Client(transport=httpx.MockTransport(handler or default)); clients.append(client); return client
    try: install_pack(store,'ko',operation_id=operation_id,client_factory=factory,cancelled=cancelled,progress=progress)
    finally:
        assert all(client.is_closed for client in clients)
    return requests,threads


def test_transfer_only_downloads_missing_component_and_publishes_marker_last(tmp_path):
    store=make_pack_store(tmp_path); events=[]
    def progress(event):
        events.append(event)
        assert not (store.user_root/'packs/ko/installed.json').exists()
    requests,threads=run_transfer(store,progress=progress)
    assert [request.url.path for request in requests]==['/rec-ko.tar']
    assert threads==[threading.get_ident()]
    assert events[-1].state=='installing'
    assert events[-1].downloaded_bytes==len(archive_for(store,'rec-ko'))
    assert next(row for row in store.scan() if row.language_id=='ko').state=='installed'


@pytest.mark.parametrize('failure', ['offline','404','redirect','truncated','oversized','length','digest'])
def test_network_or_integrity_failure_never_installs(tmp_path,failure):
    from core.language_pack_contracts import PackOperationError
    store=make_pack_store(tmp_path); data=archive_for(store,'rec-ko')
    def handler(request):
        if failure=='offline': raise httpx.ConnectError('fixture',request=request)
        if failure=='404': return httpx.Response(404)
        if failure=='redirect': return httpx.Response(302,headers={'Location':'https://evil.invalid/'})
        if failure=='truncated': return httpx.Response(200,content=data[:-1])
        if failure=='oversized': return httpx.Response(200,content=data+b'extra')
        if failure=='length': return httpx.Response(200,content=data,headers={'Content-Length':'1'})
        return httpx.Response(200,content=b'x'*len(data))
    with pytest.raises(PackOperationError): run_transfer(store,handler=handler)
    assert not (store.user_root/'packs/ko/installed.json').exists()
    assert not list((store.user_root/'.staging').glob('*'))


def test_cancel_before_marker_and_retry_reuses_validated_component(tmp_path):
    from core.language_pack_contracts import PackOperationError
    store=make_pack_store(tmp_path); cancel=False
    def progress(event):
        nonlocal cancel
        if event.state=='installing': cancel=True
    with pytest.raises(PackOperationError) as caught: run_transfer(store,cancelled=lambda:cancel,progress=progress)
    assert caught.value.error.code=='cancelled'
    assert not (store.user_root/'packs/ko/installed.json').exists()
    assert (store.user_root/'components/rec-ko/v1/inference.pdmodel').exists()
    requests,_=run_transfer(store)
    assert requests==[]
    assert store.resolve('ko').rec.exists()


@pytest.mark.parametrize('malice',['traversal','absolute','symlink','hardlink','duplicate','extra','oversize'])
def test_extraction_rejects_non_allowlisted_or_unsafe_members(tmp_path,malice):
    from core.language_pack_transfer import extract_component
    from core.language_pack_contracts import PackOperationError
    store=make_pack_store(tmp_path); artifact=store.catalog.components['rec-ko']; members=[]
    for file in artifact.files:
        content=('rec-ko '+file.path).encode(); member=tarfile.TarInfo('rec-ko/'+file.path); member.size=len(content)
        members.append((member,content))
    name={'traversal':'../outside','absolute':'/outside','extra':'rec-ko/other','duplicate':'rec-ko/inference.pdmodel'}.get(malice,'rec-ko/link')
    bad=tarfile.TarInfo(name); content=b'x'; bad.size=1
    if malice=='symlink': bad.type=tarfile.SYMTYPE; bad.linkname='../outside'; bad.size=0; content=b''
    if malice=='hardlink': bad.type=tarfile.LNKTYPE; bad.linkname='../outside'; bad.size=0; content=b''
    if malice=='oversize': members[0][0].size+=1
    else: members.append((bad,content))
    if malice=='oversize':
        member,content=members[0]; members[0]=(member,content+b'x')
    archive=tmp_path/'bad.tar'; archive.write_bytes(make_component_archive(members=members))
    with pytest.raises(PackOperationError) as caught: extract_component(archive,artifact,tmp_path/'out',cancelled=lambda:False)
    assert caught.value.error.code=='integrity'
    assert not (tmp_path/'outside').exists()


def test_disk_space_and_permission_errors_are_actionable(tmp_path,monkeypatch):
    import core.language_pack_transfer as transfer
    from core.language_pack_contracts import PackOperationError
    store=make_pack_store(tmp_path)
    monkeypatch.setattr(transfer.shutil,'disk_usage',lambda p:type('Usage',(),{'free':1})())
    with pytest.raises(PackOperationError) as caught: run_transfer(store)
    assert caught.value.error.code=='disk_space'
