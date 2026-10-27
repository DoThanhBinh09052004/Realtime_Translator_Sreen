"""Bounded HTTPS streaming and manual allowlisted extraction, off the GUI thread."""
import hashlib
from pathlib import Path
import re
import shutil
import tarfile

import httpx
from PyQt5.QtCore import QLockFile

from core.language_pack_catalog import safe_relative
from core.language_pack_contracts import PackProgress, PackOperationError, pack_error
from core.language_pack_store import _is_link, filesystem_error

CHUNK_SIZE=64*1024


def _check_cancelled(cancelled):
    if cancelled(): raise pack_error('cancelled')


def verify_component(root: Path, artifact) -> None:
    try:
        for file in artifact.files:
            path=Path(root)/file.path
            if _is_link(path) or not path.is_file() or path.stat().st_size!=file.size_bytes: raise pack_error('integrity')
            digest=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(CHUNK_SIZE),b''): digest.update(chunk)
            if digest.hexdigest()!=file.sha256: raise pack_error('integrity')
    except OSError as exc: raise filesystem_error(exc) from exc


def extract_component(archive: Path, artifact, destination: Path, *, cancelled) -> None:
    try:
        destination=Path(destination)
        if _is_link(destination): raise pack_error('integrity')
        destination.mkdir(parents=True,exist_ok=False)
        allowed={artifact.archive_root+'/'+file.path:file for file in artifact.files}
        seen=set()
        # Release archives are uncompressed .tar files. Streaming mode avoids
        # allocating a model, member list or compressed expansion in memory.
        with tarfile.open(archive,'r|') as tar:
            for member in tar:
                _check_cancelled(cancelled)
                name=safe_relative(member.name.rstrip('/') if member.isdir() else member.name)
                if name in seen: raise pack_error('integrity')
                seen.add(name)
                if member.isdir() and name==artifact.archive_root: continue
                if name not in allowed or not member.isfile() or member.size!=allowed[name].size_bytes:
                    raise pack_error('integrity')
                file=allowed[name]
                # Join the catalog's validated filename, never the tar name.
                target=destination/file.path
                if _is_link(target): raise pack_error('integrity')
                digest=hashlib.sha256(); count=0
                source=tar.extractfile(member)
                if source is None: raise pack_error('integrity')
                with source, target.open('xb') as stream:
                    while True:
                        _check_cancelled(cancelled)
                        chunk=source.read(CHUNK_SIZE)
                        if not chunk: break
                        count+=len(chunk)
                        if count>file.size_bytes: raise pack_error('integrity')
                        stream.write(chunk); digest.update(chunk)
                if count!=file.size_bytes or digest.hexdigest()!=file.sha256: raise pack_error('integrity')
        if set(allowed)!=seen.intersection(allowed): raise pack_error('integrity')
        _check_cancelled(cancelled)
    except (tarfile.TarError,ValueError,KeyError) as exc: raise pack_error('integrity') from exc
    except OSError as exc: raise filesystem_error(exc) from exc


def install_pack(store, language_id, *, operation_id, client_factory, cancelled, progress) -> None:
    if not isinstance(operation_id,str) or not re.fullmatch('[a-zA-Z0-9_-]+',operation_id): raise pack_error('integrity')
    client=None; operation_lock=None; staging=None
    try:
        _check_cancelled(cancelled)
        plan=store.plan_install(language_id)
        with store._mutation():
            staging=store._user_path('.staging',operation_id)
            staging.mkdir(parents=True,exist_ok=False)
            operation_lock=QLockFile(str(store._user_path('.staging',operation_id,'.operation.lock')))
            operation_lock.setStaleLockTime(0)
            if not operation_lock.tryLock(0): raise pack_error('busy')
        if shutil.disk_usage(store.user_root).free<plan.required_disk_bytes: raise pack_error('disk_space')
        # A new client is owned and closed in the calling worker thread, even
        # for an empty retry plan. There is exactly one request per component.
        client=client_factory()
        downloaded=0
        def emit(state):
            progress(PackProgress(operation_id,language_id,state,downloaded,plan.network_bytes))
        for artifact in plan.components:
            _check_cancelled(cancelled); emit('downloading')
            archive=store._user_path('.staging',operation_id,artifact.id+'.tar')
            digest=hashlib.sha256(); count=0
            with client.stream('GET',artifact.url,follow_redirects=False,
                               timeout=httpx.Timeout(15,connect=5),headers={'Accept-Encoding':'identity'}) as response:
                if response.status_code!=200: raise pack_error('network')
                if response.headers.get('content-encoding','identity')!='identity': raise pack_error('integrity')
                length=response.headers.get('content-length')
                if length is not None:
                    try:
                        if int(length)!=artifact.archive_size_bytes: raise pack_error('integrity')
                    except ValueError as exc: raise pack_error('integrity') from exc
                with archive.open('xb') as stream:
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        _check_cancelled(cancelled)
                        count+=len(chunk)
                        if count>artifact.archive_size_bytes: raise pack_error('integrity')
                        stream.write(chunk); digest.update(chunk); downloaded+=len(chunk); emit('downloading')
            if count!=artifact.archive_size_bytes or digest.hexdigest()!=artifact.archive_sha256: raise pack_error('integrity')
            _check_cancelled(cancelled); emit('verifying')
            destination=store._user_path('.staging',operation_id,artifact.id)
            extract_component(archive,artifact,destination,cancelled=cancelled)
            _check_cancelled(cancelled)
            store.publish_component(artifact,destination)
            archive.unlink()
        _check_cancelled(cancelled); emit('installing'); _check_cancelled(cancelled)
        store.commit_pack(plan)
    except httpx.HTTPError as exc: raise pack_error('network') from exc
    except OSError as exc: raise filesystem_error(exc) from exc
    finally:
        try:
            if client is not None: client.close()
        finally:
            if operation_lock is not None: operation_lock.unlock()
            if staging is not None and staging.exists():
                # Only the exact operation directory inside the injected root.
                # A malicious reparse point is rejected rather than followed.
                try: store._cleanup(staging)
                except (OSError,PackOperationError): pass
