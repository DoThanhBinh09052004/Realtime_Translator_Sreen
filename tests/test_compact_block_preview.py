from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from PyQt5.QtGui import QImage, QColor
from core.blocks.models import OverlayFrame, OverlayBlock, Rect


def test_comparison_uses_actual_paint_and_preserves_uncovered_pixels(qapp, capture_geometry, tmp_path):
    from tools.render_block_layout_preview import render_comparison
    from ui.block_layout import layout_blocks
    frame = OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'Among the seven gods', 'Xin chào', Rect(20, 20, 320, 40)),))
    image = QImage(800, 600, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor('#446644'))
    def wide_baseline(frame, *, max_font_px):
        block, = layout_blocks(frame, max_font_px=max_font_px)
        return (replace(block, view_rect=Rect(20, 20, 780, 40)),)
    result = render_comparison(image, frame, baseline_layout=wide_baseline, max_font_px=22, out_dir=tmp_path)
    assert all(Path(result[name]).is_file() for name in ('before', 'after', 'comparison'))
    before, after = QImage(result['before']), QImage(result['after'])
    assert before.pixelColor(500, 40) != image.pixelColor(500, 40)
    assert after.pixelColor(500, 40) == image.pixelColor(500, 40)
    assert result['blocks']['before'][0]['view_rect']['width'] == 780
    assert result['blocks']['after'][0]['view_rect']['width'] == 320


def test_preview_cli_reports_missing_video_without_reading_settings(qapp, tmp_path, capsys):
    from tools.render_block_layout_preview import main
    fixture = Path(__file__).parent / 'fixtures/blocks/compact_game_dialogue.json'
    code = main(['--fixture', str(fixture), '--video', str(tmp_path/'missing.mp4'),
                 '--baseline-ref', '87d7bcd', '--out', str(tmp_path/'out')])
    assert code != 0
    assert 'video' in capsys.readouterr().err.lower()


def test_preview_rejects_nondecodable_video(tmp_path):
    video = tmp_path/'bad.mp4'
    video.write_bytes(b'not a video')
    fixture = Path(__file__).parent / 'fixtures/blocks/compact_game_dialogue.json'
    tool = Path(__file__).resolve().parents[1]/'tools/render_block_layout_preview.py'
    # Exercise the real CLI in its own process, as users run it. Keep native
    # codec plugin teardown outside the test runner's long-lived Qt instance.
    result = subprocess.run([sys.executable, str(tool), '--fixture', str(fixture),
                             '--video', str(video), '--baseline-ref', '87d7bcd',
                             '--out', str(tmp_path/'out')], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'video' in result.stderr.lower()
