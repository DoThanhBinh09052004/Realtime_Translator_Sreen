"""Capture/OCR loops executed on the worker's existing QThread.

No Qt object or worker reference is owned here. The explicit ports keep GUI
state and generation gates in the facade; native resources stay local to a run.
"""
from dataclasses import dataclass, replace
from typing import Callable

import cv2
import numpy as np

from core.blocks.models import Rect
from core.capture.geometry import resolve_region_crops
from core.capture.models import CaptureObservation, CaptureStatus, SourceStatus
from core.contracts import EngineError, OcrResult
from core.runtime.state import RuntimeSnapshot


def mask_overlay(img, region, overlay_rect):
    """Che mờ vùng overlay phụ đề nếu nằm đè lên vùng chụp để tránh OCR chính nó"""
    if not overlay_rect:
        return img

    try:
        ox, oy, ow, oh = overlay_rect
        if not all(isinstance(value, (int, float)) and np.isfinite(value)
                   for value in (ox, oy, ow, oh)) or ow <= 0 or oh <= 0:
            return img
    except (TypeError, ValueError):
        return img
    rx, ry = region["left"], region["top"]

    x1 = max(0, int(np.floor(ox - rx - 6)))
    y1 = max(0, int(np.floor(oy - ry - 6)))
    x2 = min(img.shape[1], int(np.ceil(ox + ow - rx + 6)))
    y2 = min(img.shape[0], int(np.ceil(oy + oh - ry + 6)))

    if x1 < x2 and y1 < y2:
        img[y1:y2, x1:x2] = 0

    return img

@dataclass(frozen=True)
class RunnerPorts:
    take_snapshot: Callable[[], RuntimeSnapshot | None]
    read_revision: Callable[[], int]
    is_current: Callable[[int], bool]
    mark_stopped: Callable[[], None]
    stop_translation: Callable[[], None]
    read_ocr: Callable[..., OcrResult]
    process_dialogue_frame: Callable[..., bool]
    publish_error: Callable[[int, EngineError], None]
    publish_status: Callable[[int, CaptureStatus], None]
    publish_observation: Callable[[int, CaptureObservation], None]
    publish_terminal: Callable[[SourceStatus], None]
    publish_cleanup_error: Callable[[int, EngineError], None]


@dataclass(frozen=True)
class RunnerDependencies:
    desktop_factory: Callable
    source_factory: Callable
    scanner_factory: Callable
    clock: Callable[[], float]
    sleep: Callable[[float], None]
    sleep_ms: Callable[[int], None]
    release_ocr: Callable[[], None]
    compact_memory: Callable[[], None]


