"""Pure source and layout identity values for dialogue memory reconciliation."""
import hashlib

from core.dialogue.context_models import SourceKey, ScopeSpec


def memory_identity(*, source_invalid=False, profile=None, context=None, geometry=None, region=None):
    if source_invalid:
        return None, ()
    if profile is not None and context is not None:
        window = context.window
        identity = ((window.hwnd, window.pid, window.process_started_100ns, context.binding_epoch)
                    if window is not None else
                    (profile.monitor_name or context.geometry.screen.name, context.binding_epoch))
        exclusions = tuple(v for rect in profile.exclusions for v in (rect.x, rect.y, rect.width, rect.height))
        # Layout tuples remain compact even with many exclusion rectangles.
        exclusion_key = hashlib.sha256(repr(exclusions).encode()).hexdigest()
        scopes = tuple(ScopeSpec(r.id, (*context.geometry.image_size_px,
                       r.rect.x, r.rect.y, r.rect.width, r.rect.height, exclusion_key))
                       for r in profile.regions if r.enabled)
        return SourceKey(profile.source_kind, identity), scopes
    region = {} if region is None else region
    screen = geometry.screen.name if geometry is not None else str(region.get('monitor', 'legacy'))
    layout = tuple(region.get(k, 0) for k in ('left', 'top', 'width', 'height'))
    return SourceKey('desktop', (screen,)), (ScopeSpec('legacy-subtitle', layout),)
