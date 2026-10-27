"""Passive floating game-controls toolbar.

GameToolbar is a frameless, translucent, topmost, non-activating QWidget that
emits signals when the user clicks its icon buttons. It never calls the worker
or saves config itself. A parent GameControls coordinator (Task 2+) connects
the signals to the actual controller lifecycle.

States
------
- **Stopped** – four 44 px icon-only buttons in a horizontal row:
  Play ▸, Select region, Open app, Exit.
- **Running** – collapses to a single *Stop* button with a slowly rotating
  outer ring. The triangle icon stays still; only the ring rotates.
- **Busy** – all buttons disabled (e.g. during worker start-up).

Drag vs Click
-------------
Mouse handling on the *widget* (not individual buttons) differentiates a
drag from a click using ``QApplication.startDragDistance()``.  A completed
drag emits ``position_released(x, y)`` with the toolbar's global top-left
and suppresses any button activation.  Negative coordinates are preserved
without clamping.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import (
    QEvent, QObject, QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal,
)
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QMouseEvent,
)
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QPushButton, QWidget,
)

from ui.icons import get_lucide_icon
from ui.styles import CYBER_PALETTE

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BUTTON_SIZE = 44
_ICON_SIZE = 20
_RING_INTERVAL_MS = 40       # ~25 fps
_RING_STEP_DEG = 2.0         # degrees per tick – modest speed
_RING_RADIUS = 19            # ring drawn just inside button bounds
_RING_WIDTH = 2.5
_RING_ARC_SPAN = 270         # how much of the circle the arc covers (degrees)

_BG_COLOR = QColor(CYBER_PALETTE["bg_card"])
_BG_COLOR.setAlpha(230)

_ICON_COLOR = CYBER_PALETTE["text_muted"]        # #8c90a4
_ICON_COLOR_ACTIVE = CYBER_PALETTE["neon_green"]  # #10b981

# Minimum threshold for offscreen mode where startDragDistance can be 0
_MIN_DRAG_DISTANCE = 5

# Button definitions: (icon_name, accessible_name, tooltip, signal_attr)
_STOPPED_BUTTONS = [
    ("play",       "Play",          "Play",          "toggle_requested"),
    ("scan",       "Select region", "Select region", "region_requested"),
    ("maximize-2", "Open app",      "Open app",      "open_requested"),
    ("log-out",    "Exit",          "Exit",           "quit_requested"),
]


# ---------------------------------------------------------------------------
# GameToolbar
# ---------------------------------------------------------------------------

class GameToolbar(QWidget):
    """Passive floating game toolbar – emits signals, owns no business logic."""

    # Signals
    toggle_requested = pyqtSignal()
    region_requested = pyqtSignal()
    open_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    position_released = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Window flags: frameless, topmost, tool (non-activating)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.BypassWindowManagerHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)

        # State
        self._running = False
        self._busy = False
        self._is_closing = False
        self._ring_angle = 0.0

        # Drag tracking
        self._drag_origin: QPoint | None = None    # widget-local press pos
        self._drag_global_origin: QPoint | None = None  # global press pos
        self._widget_origin: QPoint | None = None  # widget global pos at press
        self._dragging = False

        # Ring animation timer
        self._ring_timer = QTimer(self)
        self._ring_timer.setInterval(_RING_INTERVAL_MS)
        self._ring_timer.timeout.connect(self._advance_ring)

        # Layout
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(2)

        # Create buttons
        self._buttons: list[QPushButton] = []
        self._signal_map: dict[QPushButton, str] = {}
        for icon_name, acc_name, tooltip, sig_attr in _STOPPED_BUTTONS:
            btn = self._make_button(icon_name, acc_name, tooltip, sig_attr)
            self._buttons.append(btn)
            self._layout.addWidget(btn)

        self.setLayout(self._layout)

    # -- Button factory -----------------------------------------------------

    def _make_button(
        self, icon_name: str, accessible_name: str, tooltip: str, signal_attr: str
    ) -> QPushButton:
        btn = QPushButton(self)
        btn.setIcon(get_lucide_icon(icon_name, color=_ICON_COLOR, size=_ICON_SIZE))
        btn.setAccessibleName(accessible_name)
        btn.setToolTip(tooltip)
        btn.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
        btn.setMinimumSize(_BUTTON_SIZE, _BUTTON_SIZE)
        btn.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(self._button_stylesheet())
        btn.installEventFilter(self)
        self._signal_map[btn] = signal_attr
        btn.clicked.connect(lambda checked, sa=signal_attr: self._on_button_clicked(sa))
        return btn

    @staticmethod
    def _button_stylesheet() -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.08);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.15);
            }}
            QPushButton:disabled {{
                opacity: 0.4;
            }}
        """

    # -- Signal dispatch (suppressed during drag) ---------------------------

    def _on_button_clicked(self, signal_attr: str) -> None:
        if self._dragging:
            return
        sig = getattr(self, signal_attr, None)
        if sig is not None:
            sig.emit()

    # -- Public state API ---------------------------------------------------

    def set_running(self, running: bool) -> None:
        """Switch between running (collapsed) and stopped (expanded) states."""
        self._running = running
        topleft = self.pos()

        if running:
            # Collapse: hide all but first, rebrand first as Stop
            for btn in self._buttons[1:]:
                btn.setVisible(False)
            btn0 = self._buttons[0]
            btn0.setIcon(get_lucide_icon("play", color=_ICON_COLOR_ACTIVE, size=_ICON_SIZE))
            btn0.setAccessibleName("Stop")
            btn0.setToolTip("Stop")
            self._signal_map[btn0] = "toggle_requested"
            # Start ring only if visible and not closing
            self._ring_angle = 0.0
            if self.isVisible() and not self._is_closing:
                self._ring_timer.start()
            else:
                self._ring_timer.stop()
        else:
            # Expand: show all, restore first to Play
            btn0 = self._buttons[0]
            btn0.setIcon(get_lucide_icon("play", color=_ICON_COLOR, size=_ICON_SIZE))
            btn0.setAccessibleName("Play")
            btn0.setToolTip("Play")
            self._signal_map[btn0] = "toggle_requested"
            for btn in self._buttons[1:]:
                btn.setVisible(True)
            # Stop ring
            self._ring_timer.stop()
            self._ring_angle = 0.0

        # Adjust size to fit content, then restore top-left
        self.adjustSize()
        self.move(topleft)
        self.update()

    def set_busy(self, busy: bool) -> None:
        """Enable/disable all action buttons."""
        self._busy = busy
        for btn in self._buttons:
            btn.setEnabled(not busy)

    # -- Visibility & lifecycle hooks ---------------------------------------

    def hideEvent(self, event) -> None:  # noqa: N802
        self._ring_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._running and not self._is_closing:
            self._ring_timer.start()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._is_closing = True
        self._ring_timer.stop()
        super().closeEvent(event)

    # -- Ring animation -----------------------------------------------------

    def _advance_ring(self) -> None:
        self._ring_angle = (self._ring_angle + _RING_STEP_DEG) % 360.0
        self.update()

    # -- Paint --------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw rounded-rect background
        painter.setPen(Qt.NoPen)
        painter.setBrush(_BG_COLOR)
        painter.drawRoundedRect(self.rect(), 10, 10)

        # Draw rotating ring when running
        if self._running and self._ring_timer.isActive():
            btn0 = self._buttons[0]
            center_x = btn0.x() + btn0.width() / 2.0
            center_y = btn0.y() + btn0.height() / 2.0

            pen = QPen(QColor(_ICON_COLOR_ACTIVE))
            pen.setWidthF(_RING_WIDTH)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            rect_size = _RING_RADIUS * 2
            ring_rect = (
                center_x - _RING_RADIUS,
                center_y - _RING_RADIUS,
                rect_size,
                rect_size,
            )
            painter.drawArc(
                QRectF(*ring_rect),
                int(self._ring_angle * 16),
                _RING_ARC_SPAN * 16,
            )

        painter.end()

    # -- Child event filtering for button drags -----------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched in self._buttons:
            etype = event.type()
            if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_origin = event.pos()
                self._drag_global_origin = event.globalPos()
                self._widget_origin = self.pos()
                self._dragging = False
                return False

            if etype == QEvent.MouseMove and self._drag_global_origin is not None:
                delta = event.globalPos() - self._drag_global_origin
                distance = max(abs(delta.x()), abs(delta.y()))
                threshold = max(QApplication.startDragDistance(), _MIN_DRAG_DISTANCE)
                if distance >= threshold:
                    self._dragging = True
                    if isinstance(watched, QPushButton):
                        watched.setDown(False)
                    self.move(self._widget_origin + delta)
                    return True

            if etype == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                if self._drag_global_origin is not None:
                    delta = event.globalPos() - self._drag_global_origin
                    distance = max(abs(delta.x()), abs(delta.y()))
                    threshold = max(QApplication.startDragDistance(), _MIN_DRAG_DISTANCE)
                    if distance >= threshold:
                        self._dragging = True
                        self.move(self._widget_origin + delta)

                if self._dragging:
                    if isinstance(watched, QPushButton):
                        watched.setDown(False)
                    self.position_released.emit(self.pos().x(), self.pos().y())
                    self._drag_origin = None
                    self._drag_global_origin = None
                    self._widget_origin = None
                    QTimer.singleShot(0, self._reset_dragging)
                    return True

                self._drag_origin = None
                self._drag_global_origin = None
                self._widget_origin = None
                return False

        return super().eventFilter(watched, event)

    # -- Mouse handling (drag vs click on toolbar itself) -------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.pos()
            self._drag_global_origin = event.globalPos()
            self._widget_origin = self.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_global_origin is not None and (event.buttons() & Qt.LeftButton or event.buttons() == Qt.NoButton):
            delta = event.globalPos() - self._drag_global_origin
            distance = max(abs(delta.x()), abs(delta.y()))
            threshold = max(QApplication.startDragDistance(), _MIN_DRAG_DISTANCE)
            if distance >= threshold:
                self._dragging = True
                new_pos = self._widget_origin + delta
                self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._drag_global_origin is not None:
            # Final drag-distance check (mouseMoveEvent may not fire in all
            # platform backends, e.g. offscreen, or when children consume moves)
            if not self._dragging:
                delta = event.globalPos() - self._drag_global_origin
                distance = max(abs(delta.x()), abs(delta.y()))
                threshold = max(QApplication.startDragDistance(), _MIN_DRAG_DISTANCE)
                if distance >= threshold:
                    self._dragging = True
                    new_pos = self._widget_origin + delta
                    self.move(new_pos)
            if self._dragging:
                # Emit final position — no clamping, negative coords preserved
                self.position_released.emit(self.pos().x(), self.pos().y())
            self._drag_origin = None
            self._drag_global_origin = None
            self._widget_origin = None
            # Reset _dragging after a processEvents cycle so button clicked
            # signals that fire synchronously during release are still suppressed.
            QTimer.singleShot(0, self._reset_dragging)
        super().mouseReleaseEvent(event)

    def _reset_dragging(self) -> None:
        self._dragging = False

    # -- Size hint ----------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802
        return super().sizeHint()
