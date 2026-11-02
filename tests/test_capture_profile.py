"""Profile validation, lossless legacy migration and atomic persistence contracts."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from core import config
from core.blocks.models import Rect, ScreenMapping


def raw_profile():
    return {
        'version': 1, 'source_kind': 'desktop', 'monitor_name': 'left', 'window_hint': None,
        'regions': [{'id': '11111111-1111-4111-8111-111111111111', 'name': ' Subtitles ',
                     'rect': {'x': .1, 'y': .2, 'width': .4, 'height': .3}, 'enabled': True}],
        'exclusions': [],
    }


@pytest.fixture
def screens():
    return (
        ScreenMapping('left', Rect(-1280, 0, 1280, 720), Rect(-1920, 0, 1920, 1080)),
        ScreenMapping('right', Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1080)),
    )


def test_legacy_region_roundtrips_exact_pixels(screens):
    from core.capture.profile import migrate_legacy_region
    region = {'left': -1783, 'top': 117, 'width': 641, 'height': 179}
    profile = migrate_legacy_region(region, screens)
    assert profile.source_kind == 'desktop'
    assert profile.monitor_name == 'left'
    assert profile.exclusions == ()
    roi = profile.regions[0]
    assert roi.enabled
    assert UUID(roi.id)
    assert (round(roi.rect.x * 1920) - 1920, round(roi.rect.y * 1080),
            round(roi.rect.width * 1920), round(roi.rect.height * 1080)) == (-1783, 117, 641, 179)
    assert migrate_legacy_region(region, screens) == profile


def test_legacy_spanning_region_is_retained(screens):
    region = {'left': -50, 'top': 10, 'width': 100, 'height': 100}
    path = Path(config.CONFIG_PATH)
    path.write_text(json.dumps({'region': region}), encoding='utf-8')
    before = path.read_bytes()
    assert config.load_capture_profile(screens) is None
    assert config.load_region() == region
    assert path.read_bytes() == before


@pytest.mark.parametrize('region', [None, {}, {'left': True, 'top': 0, 'width': 1, 'height': 1},
                                        {'left': 0, 'top': 0, 'width': 0, 'height': 1},
                                        {'left': 9999, 'top': 0, 'width': 1, 'height': 1}])
def test_unresolvable_legacy_region_is_not_migrated(region, screens):
    from core.capture.profile import migrate_legacy_region
    assert migrate_legacy_region(region, screens) is None


@pytest.mark.parametrize('field,value', [
    ('x', float('nan')), ('y', float('inf')), ('width', float('-inf')),
    ('x', True), ('height', False), ('x', -.01), ('y', 1.01),
    ('width', 0), ('height', -.1), ('width', .95), ('x', '0.1'),
])
def test_profile_rejects_nonfinite_bool_and_invalid_coordinates(field, value):
    from core.capture.profile import parse_capture_profile
    raw = raw_profile()
    raw['regions'][0]['rect'][field] = value
    with pytest.raises(config.ConfigError):
        parse_capture_profile(raw)


@pytest.mark.parametrize('mutation', [
    'duplicate_ids', 'nine_regions', 'seventeen_exclusions', 'no_enabled', 'empty_regions',
    'bad_uuid', 'blank_name', 'non_bool_enabled', 'overlap', 'disabled_overlap',
    'bad_version', 'bool_version', 'bad_source', 'blank_monitor', 'blank_hint',
    'non_list_regions', 'bad_exclusion', 'null_profile',
])
def test_profile_rejects_nonfinite_bool_duplicate_ids_limits_and_no_enabled_roi(mutation):
    from core.capture.profile import parse_capture_profile
    raw = raw_profile()
    roi = raw['regions'][0]
    if mutation in ('duplicate_ids', 'overlap', 'disabled_overlap'):
        other = deepcopy(roi)
        if mutation != 'duplicate_ids':
            other['id'] = '22222222-2222-4222-8222-222222222222'
        if mutation == 'disabled_overlap':
            other['enabled'] = False
        raw['regions'].append(other)
    elif mutation == 'nine_regions':
        raw['regions'] = [dict(roi, id=f'{i:08x}-1111-4111-8111-111111111111',
                               rect={'x': i / 10, 'y': 0, 'width': .05, 'height': .1})
                          for i in range(9)]
    elif mutation == 'seventeen_exclusions':
        raw['exclusions'] = [dict(roi['rect']) for _ in range(17)]
    elif mutation == 'no_enabled':
        roi['enabled'] = False
    elif mutation == 'empty_regions':
        raw['regions'] = []
    elif mutation == 'bad_uuid':
        roi['id'] = 'not-a-uuid'
    elif mutation == 'blank_name':
        roi['name'] = '  '
    elif mutation == 'non_bool_enabled':
        roi['enabled'] = 1
    elif mutation in ('bad_version', 'bool_version'):
        raw['version'] = 2 if mutation == 'bad_version' else True
    elif mutation == 'bad_source':
        raw['source_kind'] = 'title-match'
    elif mutation == 'blank_monitor':
        raw['monitor_name'] = ' '
    elif mutation == 'blank_hint':
        raw.update(source_kind='window', monitor_name=None, window_hint=' ')
    elif mutation == 'non_list_regions':
        raw['regions'] = {}
    elif mutation == 'bad_exclusion':
        raw['exclusions'] = [dict(roi['rect'], width=True)]
    elif mutation == 'null_profile':
        raw = None
    with pytest.raises(config.ConfigError):
        parse_capture_profile(raw)


def test_touching_regions_and_overlapping_exclusions_are_allowed():
    from core.capture.profile import parse_capture_profile
    raw = raw_profile()
    raw['regions'][0]['rect'] = {'x': 0, 'y': 0, 'width': .5, 'height': 1}
    raw['regions'].append(dict(raw['regions'][0], id='22222222-2222-4222-8222-222222222222',
                               rect={'x': .5, 'y': 0, 'width': .5, 'height': 1}))
    raw['exclusions'] = [{'x': .1, 'y': .2, 'width': .5, 'height': .6}] * 16
    profile = parse_capture_profile(raw)
    assert profile.regions[0].name == 'Subtitles'
    assert len(profile.regions) == 2
    assert len(profile.exclusions) == 16
    raw['regions'][0]['name'] = 'mutated'
    assert profile.regions[0].name == 'Subtitles'
    with pytest.raises(FrozenInstanceError):
        profile.regions[0].enabled = False


def test_profile_save_is_atomic_and_preserves_legacy_region_and_credentials(monkeypatch, screens):
    from core.capture.profile import parse_capture_profile
    region = {'left': -50, 'top': 10, 'width': 100, 'height': 100}
    config.save_config_values({'region': region, 'other_setting': 'keep'})
    config.save_provider_api_key('OpenAI', 'fake-profile-secret', persist=False)
    before_credentials = config.load_provider_api_key('OpenAI')
    path = Path(config.CONFIG_PATH)
    original = path.read_bytes()
    real_replace = config.os.replace
    def refuse(*args):
        raise OSError('fake-secret')
    monkeypatch.setattr(config.os, 'replace', refuse)
    profile = parse_capture_profile(raw_profile())
    with pytest.raises(config.ConfigError):
        config.save_capture_profile(profile)
    assert path.read_bytes() == original
    assert not list(path.parent.glob('.settings-*.tmp'))
    monkeypatch.setattr(config.os, 'replace', real_replace)
    config.save_capture_profile(profile)
    assert config.load_capture_profile(screens) == profile
    assert config.load_region() == region
    assert config.load_config()['other_setting'] == 'keep'
    assert config.load_provider_api_key('OpenAI') == before_credentials
    assert 'fake-profile-secret' not in path.read_text(encoding='utf-8')


def test_read_does_not_write(screens):
    path = Path(config.CONFIG_PATH)
    profile = config.load_capture_profile(screens)
    assert profile.monitor_name == 'right'
    assert not path.exists()
    path.write_text(json.dumps({'region': {'left': -1500, 'top': 20, 'width': 200, 'height': 100}}), encoding='utf-8')
    before = path.read_bytes()
    config.load_capture_profile(screens)
    assert path.read_bytes() == before


def test_invalid_existing_profile_reports_error_without_falling_back(screens):
    path = Path(config.CONFIG_PATH)
    path.write_text(json.dumps({'capture_profile': None}), encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(config.ConfigError):
        config.load_capture_profile(screens)
    with pytest.raises(config.ConfigError):
        config.normalize_config({'capture_profile': None})
    assert path.read_bytes() == original


def test_explicit_profile_save_can_replace_invalid_existing_profile(screens):
    from core.capture.profile import parse_capture_profile
    path = Path(config.CONFIG_PATH)
    region = {'left': -50, 'top': 10, 'width': 100, 'height': 100}
    path.write_text(json.dumps({'capture_profile': None, 'region': region}), encoding='utf-8')
    profile = parse_capture_profile(raw_profile())
    config.save_capture_profile(profile)
    assert config.load_capture_profile(screens) == profile
    assert config.load_region() == region


def test_window_profile_persists_hint_without_runtime_identity(screens):
    from core.capture.profile import parse_capture_profile
    raw = raw_profile()
    raw.update(source_kind='window', monitor_name=None, window_hint=' Game / game.exe ',
               hwnd=100, pid=200, process_started_100ns=300)
    profile = parse_capture_profile(raw)
    config.save_capture_profile(profile)
    persisted = json.loads(Path(config.CONFIG_PATH).read_text(encoding='utf-8'))
    assert persisted['schema_version'] == 1
    assert persisted['capture_profile']['window_hint'] == 'Game / game.exe'
    for identity_field in ('hwnd', 'pid', 'process_started_100ns'):
        assert identity_field not in json.dumps(persisted)
    assert config.load_capture_profile(screens) == profile


def test_captured_frame_owns_readonly_bgra_pixels():
    from core.capture.models import CapturedFrame
    source = np.zeros((2, 3, 4), dtype=np.uint8)
    frame = CapturedFrame(1, 2, source, (10, 20), (30, 40), 1.5)
    source[:] = 255
    assert frame.pixels.shape == (2, 3, 4)
    assert not frame.pixels.any()
    with pytest.raises(ValueError):
        frame.pixels[0, 0, 0] = 1


@pytest.mark.parametrize('pixels', [np.zeros((2, 3, 3), dtype=np.uint8),
                                   np.zeros((2, 3, 4), dtype=np.float32)])
def test_captured_frame_rejects_non_bgra_uint8(pixels):
    from core.capture.models import CapturedFrame
    with pytest.raises(ValueError):
        CapturedFrame(1, 2, pixels, (0, 0), (3, 2), 1.)
