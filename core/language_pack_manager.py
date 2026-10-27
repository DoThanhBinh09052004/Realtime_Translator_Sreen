"""App-owned asynchronous package operations; widgets only consume snapshots."""
from dataclasses import replace
from threading import Event
from uuid import uuid4

import httpx
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from core.language_pack_contracts import PackSnapshot, PackState, PackOperationError, pack_error
from core.languages import source_languages, language_by_id
from core.language_pack_transfer import install_pack


def _client():
    return httpx.Client(transport=httpx.HTTPTransport(retries=0),follow_redirects=False,
                        timeout=httpx.Timeout(15,connect=5))


class _PackWorker(QThread):
    progress=pyqtSignal(object)
    result=pyqtSignal(object)

    def __init__(self,store,kind,language_id,operation_id,cancelled,client_factory,parent):
        super().__init__(parent)
        self.store=store; self.kind=kind; self.language_id=language_id; self.operation_id=operation_id
        self.cancelled=cancelled; self.client_factory=client_factory

    def run(self):
        error=None; rows=None
        try:
            if self.kind=='refresh': self.store.recover()
            elif self.kind=='install':
                install_pack(self.store,self.language_id,operation_id=self.operation_id,client_factory=self.client_factory,
                             cancelled=self.cancelled.is_set,progress=self.progress.emit)
            elif self.kind=='remove':
                if self.cancelled.is_set(): raise pack_error('cancelled')
                self.store.remove(self.language_id)
        except PackOperationError as exc: error=exc.error
        except OSError as exc:
            from core.language_pack_store import filesystem_error
            error=filesystem_error(exc).error
        except Exception:
            # Keep a damaged package store from killing the app. No raw paths,
            # network response bodies or traceback text cross into the UI.
            error=pack_error('integrity').error
        try: rows=self.store.scan()
        except PackOperationError as exc:
            if error is None: error=exc.error
        except Exception:
            if error is None: error=pack_error('integrity').error
        self.result.emit((self.operation_id,rows,error))


class LanguagePackManager(QObject):
    snapshot_changed=pyqtSignal(object)
    shutdown_finished=pyqtSignal()

    def __init__(self,store,*,client_factory=None,parent=None):
        super().__init__(parent)
        self.store=store
        self._client_factory=client_factory or _client
        self._rows=tuple(PackState(language.id,'not_installed','none',None,False,False,0,0) for language in source_languages())
        self._operation_id=None; self._language_id=None; self._kind=None
        self._cancelled=None; self._selected=None; self._threads={}; self._results={}
        self._shutting_down=False; self._shutdown_emitted=False

    def snapshot(self):
        rows=tuple(replace(row,in_use=True,removable=False) if row.language_id==self._selected and row.state=='installed' else row
                   for row in self._rows)
        return PackSnapshot(rows,self._operation_id,bool(self._threads))

    def _publish(self):
        self.snapshot_changed.emit(self.snapshot())

    def _reject(self,language_id,code):
        self._rows=tuple(replace(row,error=pack_error(code).error) if row.language_id==language_id else row for row in self._rows)
        self._publish()
        return False

    def _start(self,kind,language_id=None):
        if self._threads or self._shutting_down: return self._reject(language_id,'busy')
        self._operation_id=uuid4().hex; self._language_id=language_id; self._kind=kind
        self._cancelled=Event()
        worker=_PackWorker(self.store,kind,language_id,self._operation_id,self._cancelled,self._client_factory,self)
        self._threads[self._operation_id]=worker
        worker.progress.connect(self._on_progress)
        worker.result.connect(self._on_result)
        worker.finished.connect(self._on_thread_finished)
        state={'install':'downloading','remove':'removing'}.get(kind)
        if state:
            self._rows=tuple(replace(row,state=state,error=None,downloaded_bytes=0,total_bytes=0,removable=False)
                             if row.language_id==language_id else row for row in self._rows)
        self._publish()
        worker.start()
        return True

    def refresh(self):
        return self._start('refresh')

    def request_install(self,language_id):
        if self._threads or self._shutting_down: return self._reject(language_id,'busy')
        try: language=language_by_id(language_id)
        except ValueError: return self._reject(language_id,'missing')
        if language.bundled: return self._reject(language_id,'protected')
        if not language.source_enabled: return self._reject(language_id,'missing')
        return self._start('install',language_id)

    def request_remove(self,language_id):
        if self._threads or self._shutting_down: return self._reject(language_id,'busy')
        try: language=language_by_id(language_id)
        except ValueError: return self._reject(language_id,'missing')
        if language.bundled: return self._reject(language_id,'protected')
        if language_id==self._selected: return self._reject(language_id,'in_use')
        row=next((row for row in self._rows if row.language_id==language_id),None)
        if row is None or row.origin!='downloaded': return self._reject(language_id,'missing')
        return self._start('remove',language_id)

    def set_selected_language(self,language_id):
        self._selected=language_id
        self._publish()

    def cancel(self):
        if self._cancelled is not None: self._cancelled.set()

    @pyqtSlot(object)
    def _on_progress(self,progress):
        if progress.operation_id!=self._operation_id or progress.operation_id not in self._threads: return
        self._rows=tuple(replace(row,state=progress.state,downloaded_bytes=progress.downloaded_bytes,total_bytes=progress.total_bytes,error=None)
                         if row.language_id==progress.language_id else row for row in self._rows)
        self._publish()

    @pyqtSlot(object)
    def _on_result(self,result):
        operation_id,rows,error=result
        if operation_id!=self._operation_id: return
        self._results[operation_id]=(rows,error)

    @pyqtSlot()
    def _on_thread_finished(self):
        worker=self.sender()
        operation_id=worker.operation_id
        self._threads.pop(operation_id,None)
        result=self._results.pop(operation_id,None)
        if operation_id==self._operation_id:
            if result is not None:
                rows,error=result
                if rows is not None: self._rows=rows
                if error is not None:
                    self._rows=tuple(replace(row,error=error,state=row.state if row.state=='installed' else 'error')
                                     if row.language_id==self._language_id or self._language_id is None else row for row in self._rows)
            self._operation_id=None; self._language_id=None; self._kind=None; self._cancelled=None
        worker.deleteLater()
        self._publish()
        self._finish_shutdown()

    def shutdown(self):
        self._shutting_down=True
        self.cancel()
        self._finish_shutdown()

    def _finish_shutdown(self):
        if self._shutting_down and not self._threads and not self._shutdown_emitted:
            self._shutdown_emitted=True
            self.shutdown_finished.emit()
