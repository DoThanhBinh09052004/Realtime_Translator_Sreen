from math import floor, ceil
from core.blocks.models import Rect, CaptureGeometry


def qt_selection_to_physical(rect, screen):
    l, p = screen.logical_rect, screen.physical_rect
    sx, sy = p.width/l.width, p.height/l.height
    x, y = floor(p.x+(rect.x-l.x)*sx), floor(p.y+(rect.y-l.y)*sy)
    right, bottom = ceil(p.x+(rect.right-l.x)*sx), ceil(p.y+(rect.bottom-l.y)*sy)
    return dict(left=x, top=y, width=right-x, height=bottom-y)


def resolve_capture_geometry(region, screens, image_size_px):
    try:
        r = Rect(region['left'], region['top'], region['width'], region['height'])
        if min(image_size_px) <= 0:
            return None
        matches = [s for s in screens if s.physical_rect.contains(r)]
        return CaptureGeometry(r, matches[0], image_size_px) if len(matches) == 1 else None
    except (ValueError, TypeError, KeyError):
        return None


def overlay_window_rect(geometry):
    r, l, p = geometry.region_px, geometry.screen.logical_rect, geometry.screen.physical_rect
    return Rect(l.x+(r.x-p.x)*l.width/p.width, l.y+(r.y-p.y)*l.height/p.height,
                r.width*l.width/p.width, r.height*l.height/p.height)


def ocr_rect_to_overlay(rect, geometry):
    window = overlay_window_rect(geometry)
    w, h = geometry.image_size_px
    return Rect(rect.x*window.width/w, rect.y*window.height/h, rect.width*window.width/w, rect.height*window.height/h)


def subtitle_mask_rect(rect, geometry):
    """Clip the legacy global Qt rectangle before converting to physical pixels."""
    if rect is None:
        return None
    try:
        r = Rect(*rect)
        s = geometry.screen.logical_rect
        x, y, right, bottom = max(r.x, s.x), max(r.y, s.y), min(r.right, s.right), min(r.bottom, s.bottom)
        if right <= x or bottom <= y:
            return None
        p = qt_selection_to_physical(Rect(x, y, right-x, bottom-y), geometry.screen)
        return p['left'], p['top'], p['width'], p['height']
    except (ValueError, TypeError):
        return None
