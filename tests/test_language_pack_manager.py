import threading
import httpx
from PyQt5.QtCore import QTimer
from language_pack_helpers import make_pack_store, archive_for, install_fixture


def make_manager(tmp_path,qtbot):
    from core.language_pack_manager import LanguagePackManager
    store=make_pack_store(tmp_path)
    manager=LanguagePackManager(store,client_factory=lambda:httpx.Client(transport=httpx.MockTransport(
        lambda request:httpx.Response(200,content=archive_for(store,request.url.path.split('/')[-1].removesuffix('.tar'))))))
    return manager,store


def finish(qtbot,manager):
    qtbot.waitUntil(lambda:not manager.snapshot().busy,timeout=5000)
    manager.shutdown()
    qtbot.waitUntil(lambda:not manager._threads,timeout=5000)


def test_refresh_and_install_are_async_and_do_not_block_gui_timer(tmp_path,qtbot):
    manager,store=make_manager(tmp_path,qtbot)
    entered=threading.Event(); release=threading.Event(); timer=[]; threads=[]
    original=store.scan
    def blocked_scan():
        threads.append(threading.get_ident()); entered.set(); assert release.wait(5)
        return original()
    store.scan=blocked_scan
    assert manager.refresh()
    qtbot.waitUntil(entered.is_set)
    QTimer.singleShot(0,lambda:timer.append(True))
    qtbot.waitUntil(lambda:bool(timer))
    assert manager.snapshot().busy
    assert not manager.request_install('ko')
    release.set()
    qtbot.waitUntil(lambda:not manager.snapshot().busy)
    assert threads[0]!=threading.get_ident()
    assert manager.request_install('ko')
    qtbot.waitUntil(lambda:not manager.snapshot().busy)
    assert next(row for row in manager.snapshot().rows if row.language_id=='ko').state=='installed'
    finish(qtbot,manager)


def test_selected_and_bundled_removal_rejected_before_dispatch(tmp_path,qtbot):
    manager,store=make_manager(tmp_path,qtbot); install_fixture(store,'ko')
    manager.refresh(); qtbot.waitUntil(lambda:not manager.snapshot().busy)
    manager.set_selected_language('ko')
    assert not manager.request_remove('ko')
    assert next(row for row in manager.snapshot().rows if row.language_id=='ko').error.code=='in_use'
    assert not manager.request_remove('en')
    assert next(row for row in manager.snapshot().rows if row.language_id=='en').error.code=='protected'
    assert not manager.snapshot().busy
    finish(qtbot,manager)


def test_removing_is_published_synchronously_and_shutdown_waits_without_blocking(tmp_path,qtbot):
    manager,store=make_manager(tmp_path,qtbot); install_fixture(store,'ko')
    manager.refresh(); qtbot.waitUntil(lambda:not manager.snapshot().busy)
    entered=threading.Event(); release=threading.Event(); finished=[]
    original=store.remove
    def blocked_remove(language):
        entered.set(); assert release.wait(5); return original(language)
    store.remove=blocked_remove
    manager.shutdown_finished.connect(lambda:finished.append(True))
    assert manager.request_remove('ko')
    assert next(row for row in manager.snapshot().rows if row.language_id=='ko').state=='removing'
    qtbot.waitUntil(entered.is_set)
    manager.shutdown()
    assert not finished and manager.snapshot().busy
    release.set(); qtbot.waitUntil(lambda:bool(finished),timeout=5000)
    assert not manager._threads


def test_cancelled_install_rescans_and_late_progress_cannot_override_snapshot(tmp_path,qtbot):
    from core.language_pack_contracts import PackProgress
    manager,store=make_manager(tmp_path,qtbot)
    entered=threading.Event(); release=threading.Event()
    def factory():
        entered.set(); assert release.wait(5)
        return httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=archive_for(store,'rec-ko'))))
    manager._client_factory=factory
    manager.refresh(); qtbot.waitUntil(lambda:not manager.snapshot().busy)
    manager.request_install('ko'); operation=manager.snapshot().operation_id
    qtbot.waitUntil(entered.is_set); manager.cancel(); release.set()
    qtbot.waitUntil(lambda:not manager.snapshot().busy)
    row=next(row for row in manager.snapshot().rows if row.language_id=='ko')
    assert row.state=='error' and row.error.code=='cancelled'
    manager._on_progress(PackProgress(operation,'ko','installed',999,999))
    assert next(row for row in manager.snapshot().rows if row.language_id=='ko').state=='error'
    finish(qtbot,manager)
