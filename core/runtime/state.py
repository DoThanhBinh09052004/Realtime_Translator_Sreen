"""Authoritative runtime state, protected by the worker's existing QMutex.

All state transitions and snapshot reads require ``mutex`` to be held by the
facade. No method here locks recursively or emits Qt signals. Algorithm caches
remain on the capture thread; lifecycle intent remains on the GUI thread.
"""
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping

from PyQt5.QtCore import QMutex

from core.blocks.models import CaptureGeometry
from core.capture.models import CaptureContext, CaptureProfile
from core.contracts import RuntimeSettings


@dataclass(frozen=True)
class RuntimeSnapshot:
    settings: RuntimeSettings
    revision: int
    running: bool
    session_id: int
    region: Mapping[str, int]
    overlay_rect: tuple | None
    geometry: CaptureGeometry | None
    profile: CaptureProfile | None
    context: CaptureContext | None
    source_invalid: bool
    force_regions: frozenset[str]
    needs_dialogue_scan: bool
    invalidated: bool

    def __post_init__(self):
        object.__setattr__(self, 'region', MappingProxyType(dict(self.region)))
        object.__setattr__(self, 'force_regions', frozenset(self.force_regions))
        if self.overlay_rect is not None:
            object.__setattr__(self, 'overlay_rect', tuple(self.overlay_rect))

    def __iter__(self):
        # Existing direct worker helpers/tests unpack these four values.
        yield self.settings
        yield self.revision
        yield dict(self.region)
        yield self.overlay_rect


@dataclass
class WorkerRuntimeState:
    settings: RuntimeSettings
    region: dict
    mutex: QMutex = field(default_factory=QMutex)
    revision: int = 0
    running: bool = False
    invalidated: bool = True
    overlay_rect: tuple | None = None
    geometry: CaptureGeometry | None = None
    profile: CaptureProfile | None = None
    context: CaptureContext | None = None
    source_invalid: bool = False
    force_regions: frozenset[str] = frozenset()
    needs_dialogue_scan: bool = False
    session_id: int = 0

    def __post_init__(self):
        self.region = dict(self.region)

    def snapshot(self, *, consume_invalidation=False):
        snapshot = RuntimeSnapshot(self.settings, self.revision, self.running,
            self.session_id, self.region, self.overlay_rect, self.geometry,
            self.profile, self.context, self.source_invalid, self.force_regions,
            self.needs_dialogue_scan, self.invalidated)
        if consume_invalidation:
            self.invalidated = False
        return snapshot

    def invalidate(self):
        self.revision += 1
        self.invalidated = True
        return self.revision

    def configure(self, settings):
        mode_changed = self.settings.overlay_mode != settings.overlay_mode
        self.settings = settings
        return self.invalidate(), mode_changed

    def set_interval(self, ms):
        self.settings = replace(self.settings, interval_ms=max(100, min(3000, int(ms))))
        return self.invalidate()

    def set_region(self, region):
        self.region = dict(region)
        return self.invalidate()

    def set_geometry(self, geometry):
        self.geometry = geometry
        return self.invalidate()

    def configure_capture(self, profile, context):
        self.profile, self.context = profile, context
        self.source_invalid = False
        self.geometry = context.geometry
        self.force_regions = frozenset()
        return self.invalidate()

    def update_geometry(self, context):
        old = self.context
        if old is None or (old.binding_epoch, old.source_kind, old.window,
                old.geometry.image_size_px, old.geometry.screen) != (
                context.binding_epoch, context.source_kind, context.window,
                context.geometry.image_size_px, context.geometry.screen):
            return False
        if context.geometry_sequence < old.geometry_sequence:
            return False
        self.context, self.geometry = context, context.geometry
        return True

    def reset_context(self):
        self.force_regions = (frozenset(r.id for r in self.profile.regions if r.enabled)
                              if self.profile else frozenset())
        return self.invalidate()

    def invalidate_source(self, binding_epoch):
        if self.context is None or self.context.binding_epoch != binding_epoch or self.source_invalid:
            return None
        self.source_invalid = True
        return self.reset_context()

    def start_run(self, *, preserve_session):
        if not preserve_session:
            self.session_id += 1
        self.running = True
        return self.invalidate()

    def stop_run(self):
        self.running = False
        return self.invalidate()


def runtime_field(name):
    """Legacy private facade aliases; callers keep the existing mutex discipline."""
    def get(worker):
        return getattr(worker._runtime, name)
    def set_value(worker, value):
        if name == 'overlay_rect' and value is not None:
            value = tuple(value)
        setattr(worker._runtime, name, value)
    return property(get, set_value)
