"""GUI-owned, region-isolated dialogue sessions on one source canvas.

Only presentation is combined. The translation worker sees ordinary four-part
request keys, with monotonic block IDs allocated here and reversed on delivery.
"""
from collections import Counter
from dataclasses import replace
from math import isfinite

from core.blocks.grouping import group_spans
from core.blocks.models import CaptureGeometry, OverlayFrame
from core.blocks.session import BlockSession
from core.capture.geometry import resolve_region_crops, to_source_rect
from core.capture.models import CaptureContext, CaptureObservation, CaptureProfile, RegionOcrObservation
from core.capture.profile import serialize_capture_profile
from core.contracts import OcrResult, SubtitleFrame
from core.dialogue.policy import DEFAULT_DIALOGUE_POLICY
from core.dialogue.subtitle_session import SubtitleDialogueSession


class RegionDialogueSession:
    def __init__(self, profile: CaptureProfile, *, policy=DEFAULT_DIALOGUE_POLICY):
        serialize_capture_profile(profile)
        self.profile, self.policy = profile, policy
        self._regions = tuple(r for r in profile.regions if r.enabled)
        self._revision = None
        self._next_id = 0
        self._context = None

    def reset(self, revision, settings):
        self._revision, self._settings = revision, settings
        self._context = None
        self._now = 0.
        self._clear()

    def _clear(self):
        # Deliberately keep _next_id even for a same-revision geometry reset.
        self._sessions = {}
        quota, extra = divmod(32, len(self._regions))
        for index, region in enumerate(self._regions):
            if self._settings.overlay_mode == 'blocks':
                child = BlockSession(policy=self.policy, max_tracks=quota+(index < extra))
            else:
                child = SubtitleDialogueSession(policy=self.policy)
                child.reset(self._revision, self._settings)
            self._sessions[region.id] = child
        self._routes, self._reverse = {}, {}
        self._scan_id = -1
        self._completed = dict.fromkeys(self._sessions, float('-inf'))
        self._errors = []

    @staticmethod
    def _valid_context(context):
        if not isinstance(context, CaptureContext) or not isinstance(context.geometry, CaptureGeometry):
            return False
        try:
            return (type(context.binding_epoch) is int and context.binding_epoch >= 0
                    and type(context.geometry_sequence) is int and context.geometry_sequence >= 0
                    and len(context.geometry.image_size_px) == 2
                    and all(type(v) is int and v > 0 for v in context.geometry.image_size_px))
        except (AttributeError, TypeError):
            return False

    def set_geometry(self, context: CaptureContext):
        if not self._valid_context(context) or context.source_kind != self.profile.source_kind:
            return False
        old = self._context
        if old is not None:
            if context.binding_epoch < old.binding_epoch:
                return False
            if context.binding_epoch == old.binding_epoch:
                if context.geometry_sequence < old.geometry_sequence:
                    return False
                if context.geometry_sequence == old.geometry_sequence and context != old:
                    return False
            hard = not self._same_source_raster(context, old)
            if hard:
                scan_id = self._scan_id
                self._clear()
                self._scan_id = scan_id
        self._context = context
        return True

    @staticmethod
    def _same_source_raster(first, second):
        return (first.binding_epoch == second.binding_epoch
                and first.source_kind == second.source_kind and first.window == second.window
                and first.geometry.image_size_px == second.geometry.image_size_px
                and (first.geometry.region_px.width, first.geometry.region_px.height)
                    == (second.geometry.region_px.width, second.geometry.region_px.height))

    def observe(self, batch: CaptureObservation):
        if (not isinstance(batch, CaptureObservation) or batch.revision != self._revision
                or batch.settings != self._settings or type(batch.scan_id) is not int
                or batch.scan_id <= self._scan_id):
            return
        items = tuple(item for item in batch.regions if isinstance(item, RegionOcrObservation)
                      and isinstance(item.region_id, str) and isinstance(item.ocr, OcrResult))
        counts = Counter(item.region_id for item in items)
        valid_items = []
        for item in items:
            region_id = item.region_id
            if region_id not in self._sessions or counts[region_id] != 1:
                continue
            try:
                valid = (isfinite(item.captured_at_s) and isfinite(item.completed_at_s)
                         and item.captured_at_s <= item.completed_at_s
                         and item.completed_at_s >= self._completed[region_id])
            except (TypeError, ValueError):
                valid = False
            if not valid:
                continue
            valid_items.append(item)
        if not valid_items or not self._valid_context(batch.context):
            return
        current = self._context
        if (current is not None and batch.context.binding_epoch == current.binding_epoch
                and batch.context.geometry_sequence < current.geometry_sequence):
            # OCR coordinates are local to the unchanged source raster. A GUI
            # origin update can overtake slow OCR; consume its data without
            # replacing the newer canvas mapping with the batch's snapshot.
            if not self._same_source_raster(batch.context, current):
                return
        elif not self.set_geometry(batch.context):
            return
        self._scan_id = batch.scan_id
        crops = resolve_region_crops(self.profile, self._context.geometry.image_size_px)
        for item in valid_items:
            region_id = item.region_id
            self._completed[region_id] = item.completed_at_s
            self._now = max(self._now, item.completed_at_s)
            if item.ocr.error is not None:
                self._errors = (self._errors+[item.ocr.error])[-32:]
                continue
            child = self._sessions[region_id]
            if self._settings.overlay_mode == 'blocks':
                crop = crops[region_id]
                blocks = tuple(replace(b, source_rect=to_source_rect(b.source_rect, crop))
                               for b in group_spans(item.ocr.spans, (crop.width, crop.height)))
                child.observe(blocks, settings=self._settings, revision=self._revision,
                              frame_id=batch.scan_id, geometry=self._context.geometry,
                              now_s=item.completed_at_s)
            else:
                child.observe(item.ocr.text, now_s=item.completed_at_s)
        self._sync_routes()

    def _sync_routes(self):
        active = {(region_id, local_id) for region_id, child in self._sessions.items()
                  for _, local_id, _ in child.active_turns}
        for key in self._routes.keys()-active:
            self._reverse.pop(self._routes.pop(key), None)
        for key in sorted(active-self._routes.keys()):
            self._routes[key] = self._next_id
            self._reverse[self._next_id] = key
            self._next_id += 1

    @property
    def active_turns(self):
        self._sync_routes()
        return frozenset((revision, self._routes[region_id, local_id], turn)
                         for region_id, child in self._sessions.items()
                         for revision, local_id, turn in child.active_turns)

    @property
    def needs_scan_regions(self):
        return frozenset(region_id for region_id, child in self._sessions.items() if child.needs_scan)

    def translation_jobs(self, *, now_s):
        self._sync_routes()
        return tuple(replace(job, block_id=self._routes[region_id, job.block_id])
                     for region_id, child in self._sessions.items()
                     for job in child.translation_jobs(now_s=now_s))

    def _local(self, item):
        self._sync_routes()
        if item.revision != self._revision:
            return None
        route = self._reverse.get(item.block_id)
        if route is None:
            return None
        region_id, local_id = route
        return self._sessions[region_id], replace(item, block_id=local_id)

    def mark_dispatched(self, job, *, now_s):
        local = self._local(job)
        if local is not None and job.settings == self._settings:
            child, local_job = local
            child.mark_dispatched(local_job, now_s=now_s)

    def apply_result(self, result, *, now_s):
        self._now = max(self._now, now_s)
        local = self._local(result)
        if local is None:
            return False
        child, local_result = local
        return child.apply_result(local_result, now_s=now_s)

    def tick(self, *, now_s):
        self._now = max(self._now, now_s)
        for child in self._sessions.values():
            child.tick(now_s=now_s)
        self._sync_routes()

    def current_frame(self):
        if self._revision is None:
            return None
        if self._settings.overlay_mode == 'blocks':
            if self._context is None:
                return None
            self._sync_routes()
            blocks = tuple(replace(block, block_id=self._routes[region_id, block.block_id])
                           for region_id, child in self._sessions.items()
                           if (frame := child.current_frame()) is not None for block in frame.blocks
                           if (region_id, block.block_id) in self._routes)
            return OverlayFrame(self._revision, max(0, self._scan_id), self._context.geometry, blocks)
        frames = tuple(child.current_frame() for child in self._sessions.values())
        visible = tuple(frame for frame in frames if frame is not None and frame.text)
        return SubtitleFrame(self._revision, max((f.candidate_id for f in frames), default=0),
                             '\n\n'.join(f.source_text for f in visible),
                             '\n\n'.join(f.text for f in visible))

    def drain_errors(self):
        errors, self._errors = tuple(self._errors), []
        return errors+tuple(error for child in self._sessions.values() for error in child.drain_errors())
