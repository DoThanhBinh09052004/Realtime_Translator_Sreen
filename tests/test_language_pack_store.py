from dataclasses import replace
import json
from pathlib import Path
import pytest
from language_pack_helpers import make_pack_store, stage_component, install_fixture


def test_fresh_store_only_advertises_valid_bundled_languages_and_reuses_shared_components(tmp_path):
    store=make_pack_store(tmp_path)
    assert [row.language_id for row in store.scan() if row.state=='installed']==['en','ja']
    assert [component.id for component in store.plan_install('ko').components]==['rec-ko']
    install_fixture(store,'zh-Hans')
    paths=store.resolve('zh-Hans')
    assert paths.det==store.user_root/'components/det-ch/v1'
    assert paths.rec==store.user_root/'components/rec-ch/v1'
    assert paths.cls==store.bundled_root/'cls'
    assert paths.dictionary==store.bundled_root/'pack_resources/ch_dict.txt'
    assert store.identity('zh-Hans')[0]=='zh-Hans'


def test_uncommitted_or_corrupt_models_are_not_installed(tmp_path):
    from core.language_pack_contracts import PackOperationError
    store=make_pack_store(tmp_path); stage_component(store,'rec-ko')
    assert next(row for row in store.scan() if row.language_id=='ko').state=='not_installed'
    install_fixture(store,'ko')
    (store.user_root/'components/rec-ko/v1/inference.pdmodel').write_bytes(b'bad')
    assert next(row for row in store.scan() if row.language_id=='ko').state=='error'
    with pytest.raises(PackOperationError): store.resolve('ko')


def test_removal_protects_bundle_and_cross_instance_live_lease(tmp_path):
    from core.language_pack_store import PackStore
    from core.language_pack_contracts import PackOperationError
    store=make_pack_store(tmp_path); install_fixture(store,'ko')
    before={str(p.relative_to(store.bundled_root)):p.read_bytes() for p in store.bundled_root.rglob('*') if p.is_file()}
    other=PackStore(user_root=store.user_root,bundled_root=store.bundled_root,catalog=store.catalog)
    with pytest.raises(PackOperationError) as protected: store.remove('en')
    assert protected.value.error.code=='protected'
    with store.lease('ko'):
        with pytest.raises(PackOperationError) as busy: other.remove('ko')
        assert busy.value.error.code=='in_use'
    size=sum(file.size_bytes for file in store.catalog.components['rec-ko'].files)
    removed=other.remove('ko')
    assert removed.reclaimed_bytes>=size and not removed.pending_cleanup
    assert next(row for row in store.scan() if row.language_id=='ko').state=='not_installed'
    assert before=={str(p.relative_to(store.bundled_root)):p.read_bytes() for p in store.bundled_root.rglob('*') if p.is_file()}


def test_mutation_lock_rejects_independent_store(tmp_path):
    from PyQt5.QtCore import QLockFile
    from core.language_pack_contracts import PackOperationError
    store=make_pack_store(tmp_path); store.user_root.mkdir()
    lock=QLockFile(str(store.user_root/'.mutation.lock')); lock.setStaleLockTime(0); assert lock.tryLock(0)
    try:
        with pytest.raises(PackOperationError) as busy: store.plan_install('ko')
        assert busy.value.error.code=='busy'
    finally: lock.unlock()


def test_atomic_marker_failure_preserves_other_installed_pack(tmp_path,monkeypatch):
    import core.language_pack_store as module
    store=make_pack_store(tmp_path); install_fixture(store,'ko')
    plan=store.plan_install('zh-Hans')
    for artifact in plan.components: stage_component(store,artifact.id)
    original=module.os.replace
    def reject_marker(source,destination):
        if str(destination).endswith('installed.json'): raise PermissionError('fixture')
        return original(source,destination)
    monkeypatch.setattr(module.os,'replace',reject_marker)
    with pytest.raises(Exception): store.commit_pack(plan)
    assert next(row for row in store.scan() if row.language_id=='ko').state=='installed'
    assert next(row for row in store.scan() if row.language_id=='zh-Hans').state!='installed'


def test_user_root_unicode_cwd_and_pending_cleanup(tmp_path,monkeypatch):
    import core.language_pack_store as module
    store=make_pack_store(tmp_path/'Ngôn ngữ 空白'); install_fixture(store,'ko')
    monkeypatch.chdir(tmp_path)
    assert store.resolve('en').rec.is_absolute()
    def blocked(path): raise PermissionError('Windows sharing violation')
    monkeypatch.setattr(module,'_delete_tree',blocked)
    result=store.remove('ko')
    assert result.pending_cleanup and result.reclaimed_bytes==0
    assert next(row for row in store.scan() if row.language_id=='ko').state=='not_installed'
