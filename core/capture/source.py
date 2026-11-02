"""Owner-thread capture contract and lazy adapter selection."""
from typing import Callable, Protocol

from core.blocks.models import Rect
from core.capture.models import CaptureContext, CapturedFrame, SourceStatus


class CaptureSource(Protocol):
    def open(self, context: CaptureContext, *, roi_rects_px: tuple[Rect, ...] | None = None) -> None: ...

    def read_latest(self, *, now_s: float) -> CapturedFrame | None: ...

    def status(self) -> SourceStatus: ...

    def close(self) -> None: ...


def create_capture_source(context: CaptureContext, *,
                          on_terminal: Callable[[SourceStatus], None] | None = None) -> CaptureSource:
    if context.source_kind == 'desktop':
        from core.capture.desktop import DesktopCaptureSource
        return DesktopCaptureSource(on_terminal=on_terminal)
    if context.source_kind == 'window':
        from core.capture.wgc import WgcCaptureSource
        return WgcCaptureSource(on_terminal=on_terminal)
    raise ValueError('Unknown capture source kind')
