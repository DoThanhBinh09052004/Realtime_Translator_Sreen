from types import SimpleNamespace
from unittest.mock import Mock
from PyQt5.QtCore import QObject
import pytest

from core.blocks.models import CaptureGeometry, OverlayBlock, OverlayFrame, Rect, ScreenMapping
from core.contracts import SubtitleFrame
from test_capture_app_integration import capture_values
from ui.controller_state import PresentedTranslation, PresentedPair
from ui.overlay import Overlay
from ui.block_overlay import BlockOverlay


def test_subtitle_source_matches_presented_translation(qtbot):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    presented = []
    overlay.translation_presented.connect(presented.append)

    frame = SubtitleFrame(
        revision=0,
        candidate_id=1,
        source_text="Hello world",
        text="Xin chào thế giới",
        render_sequence=1,
    )
    overlay.update_subtitle(frame)

    assert len(presented) == 1
    p = presented[0]
    assert p.mode == "subtitle"
    assert len(p.pairs) == 1
    assert p.pairs[0].source_text == "Hello world"
    assert p.pairs[0].translated_text == "Xin chào thế giới"


def test_stale_sequence_emits_nothing(qtbot):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    presented = []
    overlay.translation_presented.connect(presented.append)

    frame1 = SubtitleFrame(revision=0, candidate_id=1, source_text="First", text="Thứ nhất", render_sequence=2)
    overlay.update_subtitle(frame1)
    assert len(presented) == 1

    # Stale render sequence
    frame2 = SubtitleFrame(revision=0, candidate_id=2, source_text="Old", text="Cũ", render_sequence=1)
    overlay.update_subtitle(frame2)
    assert len(presented) == 1


def test_held_subtitle_retains_original_pair(qtbot):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    presented = []
    overlay.translation_presented.connect(presented.append)

    frame = SubtitleFrame(revision=0, candidate_id=1, source_text="Held text", text="Chữ giữ nguyên", render_sequence=1)
    overlay.update_subtitle(frame)
    assert len(presented) == 1
    assert presented[0].pairs[0].source_text == "Held text"

    # Refreshing or holding subtitle without new sequence
    overlay.refresh()
    assert len(presented) == 1


def test_block_protection_failure_never_reports_success(qtbot, monkeypatch, capture_geometry):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    overlay.set_mode("blocks", 0)
    presented = []
    overlay.translation_presented.connect(presented.append)

    # Force protection failure
    monkeypatch.setattr(overlay.block_overlay, "_protect", lambda: False)

    block = OverlayBlock(1, "Source", "Dịch", Rect(10, 10, 50, 20), region_id="r1")
    frame = OverlayFrame(0, 1, capture_geometry, (block,))

    success = overlay.block_overlay.set_frame(frame)
    assert success is False
    # Must never report success presentation
    assert not any(p.pairs for p in presented)


def test_empty_or_invalidated_frame_clears_output(qtbot, capture_geometry):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    presented = []
    overlay.translation_presented.connect(presented.append)

    frame = SubtitleFrame(revision=0, candidate_id=1, source_text="Some", text="Một vài", render_sequence=1)
    overlay.update_subtitle(frame)
    assert len(presented) == 1
    assert len(presented[0].pairs) == 1

    overlay.clear()
    assert len(presented) == 2
    assert presented[1].pairs == ()


def test_multi_region_pairs_keep_region_id_and_reading_order(qtbot, monkeypatch, capture_geometry):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    overlay.set_mode("blocks", 0)
    presented = []
    overlay.translation_presented.connect(presented.append)

    import ui.block_overlay as block_mod
    monkeypatch.setattr(block_mod, "set_capture_excluded", lambda *args: None)

    # Two regions, unordered blocks in geometry
    b1_regA = OverlayBlock(1, "Top A", "Dịch A1", Rect(10, 20, 50, 20), region_id="reg_A")
    b2_regA = OverlayBlock(2, "Bottom A", "Dịch A2", Rect(10, 80, 50, 20), region_id="reg_A")
    b1_regB = OverlayBlock(3, "Top B", "Dịch B1", Rect(200, 10, 50, 20), region_id="reg_B")

    frame = OverlayFrame(0, 1, capture_geometry, (b2_regA, b1_regA, b1_regB))
    overlay.update_blocks(frame)

    assert len(presented) >= 1
    last_p = presented[-1]
    assert len(last_p.pairs) == 3
    # reg_A came first, sorted by y: b1_regA (y=20), b2_regA (y=80), then reg_B b1_regB
    assert last_p.pairs[0].region_id == "reg_A" and last_p.pairs[0].source_text == "Top A"
    assert last_p.pairs[1].region_id == "reg_A" and last_p.pairs[1].source_text == "Bottom A"
    assert last_p.pairs[2].region_id == "reg_B" and last_p.pairs[2].source_text == "Top B"


def test_style_repaint_does_not_duplicate_output(qtbot):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    presented = []
    overlay.translation_presented.connect(presented.append)

    frame = SubtitleFrame(revision=0, candidate_id=1, source_text="Source", text="Dịch", render_sequence=1)
    overlay.update_subtitle(frame)
    assert len(presented) == 1

    overlay.apply_style(font_size=28)
    assert len(presented) == 1
