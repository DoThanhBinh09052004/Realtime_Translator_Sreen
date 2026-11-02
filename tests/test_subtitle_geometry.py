import pytest
from PyQt5.QtCore import QPoint, QRect, QSize
from ui.subtitle_geometry import clamp_position, preset_position

@pytest.mark.parametrize('area,preset,expected', [
 ((1920,0,1920,1080),'bottom_center',(2730,940)),
 ((-1920,0,1920,1080),'bottom_center',(-1110,940)),
 ((0,-1080,1920,1080),'bottom_center',(810,-140)),
 ((1920,40,1880,1000),'bottom_center',(2710,900)),
 ((-1920,-1080,1920,1080),'top_center',(-1110,-1020)),
 ((-1920,-1080,1920,1080),'bottom_left',(-1860,-140)),
])
def test_preset_in_global_work_area(area, preset, expected):
    assert preset_position(QRect(*area), QSize(300,60), preset) == QPoint(*expected)

@pytest.mark.parametrize('position,expected', [((500,500),(-310,-70)),((-5000,-5000),(-1910,-1070))])
def test_clamp_uses_exclusive_global_edges(position, expected):
    assert clamp_position(QRect(-1920,-1080,1920,1080), QSize(300,60), QPoint(*position)) == QPoint(*expected)

def test_oversized_overlay_anchors_at_origin():
    assert clamp_position(QRect(1920,0,200,100), QSize(300,150), QPoint(500,500)) == QPoint(1920,0)

@pytest.mark.parametrize('preset', ['custom', 'unknown'])
def test_custom_preset_does_not_move(preset):
    assert preset_position(QRect(0,0,1920,1080), QSize(300,60), preset) is None

def test_small_preset_uses_legacy_minimum_size():
    assert preset_position(QRect(0,0,1920,1080), QSize(20,20), 'bottom_center') == QPoint(860,960)

@pytest.mark.parametrize('size,expected', [((1905,1065),(0,15)),((1910,1060),(0,10)),((2000,60),(0,1010))])
def test_clamp_margin_is_independent_per_axis(size, expected):
    assert clamp_position(QRect(0,0,1920,1080), QSize(*size), QPoint(-100,5000)) == QPoint(*expected)
