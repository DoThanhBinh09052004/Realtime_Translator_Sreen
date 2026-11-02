"""Tests for GameToolbar – the passive floating game-controls widget.

Covers:
 - Stopped state: four visible icon-only actions with correct tooltips/accessible names.
 - Running state: collapses to single Play action with active ring animation.
 - Stopping: ring stops, toolbar expands at unchanged top-left.
 - Drag-vs-click: clicking emits toggle once; dragging emits position_released
   but no toggle; negative global coordinates stay unchanged.
 - Busy state blocks actions appropriately.
"""
import sys
from unittest.mock import patch

import pytest
from PyQt5.QtCore import QPoint, Qt, QEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action_names(toolbar):
    """Return list of visible action accessible-names, in layout order."""
    names = []
    for i in range(toolbar.layout().count()):
        w = toolbar.layout().itemAt(i).widget()
        if w is not None and w.isVisible():
            names.append(w.accessibleName())
    return names


def _visible_buttons(toolbar):
    """Return list of visible button widgets."""
    btns = []
    for i in range(toolbar.layout().count()):
        w = toolbar.layout().itemAt(i).widget()
        if w is not None and w.isVisible():
            btns.append(w)
    return btns


# ---------------------------------------------------------------------------
# Stopped-state tests
# ---------------------------------------------------------------------------

