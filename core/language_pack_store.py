"""Transactional, read-only-bundle OCR component store.

Mutation and lease creation share a cross-process QLockFile. Downloads never
hold that lock. Only a final validated marker makes a downloaded pack usable.
"""
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from uuid import uuid4

from PyQt5.QtCore import QLockFile

from core.language_pack_catalog import ARCHIVE_METADATA_FILES
from core.language_pack_contracts import InstallPlan, PackState, RemovalResult, PackOperationError, pack_error
from core.languages import language_by_id, source_languages
from core.ocr_models import OcrModelPaths

BUNDLED_COMPONENT_PATHS = {'det-en':'det/en', 'det-ml':'det/ml', 'rec-en':'rec/en', 'rec-ja':'rec/japan', 'cls':'cls'}


def filesystem_error(exc):
    if isinstance(exc, PermissionError): return pack_error('permission')
    if getattr(exc,'errno',None) in (errno.ENOSPC, errno.EDQUOT): return pack_error('disk_space')
    return pack_error('integrity')


def _is_link(path):
    try:
        info=path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&0x400)


def _delete_tree(path):
    # The caller has checked containment and every descendant for reparse points.
    shutil.rmtree(path)


class PackStore:
    def __init__(self, *, user_root: Path, bundled_root: Path, catalog):
        self.user_root=Path(os.path.abspath(user_root))
        self.bundled_root=Path(os.path.abspath(bundled_root))
        self.catalog=catalog
        self._validation_cache={}

    def _user_path(self, *parts):
        path=self.user_root.joinpath(*parts)
        if not path.is_relative_to(self.user_root): raise pack_error('integrity')
        current=self.user_root
        if _is_link(current): raise pack_error('integrity')
        for part in path.relative_to(self.user_root).parts:
            if part in ('..','.') or ':' in part: raise pack_error('integrity')
            current=current/part
            if _is_link(current): raise pack_error('integrity')
        if not path.resolve().is_relative_to(self.user_root.resolve()): raise pack_error('integrity')
        return path

    @contextmanager
    def _mutation(self):
        try:
            self._user_path().mkdir(parents=True,exist_ok=True)
            lock=QLockFile(str(self._user_path('.mutation.lock')))
            lock.setStaleLockTime(0)
            if not lock.tryLock(0): raise pack_error('busy')
            try: yield
            finally: lock.unlock()
        except OSError as exc:
            raise filesystem_error(exc) from exc

    def _language(self, language_id):
        try: language=language_by_id(language_id)
        except ValueError as exc: raise pack_error('missing') from exc
        if not language.source_enabled: raise pack_error('missing')
        return language

    def _file_valid(self, path, file):
        try:
            if _is_link(path) or not path.is_file(): return False
            info=path.stat()
            if info.st_size!=file.size_bytes: return False
            key=(str(path),file.sha256,info.st_size,info.st_mtime_ns,info.st_ctime_ns,getattr(info,'st_ino',0))
            if key in self._validation_cache: return True
            digest=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(65536),b''): digest.update(chunk)
            if digest.hexdigest()!=file.sha256: return False
            # Do not cache a file changed while hashing.
            after=path.stat()
            if (after.st_mtime_ns,after.st_ctime_ns,after.st_size)!=(info.st_mtime_ns,info.st_ctime_ns,info.st_size): return False
            self._validation_cache[key]=True
            return True
        except OSError: return False

    def _bundle_metadata_valid(self):
        try:
            manifest=json.loads((self.bundled_root/'manifest.json').read_text(encoding='utf-8'))
            return (manifest.get('schema')==1 and manifest.get('paddleocr_version')==self.catalog.paddleocr_version
                    and manifest.get('ocr_version')==self.catalog.ocr_version and manifest.get('languages')==['en','japan'])
        except (OSError,ValueError,AttributeError): return False

    def _component_valid(self, root, artifact, *, bundled=False):
        if _is_link(root) or not root.is_dir(): return False
        files=tuple(f for f in artifact.files if not bundled or f.path not in ARCHIVE_METADATA_FILES)
        return all(self._file_valid(root/file.path,file) for file in files)

    def _component_path(self, component_id):
        artifact=self.catalog.components[component_id]
        if component_id in BUNDLED_COMPONENT_PATHS and self._bundle_metadata_valid():
            root=self.bundled_root/BUNDLED_COMPONENT_PATHS[component_id]
            if self._component_valid(root,artifact,bundled=True): return root
        root=self._user_path('components',artifact.id,artifact.revision)
        if self._component_valid(root,artifact): return root
        return None

    def _resource_paths(self, language):
        paths=[]
        for id in (language.dictionary_resource,'notice'):
            resource=self.catalog.resources[id]; root=self.bundled_root
            target=root/resource.path
            if any(_is_link(root.joinpath(*target.relative_to(root).parts[:i])) for i in range(len(target.relative_to(root).parts)+1)):
                raise pack_error('missing')
            if not self._file_valid(target,resource): raise pack_error('missing')
            paths.append(target)
        return paths

    def _revision(self, language):
        identity={'schema':self.catalog.schema,'paddleocr_version':self.catalog.paddleocr_version,'ocr_version':self.catalog.ocr_version,
                  'components':[(id,self.catalog.components[id].revision,
                                 [(f.path,f.sha256,f.size_bytes) for f in self.catalog.components[id].files]) for id in language.component_ids],
                  'resources':[(id,self.catalog.resources[id].sha256) for id in (language.dictionary_resource,'notice')]}
        return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()

    def _marker_path(self, language):
        return self._user_path('packs',language.id,'installed.json')

    def _marker_valid(self, language):
        path=self._marker_path(language)
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            return (data.get('schema')==1 and data.get('language_id')==language.id
                    and data.get('revision')==self._revision(language)
                    and data.get('components')==list(language.component_ids)
                    and data.get('paddleocr_version')==self.catalog.paddleocr_version
                    and data.get('ocr_version')==self.catalog.ocr_version)
        except (OSError,ValueError,AttributeError): return False

    def _resolve(self, language):
        if language.bundled:
            if not self._bundle_metadata_valid(): raise pack_error('missing')
        elif not self._marker_valid(language): raise pack_error('missing')
        paths=[self._component_path(id) for id in language.component_ids]
        if any(path is None for path in paths): raise pack_error('missing')
        resources=self._resource_paths(language)
        return OcrModelPaths(paths[0],paths[1],paths[2],resources[0])

    def resolve(self, language_id):
        language=self._language(language_id)
        with self._mutation(): return self._resolve(language)

    def identity(self, language_id):
        language=self._language(language_id)
        with self._mutation():
            self._resolve(language)
            return language.id,self._revision(language)

    def _live_leases(self, language_id):
        directory=self._user_path('.leases')
        if not directory.exists(): return False
        live=False
        for path in directory.glob(language_id+'.*.lock'):
            self._user_path('.leases',path.name)
            probe=QLockFile(str(path)); probe.setStaleLockTime(0)
            if probe.tryLock(0): probe.unlock()
            else: live=True
        return live

    @contextmanager
    def lease(self, language_id):
        language=self._language(language_id)
        with self._mutation():
            paths=self._resolve(language)
            directory=self._user_path('.leases'); directory.mkdir(exist_ok=True)
            lock=QLockFile(str(self._user_path('.leases',language.id+'.'+uuid4().hex+'.lock')))
            lock.setStaleLockTime(0)
            if not lock.tryLock(0): raise pack_error('busy')
        try: yield paths
        finally: lock.unlock()

    def _referenced(self, excluding=None):
        referenced=set()
        for language in source_languages():
            if language.id==excluding or language.bundled: continue
            # Conservatively retain components for any current marker, even if
            # another component became corrupt outside the app.
            if self._marker_valid(language): referenced.update(language.component_ids)
        return referenced

    def scan(self):
        with self._mutation():
            rows=[]
            for language in source_languages():
                marker=self._marker_path(language)
                try:
                    paths=self._resolve(language)
                    installed=sum(sum(f.size_bytes for f in self.catalog.components[id].files) for id in language.component_ids)
                    reclaimable=0
                    shared=self._referenced(excluding=language.id)
                    for id,path in zip(language.component_ids,(paths.det,paths.rec,paths.cls)):
                        if id not in shared and path.is_relative_to(self.user_root):
                            reclaimable+=sum(f.size_bytes for f in self.catalog.components[id].files)
                    rows.append(PackState(language.id,'installed','bundled' if language.bundled else 'downloaded',self._revision(language),
                        not language.bundled,self._live_leases(language.id),installed,reclaimable))
                except PackOperationError as exc:
                    damaged=marker.exists() and not language.bundled
                    rows.append(PackState(language.id,'error' if damaged else 'not_installed',
                        'downloaded' if damaged else 'none',None,damaged,False,0,0,error=exc.error if damaged else None))
            return tuple(rows)

    def plan_install(self, language_id):
        language=self._language(language_id)
        with self._mutation():
            self._resource_paths(language)
            components=tuple(self.catalog.components[id] for id in language.component_ids if self._component_path(id) is None)
            network=sum(a.archive_size_bytes for a in components)
            expanded=sum(f.size_bytes for a in components for f in a.files)
            resources=tuple(self.catalog.resources[id] for id in (language.dictionary_resource,'notice'))
            return InstallPlan(language.id,components,resources,network,network+expanded+16*1024*1024)

    def publish_component(self, artifact, staging):
        if self.catalog.components.get(artifact.id)!=artifact: raise pack_error('invalid_catalog')
        staging=self._user_path(*Path(staging).absolute().relative_to(self.user_root).parts)
        if not staging.is_relative_to(self.user_root/'.staging'): raise pack_error('integrity')
        with self._mutation():
            if not self._component_valid(staging,artifact): raise pack_error('integrity')
            destination=self._user_path('components',artifact.id,artifact.revision)
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():
                if self._component_valid(destination,artifact): return
                if any(self._live_leases(language.id) for language in source_languages() if artifact.id in language.component_ids):
                    raise pack_error('in_use')
                self._trash(destination)
            os.replace(staging,destination)
            self._validation_cache.clear()

    def commit_pack(self, plan):
        language=self._language(plan.language_id)
        if language.bundled: raise pack_error('protected')
        with self._mutation():
            if any(self._component_path(id) is None for id in language.component_ids): raise pack_error('integrity')
            self._resource_paths(language)
            marker=self._marker_path(language); marker.parent.mkdir(parents=True,exist_ok=True)
            temporary=self._user_path('packs',language.id,uuid4().hex+'.tmp')
            try:
                with temporary.open('x',encoding='utf-8') as stream:
                    json.dump(dict(schema=1,language_id=language.id,revision=self._revision(language),components=list(language.component_ids),
                                   paddleocr_version=self.catalog.paddleocr_version,ocr_version=self.catalog.ocr_version),stream)
                    stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary,marker)
            finally:
                temporary.unlink(missing_ok=True)

    def _tree_bytes(self, path):
        total=0
        for root,dirs,files in os.walk(path,followlinks=False):
            for name in dirs+files:
                child=Path(root)/name
                self._user_path(*child.relative_to(self.user_root).parts)
            for name in files: total+=(Path(root)/name).stat().st_size
        return total

    def _trash(self, path):
        self._user_path(*path.relative_to(self.user_root).parts)
        self._tree_bytes(path)
        trash=self._user_path('.trash'); trash.mkdir(exist_ok=True)
        destination=self._user_path('.trash',uuid4().hex)
        os.replace(path,destination)
        return destination

    def _cleanup(self, path):
        self._user_path(*path.relative_to(self.user_root).parts)
        before=self._tree_bytes(path)
        try:
            _delete_tree(path)
            return before,False
        except OSError:
            remaining=self._tree_bytes(path) if path.exists() else 0
            return max(0,before-remaining),path.exists()

    def remove(self, language_id):
        language=self._language(language_id)
        if language.bundled: raise pack_error('protected')
        with self._mutation():
            if self._live_leases(language.id): raise pack_error('in_use')
            marker=self._marker_path(language)
            if not marker.exists(): raise pack_error('missing')
            pending=False; freed=0
            # Retire marker first: partial cleanup cannot advertise installed.
            retired=self._trash(marker.parent)
            retained=self._referenced(excluding=language.id)
            targets=[retired]
            for id in language.component_ids:
                artifact=self.catalog.components[id]
                component=self._user_path('components',id,artifact.revision)
                if id not in retained and component.exists():
                    try: targets.append(self._trash(component))
                    except OSError: pending=True
            self._validation_cache.clear()
        # Long filesystem deletion does not hold the mutation lock. All targets
        # have unique names in trash and cannot become active components again.
        for target in targets:
            size,waiting=self._cleanup(target); freed+=size; pending|=waiting
        return RemovalResult(freed,pending)

    def recover(self):
        # A live transfer owns its staging operation lock. Dead-process locks
        # are recovered by QLockFile rather than by unreliable age thresholds.
        with self._mutation():
            targets=[]
            staging=self._user_path('.staging')
            if staging.exists():
                for entry in staging.iterdir():
                    self._user_path('.staging',entry.name)
                    if not entry.is_dir(): continue
                    lock=QLockFile(str(entry/'.operation.lock')); lock.setStaleLockTime(0)
                    if lock.tryLock(0):
                        lock.unlock(); targets.append(self._trash(entry))
            trash=self._user_path('.trash')
            if trash.exists(): targets+=list(trash.iterdir())
        for target in dict.fromkeys(targets):
            if target.exists(): self._cleanup(target)
