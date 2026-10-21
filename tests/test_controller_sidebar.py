import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QLabel


@pytest.mark.parametrize('logo', [None, 'missing.png', 'valid'])
def test_sidebar_signals_logo_and_status(qtbot, tmp_path, logo):
    from ui.widgets.sidebar import ControllerSidebar
    from PyQt5.QtGui import QPixmap
    if logo == 'valid':
        path = tmp_path / 'logo.png'
        pixmap = QPixmap(28, 28)
        pixmap.fill()
        pixmap.save(str(path))
        logo = str(path)
    sidebar = ControllerSidebar((('bot', 'AI', 'Settings'), ('palette', 'Phụ đề', 'Style')), logo)
    qtbot.addWidget(sidebar)
    spy = QSignalSpy(sidebar.page_requested)
    quit_spy = QSignalSpy(sidebar.quit_requested)
    for index in (1, 0, 1):
        sidebar.set_active_page(index)
        sidebar.nav_buttons[index].click()
    assert list(spy) == [[1], [0], [1]]
    sidebar.quit_button.click()
    assert len(quit_spy) == 1
    sidebar.set_status('Ready', 'color: green;')
    assert sidebar.status.text() == 'Ready'
    assert sidebar.width() == 205
    assert sidebar.objectName() == 'sidebarFrame'
    assert any(label.pixmap() and not label.pixmap().isNull() for label in sidebar.findChildren(QLabel))
