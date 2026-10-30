"""Validate persistent capture profiles and migrate single-monitor legacy ROIs."""
from uuid import NAMESPACE_URL, UUID, uuid5

from core.blocks.models import Rect, ScreenMapping
from core.config import ConfigError
from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect


def _invalid() -> ConfigError:
    return ConfigError('Cấu hình nguồn chụp không hợp lệ. Vui lòng chọn lại nguồn và vùng OCR.')


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid()
    return value.strip()


def _rect(raw: object) -> NormalizedRect:
    if not isinstance(raw, dict):
        raise _invalid()
    try:
        return NormalizedRect(*(raw[key] for key in ('x', 'y', 'width', 'height')))
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _invalid() from None


def parse_capture_profile(raw: object) -> CaptureProfile:
    """Parse a nested version-1 JSON object; invalid existing profiles raise."""
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1:
        raise _invalid()
    kind = raw.get('source_kind')
    if kind not in ('desktop', 'window'):
        raise _invalid()
    monitor = raw.get('monitor_name')
    hint = raw.get('window_hint')
    if kind == 'desktop':
        monitor = _text(monitor)
        if hint is not None:
            raise _invalid()
    else:
        if monitor is not None:
            raise _invalid()
        hint = None if hint is None else _text(hint)
    regions_raw, exclusions_raw = raw.get('regions'), raw.get('exclusions')
    if (not isinstance(regions_raw, list) or not 1 <= len(regions_raw) <= 8
            or not isinstance(exclusions_raw, list) or len(exclusions_raw) > 16):
        raise _invalid()
    regions, ids = [], set()
    for item in regions_raw:
        if not isinstance(item, dict) or type(item.get('enabled')) is not bool:
            raise _invalid()
        try:
            region_id = str(UUID(_text(item.get('id'))))
        except (ValueError, AttributeError):
            raise _invalid() from None
        if region_id in ids:
            raise _invalid()
        ids.add(region_id)
        rect = _rect(item.get('rect'))
        for other in regions:
            r = other.rect
            if (rect.x < r.x + r.width and rect.x + rect.width > r.x
                    and rect.y < r.y + r.height and rect.y + rect.height > r.y):
                raise _invalid()
        regions.append(CaptureRegion(region_id, _text(item.get('name')), rect, item['enabled']))
    if not any(region.enabled for region in regions):
        raise _invalid()
    return CaptureProfile(1, kind, monitor, hint, tuple(regions),
                          tuple(_rect(item) for item in exclusions_raw))


def serialize_capture_profile(profile: CaptureProfile) -> dict:
    """Whitelist persistent fields, validate typed callers, and omit runtime identity."""
    if not isinstance(profile, CaptureProfile):
        raise _invalid()
    def rect_data(rect):
        if not isinstance(rect, NormalizedRect):
            raise _invalid()
        return {key: getattr(rect, key) for key in ('x', 'y', 'width', 'height')}
    try:
        raw = {
            'version': profile.version, 'source_kind': profile.source_kind,
            'monitor_name': profile.monitor_name, 'window_hint': profile.window_hint,
            'regions': [{'id': region.id, 'name': region.name, 'rect': rect_data(region.rect),
                         'enabled': region.enabled} for region in profile.regions],
            'exclusions': [rect_data(rect) for rect in profile.exclusions],
        }
    except (AttributeError, TypeError):
        raise _invalid() from None
    normalized = parse_capture_profile(raw)
    raw.update(monitor_name=normalized.monitor_name, window_hint=normalized.window_hint)
    for data, region in zip(raw['regions'], normalized.regions):
        data.update(id=region.id, name=region.name)
    return raw


def migrate_legacy_region(region: dict, screens: tuple[ScreenMapping, ...]) -> CaptureProfile | None:
    """Resolve physical legacy pixels only when one monitor contains the entire ROI."""
    if (not isinstance(region, dict)
            or any(type(region.get(key)) is not int for key in ('left', 'top', 'width', 'height'))
            or region['width'] <= 0 or region['height'] <= 0):
        return None
    rect = Rect(region['left'], region['top'], region['width'], region['height'])
    candidates = [screen for screen in screens if screen.physical_rect.contains(rect)]
    if len(candidates) != 1 or not candidates[0].name.strip():
        return None
    screen = candidates[0]
    source = screen.physical_rect
    normalized = NormalizedRect((rect.x - source.x) / source.width,
                                (rect.y - source.y) / source.height,
                                rect.width / source.width, rect.height / source.height)
    region_id = str(uuid5(NAMESPACE_URL, f'translate-hud:legacy:{screen.name}:'
                          f'{rect.x}:{rect.y}:{rect.width}:{rect.height}'))
    return CaptureProfile(1, 'desktop', screen.name, None,
                          (CaptureRegion(region_id, 'OCR 1', normalized, True),), ())
