from types import SimpleNamespace
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QCursor
from core.blocks.models import Rect, ScreenMapping


def test_selector_emits_global_physical_not_local_coordinates(qtbot, monkeypatch):
    from ui.selector import RegionSelector
    mapping = ScreenMapping('left', Rect(-1280, 0, 1280, 720), Rect(-1920, 0, 1920, 1080))
    monkeypatch.setattr(QCursor, 'pos', lambda: QPoint(-1000, 20))
    selector = RegionSelector(geometry_provider=SimpleNamespace(snapshot=lambda: (mapping,)))
    qtbot.addWidget(selector)
    selector.start, selector.end = QPoint(300, 200), QPoint(100, 100)
    with qtbot.waitSignal(selector.region_selected) as signal:
        selector.mouseReleaseEvent(SimpleNamespace(pos=lambda: QPoint(100, 100)))
    assert signal.args[0] == dict(left=-1770, top=150, width=300, height=150)