class CaptureOcrRunner:
    def __init__(self, ports: RunnerPorts, dependencies: RunnerDependencies):
        self.ports = ports
        self.dependencies = dependencies

    def _finish(self, revision):
        ports, deps = self.ports, self.dependencies
        failures = []
        for name, cleanup in (('translation_stop', ports.stop_translation),
                              ('ocr_release', deps.release_ocr),
                              ('mark_stopped', ports.mark_stopped),
                              ('memory_compaction', deps.compact_memory)):
            try:
                cleanup()
            except Exception:
                failures.append(name)
        if failures:
            try:
                ports.publish_cleanup_error(revision, EngineError('worker_cleanup',
                    'Không thể hoàn tất dọn dẹp worker: ' + ', '.join(failures) + '.', True))
            except Exception:
                # Reporting must not undo cleanup or escape QThread.run().
                pass

    def _capture_error(self, context):
        if context is not None:
            self.ports.publish_terminal(SourceStatus(context.binding_epoch, 'error',
                EngineError('capture', 'Không thể mở hoặc xử lý nguồn chụp. Chọn nguồn hoặc thử lại.', True)))

    def run_legacy(self):
        ports, deps = self.ports, self.dependencies
        revision = ports.read_revision()
        idle_counter = 0
        try:
            with deps.desktop_factory() as sct:
                while True:
                    snapshot = ports.take_snapshot()
                    if snapshot is None:
                        break
                    settings, revision = snapshot.settings, snapshot.revision
                    region, overlay_rect = snapshot.region, snapshot.overlay_rect
                    started = deps.clock()
                    img_raw = img = img_gray = None
                    idle = False
                    try:
                        if region.get("width", 0) <= 0 or region.get("height", 0) <= 0:
                            deps.sleep(0.1)
                            continue
                        monitor = {k: int(region[k]) for k in ("top", "left", "width", "height")}
                        img_raw = sct.grab(monitor)
                        img = np.array(img_raw)
                        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        if settings.overlay_mode == 'blocks':
                            geometry = snapshot.geometry
                            expected = Rect(region['left'], region['top'], region['width'], region['height'])
                            if geometry is None or geometry.region_px != expected:
                                ports.publish_error(revision,
                                                   EngineError('capture_geometry', 'Hãy chọn vùng OCR nằm trọn trên một màn hình.', False))
                                ports.mark_stopped()
                                continue
                            geometry = replace(geometry, image_size_px=(img_gray.shape[1], img_gray.shape[0]))
                            idle = ports.process_dialogue_frame(img_gray, settings, revision, geometry, captured_at_s=started, force_scan=snapshot.needs_dialogue_scan)
                        else:
                            img_gray = mask_overlay(img_gray, region, overlay_rect)
                            idle = ports.process_dialogue_frame(img_gray, settings, revision, captured_at_s=started, force_scan=snapshot.needs_dialogue_scan)
                    except Exception:
                        ports.publish_error(revision,
                                           EngineError("capture", "Không thể xử lý ảnh chụp màn hình.", True))
                    finally:
                        del img_raw, img, img_gray
                    idle_counter = idle_counter + 1 if idle else 0
                    if idle_counter == 3 or (idle_counter > 0 and idle_counter % 20 == 0):
                        deps.compact_memory()
                    elapsed_ms = (deps.clock() - started) * 1000
                    deps.sleep(max(20, settings.interval_ms - elapsed_ms) / 1000.0)
        except Exception:
            ports.publish_error(revision,
                               EngineError("capture", "Không thể mở bộ chụp màn hình.", True))
        finally:
            self._finish(revision)

    def run_capture(self):
        ports, deps = self.ports, self.dependencies
        source = None
        source_context = None
        source_key = scanner_revision = None
        scanner = None
        last_status = None
        revision = ports.read_revision()
        try:
            while True:
                snapshot = ports.take_snapshot()
                if snapshot is None:
                    break
                settings, revision, overlay_rect = snapshot.settings, snapshot.revision, snapshot.overlay_rect
                profile, context, forced = snapshot.profile, snapshot.context, snapshot.force_regions
                started = deps.clock()
                key = (profile, context.binding_epoch)
                if key != source_key:
                    if source is not None:
                        retiring, source = source, None
                        retiring.close()
                    source_context = context
                    # The callback only emits immutable data. Qt delivers the
                    # terminal event to the GUI even while Paddle is blocked.
                    source = deps.source_factory(context, on_terminal=ports.publish_terminal)
                    source.open(context, roi_rects_px=tuple(resolve_region_crops(profile, context.geometry.image_size_px).values()))
                    source_key = key
                    last_status = None
                if scanner_revision != revision:
                    scanner = deps.scanner_factory(profile, ocr_reader=lambda img, lang: ports.read_ocr(img, lang, settings=settings), clock=deps.clock)
                    scanner_revision = revision
                frame = source.read_latest(now_s=started)
                status = source.status()
                current_status = CaptureStatus(revision, status.binding_epoch, status.phase, status.error)
                if current_status != last_status:
                    ports.publish_status(revision, current_status)
                    last_status = current_status
                if status.phase in ('unavailable', 'error'):
                    ports.publish_terminal(status)
                    break
                masks = ()
                if context.source_kind == 'desktop' and overlay_rect:
                    x, y, width, height = overlay_rect
                    if width > 0 and height > 0:
                        origin = context.geometry.region_px
                        masks = (Rect(x-origin.x-6, y-origin.y-6, width+12, height+12),)
                if frame is not None:
                    batch = scanner.observe(frame, settings=settings, context=context,
                        revision=revision, force_regions=forced, dynamic_masks_px=masks,
                        is_current=lambda: ports.is_current(revision))
                    if batch is not None:
                        ports.publish_observation(revision, batch)
                # Interruption is checked frequently without involving the GUI.
                deadline = started + settings.interval_ms / 1000
                while ports.is_current(revision) and deps.clock() < deadline:
                    deps.sleep_ms(20)
        except Exception:
            self._capture_error(source_context)
        finally:
            try:
                if source is not None:
                    source.close()
            except Exception:
                # Cleanup failure is terminal data, never an uncaught QThread exception.
                try:
                    self._capture_error(source_context)
                except Exception:
                    pass
            finally:
                self._finish(revision)
