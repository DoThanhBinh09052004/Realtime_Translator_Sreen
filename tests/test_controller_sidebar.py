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
    assert sidebar.width() == 64
    assert sidebar.objectName() == 'sidebarFrame'
    assert any(label.pixmap() and not label.pixmap().isNull() for label in sidebar.findChildren(QLabel))


def test_sidebar_collapse_and_theme_keep_navigation(qtbot):
    from ui.widgets.sidebar import ControllerSidebar
    sidebar = ControllerSidebar((('languages', 'Công cụ dịch', 'Chọn công cụ'),), None)
    qtbot.addWidget(sidebar)
    assert sidebar.is_collapsed() and sidebar.width() == 64
    sidebar.set_collapsed(False)
    assert sidebar.width() == 212
    assert sidebar.nav_buttons[0].text().strip() == 'Công cụ dịch'
    sidebar.apply_theme('dark')
    sidebar.set_collapsed(True)
    assert sidebar.width() == 64 and sidebar.nav_buttons[0].text() == ''
    assert sidebar.nav_buttons[0].toolTip()
    spy = QSignalSpy(sidebar.theme_toggle_requested)
    sidebar.theme_button.click()
    assert len(spy) == 1


def test_sidebar_animation_reversing_and_solid_icons(qtbot):
    from ui.widgets.sidebar import ControllerSidebar
    sidebar = ControllerSidebar((
        ('layout-dashboard', 'Tổng quan', 'Dashboard'),
        ('bot', 'Công cụ dịch', 'AI Tools'),
    ), None)
    qtbot.addWidget(sidebar)
    sidebar.show()

    # Active icon should be solid
    sidebar.set_active_page(0)
    assert sidebar.nav_buttons[0]._theme_icon[0] == 'layout-dashboard-solid'
    assert sidebar.nav_buttons[1]._theme_icon[0] == 'bot'

    # Switch active page
    sidebar.set_active_page(1)
    assert sidebar.nav_buttons[0]._theme_icon[0] == 'layout-dashboard'
    assert sidebar.nav_buttons[1]._theme_icon[0] == 'bot-solid'

    # Animation expand and mid-flight reverse
    sidebar.set_collapsed(False)
    assert sidebar.is_collapsed() is False
    # Reversing while running
    sidebar.set_collapsed(True)
    assert sidebar.is_collapsed() is True
    qtbot.waitUntil(lambda: sidebar.width() == 64, timeout=1000)
    assert sidebar.width() == 64