class TestStoppedState:
    """Stopped toolbar has four visible icon-only actions."""

    def test_four_actions_visible(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        names = _action_names(tb)
        assert len(names) == 4, f"Expected 4 visible actions, got {len(names)}: {names}"

    def test_action_order(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        names = _action_names(tb)
        assert names == ["Play", "Select region", "Open app", "Exit"]

    def test_tooltips(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tips = []
        for i in range(tb.layout().count()):
            w = tb.layout().itemAt(i).widget()
            if w is not None and w.isVisible():
                tips.append(w.toolTip())
        assert tips[0] == "Play"
        assert tips[1] == "Select region"
        assert tips[2] == "Open app"
        assert tips[3] == "Exit"

    def test_icon_only_no_text(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        for btn in _visible_buttons(tb):
            assert btn.text() == "", f"Button {btn.accessibleName()!r} should have no text"

    def test_ring_not_active(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        assert not tb._ring_timer.isActive()

    def test_frameless_translucent(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        flags = tb.windowFlags()
        assert flags & Qt.FramelessWindowHint
        assert flags & Qt.WindowStaysOnTopHint
        assert tb.testAttribute(Qt.WA_TranslucentBackground)

    def test_non_activating(self, qtbot):
        """Toolbar must not steal focus/activation from the game."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        flags = tb.windowFlags()
        # Assert native-window no-focus flags and button NoFocus explicitly
        assert flags & Qt.Tool
        assert flags & Qt.WindowDoesNotAcceptFocus
        assert tb.testAttribute(Qt.WA_ShowWithoutActivating)
        for btn in tb._buttons:
            assert btn.focusPolicy() == Qt.NoFocus


# ---------------------------------------------------------------------------
# Running-state tests
# ---------------------------------------------------------------------------

class TestRunningState:
    """Running collapses to one Play action with rotating ring."""

    def test_collapse_to_one_action(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        QApplication.processEvents()
        names = _action_names(tb)
        assert names == ["Stop"], f"Running should show only Stop, got {names}"

    def test_ring_active(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        QApplication.processEvents()
        assert tb._ring_timer.isActive()

    def test_stop_expands(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        QApplication.processEvents()
        tb.set_running(False)
        QApplication.processEvents()
        names = _action_names(tb)
        assert len(names) == 4

    def test_stop_preserves_topleft(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.move(200, 150)
        tb.show()
        QApplication.processEvents()
        orig_pos = tb.pos()
        tb.set_running(True)
        QApplication.processEvents()
        tb.set_running(False)
        QApplication.processEvents()
        assert tb.pos() == orig_pos, f"Top-left moved from {orig_pos} to {tb.pos()}"

    def test_ring_stops_on_stop(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        QApplication.processEvents()
        assert tb._ring_timer.isActive()
        tb.set_running(False)
        QApplication.processEvents()
        assert not tb._ring_timer.isActive()

    def test_hidden_running_initialization_timer_stopped(self, qtbot):
        """set_running(True) while hidden must not start the animation timer."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.set_running(True)
        assert not tb._ring_timer.isActive()
        # Showing resumes timer
        tb.show()
        QApplication.processEvents()
        assert tb._ring_timer.isActive()

    def test_hide_stops_timer_show_resumes(self, qtbot):
        """Hiding toolbar stops timer; showing while still running resumes it."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        assert tb._ring_timer.isActive()
        tb.hide()
        QApplication.processEvents()
        assert not tb._ring_timer.isActive()
        tb.show()
        QApplication.processEvents()
        assert tb._ring_timer.isActive()

    def test_stop_while_hidden_does_not_resume(self, qtbot):
        """Stopping while hidden keeps timer stopped when shown later."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        assert tb._ring_timer.isActive()
        tb.hide()
        QApplication.processEvents()
        assert not tb._ring_timer.isActive()
        tb.set_running(False)
        assert not tb._ring_timer.isActive()
        tb.show()
        QApplication.processEvents()
        assert not tb._ring_timer.isActive()

    def test_close_stops_timer_permanently(self, qtbot):
        """Closing the toolbar stops timer and prevents accidental restart."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        assert tb._ring_timer.isActive()
        tb.close()
        assert not tb._ring_timer.isActive()
        assert tb._is_closing

    def test_ring_center_uses_mapped_center_without_double_margins(self, qtbot):
        """Ring center matches button mapped center and does not add layout margins twice."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        btn0 = tb._buttons[0]
        # btn0.geometry().center() accounts for layout margins once
        expected_center = btn0.geometry().center()
        calc_x = btn0.x() + btn0.width() / 2.0
        calc_y = btn0.y() + btn0.height() / 2.0
        assert abs(calc_x - expected_center.x()) <= 1.0
        assert abs(calc_y - expected_center.y()) <= 1.0
        # Verify it does not equal center + extra margins
        margin_x = tb._layout.contentsMargins().left()
        if margin_x > 0:
            assert calc_x != (btn0.x() + btn0.width() / 2.0 + margin_x)


# ---------------------------------------------------------------------------
# Click / signal tests
# ---------------------------------------------------------------------------

class TestSignals:
    """Button clicks emit the correct signals exactly once."""

    def test_toggle_signal(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        play_btn = _visible_buttons(tb)[0]
        with qtbot.waitSignal(tb.toggle_requested, timeout=1000):
            QTest.mouseClick(play_btn, Qt.LeftButton)

    def test_region_signal(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        region_btn = _visible_buttons(tb)[1]
        with qtbot.waitSignal(tb.region_requested, timeout=1000):
            QTest.mouseClick(region_btn, Qt.LeftButton)

    def test_open_signal(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        open_btn = _visible_buttons(tb)[2]
        with qtbot.waitSignal(tb.open_requested, timeout=1000):
            QTest.mouseClick(open_btn, Qt.LeftButton)

    def test_quit_signal(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        quit_btn = _visible_buttons(tb)[3]
        with qtbot.waitSignal(tb.quit_requested, timeout=1000):
            QTest.mouseClick(quit_btn, Qt.LeftButton)

    def test_stop_signal_when_running(self, qtbot):
        """Clicking the collapsed Stop button emits toggle_requested."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        QApplication.processEvents()
        stop_btn = _visible_buttons(tb)[0]
        with qtbot.waitSignal(tb.toggle_requested, timeout=1000):
            QTest.mouseClick(stop_btn, Qt.LeftButton)


# ---------------------------------------------------------------------------
# Drag tests
# ---------------------------------------------------------------------------

class TestDrag:
    """Drag differentiated from click using Qt drag threshold."""

    def test_click_emits_toggle_not_position(self, qtbot):
        """A click (no drag) emits toggle_requested, not position_released."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        play_btn = _visible_buttons(tb)[0]
        position_emitted = []
        tb.position_released.connect(lambda x, y: position_emitted.append((x, y)))
        with qtbot.waitSignal(tb.toggle_requested, timeout=1000):
            QTest.mouseClick(play_btn, Qt.LeftButton)
        assert len(position_emitted) == 0, "Click should not emit position_released"

    def test_drag_emits_position_not_toggle(self, qtbot):
        """Dragging beyond threshold emits position_released, not toggle."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.move(100, 100)
        tb.show()
        QApplication.processEvents()

        toggle_emitted = []
        tb.toggle_requested.connect(lambda: toggle_emitted.append(True))
        position_emitted = []
        tb.position_released.connect(lambda x, y: position_emitted.append((x, y)))

        # Simulate drag: press on widget, move beyond drag threshold, release
        drag_threshold = max(QApplication.startDragDistance(), 5)
        press_pos = QPoint(22, 22)  # center-ish of the toolbar
        QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, press_pos)
        # Move well past the drag threshold
        for step in range(1, drag_threshold + 10):
            move_pos = press_pos + QPoint(step, 0)
            QTest.mouseMove(tb, move_pos)
        release_pos = press_pos + QPoint(drag_threshold + 10, 0)
        QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, release_pos)
        QApplication.processEvents()

        assert len(toggle_emitted) == 0, "Drag should not emit toggle_requested"
        assert len(position_emitted) == 1, "Drag should emit position_released"

    def test_drag_collapsed_button_no_stop(self, qtbot):
        """Dragging over the collapsed Stop button must not stop translation."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.move(100, 100)
        tb.show()
        QApplication.processEvents()
        tb.set_running(True)
        QApplication.processEvents()

        toggle_emitted = []
        tb.toggle_requested.connect(lambda: toggle_emitted.append(True))

        drag_threshold = max(QApplication.startDragDistance(), 5)
        press_pos = QPoint(22, 22)
        QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, press_pos)
        for step in range(1, drag_threshold + 10):
            QTest.mouseMove(tb, press_pos + QPoint(step, 0))
        QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier,
                           press_pos + QPoint(drag_threshold + 10, 0))
        QApplication.processEvents()

        assert len(toggle_emitted) == 0, "Drag over collapsed button must not stop"

    def test_negative_coordinates_preserved(self, qtbot):
        """After dragging to a negative global position, toolbar stays there."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.move(-50, -30)
        tb.show()
        QApplication.processEvents()

        drag_threshold = max(QApplication.startDragDistance(), 5)
        press_pos = QPoint(22, 22)
        QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, press_pos)
        # Drag leftward – further into negative territory
        for step in range(1, drag_threshold + 10):
            QTest.mouseMove(tb, press_pos + QPoint(-step, 0))
        QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier,
                           press_pos + QPoint(-(drag_threshold + 10), 0))
        QApplication.processEvents()

        # Position must remain in negative territory – no clamping to (0, 0)
        assert tb.pos().x() < 0, f"X should be negative, got {tb.pos().x()}"

    def test_position_released_reports_global_position(self, qtbot):
        """position_released emits the toolbar's global top-left."""
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.move(300, 200)
        tb.show()
        QApplication.processEvents()

        positions = []
        tb.position_released.connect(lambda x, y: positions.append((x, y)))

        drag_threshold = max(QApplication.startDragDistance(), 5)
        press_pos = QPoint(22, 22)
        QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, press_pos)
        for step in range(1, drag_threshold + 10):
            QTest.mouseMove(tb, press_pos + QPoint(step, 0))
        QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier,
                           press_pos + QPoint(drag_threshold + 10, 0))
        QApplication.processEvents()

        assert len(positions) == 1
        rx, ry = positions[0]
        # The emitted position should match the widget's actual global pos
        assert rx == tb.pos().x()
        assert ry == tb.pos().y()


# ---------------------------------------------------------------------------
# Busy-state tests
# ---------------------------------------------------------------------------

class TestBusy:
    """set_busy(True) disables action buttons."""

    def test_busy_disables_actions(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_busy(True)
        QApplication.processEvents()
        for btn in _visible_buttons(tb):
            assert not btn.isEnabled(), f"{btn.accessibleName()!r} should be disabled"

    def test_busy_blocks_toggle(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_busy(True)
        QApplication.processEvents()

        toggle_emitted = []
        tb.toggle_requested.connect(lambda: toggle_emitted.append(True))
        play_btn = _visible_buttons(tb)[0]
        QTest.mouseClick(play_btn, Qt.LeftButton)
        QApplication.processEvents()
        assert len(toggle_emitted) == 0

    def test_unbusy_re_enables(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        tb.set_busy(True)
        QApplication.processEvents()
        tb.set_busy(False)
        QApplication.processEvents()
        for btn in _visible_buttons(tb):
            assert btn.isEnabled(), f"{btn.accessibleName()!r} should be enabled"


# ---------------------------------------------------------------------------
# 44px target size
# ---------------------------------------------------------------------------

class TestTargetSize:
    """Each button target should be 44px."""

    def test_button_size(self, qtbot):
        from ui.game_toolbar import GameToolbar
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()
        QApplication.processEvents()
        for btn in _visible_buttons(tb):
            assert btn.minimumWidth() >= 44
            assert btn.minimumHeight() >= 44
