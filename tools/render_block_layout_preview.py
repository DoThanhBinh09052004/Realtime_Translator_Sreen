"""Offline before/after block rendering on recorded game frames. No OCR or HTTP."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if os.name == 'nt':
    os.environ.setdefault('QT_QPA_FONTDIR', str(Path(os.environ.get('WINDIR', r'C:\Windows'))/'Fonts'))
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter, QColor, QFont, QFontInfo
from PyQt5.QtWidgets import QApplication
from core.blocks.models import Rect, ScreenMapping, CaptureGeometry, OverlayBlock, OverlayFrame
from core.blocks.geometry import overlay_window_rect
from ui.block_layout import layout_blocks, paint_blocks


def _save(image, path):
    if not image.save(str(path)):
        raise ValueError(f'Cannot save preview: {path}')
    return str(path.resolve())


def _paired(before, after):
    width, height = before.width(), before.height()
    result = QImage(width*2+16, height+38, QImage.Format_ARGB32_Premultiplied)
    result.fill(QColor('#171c24'))
    painter = QPainter(result)
    painter.setPen(QColor('white'))
    font = QFont('Segoe UI'); font.setPixelSize(15)
    painter.setFont(font)
    painter.drawText(8, 24, 'TRƯỚC · nền lấy hết khoảng trống')
    painter.drawText(width+24, 24, 'SAU · nền vừa đủ theo khối')
    painter.drawImage(0, 38, before)
    painter.drawImage(width+16, 38, after)
    painter.end()
    return result


def render_comparison(image: QImage, frame: OverlayFrame, *, baseline_layout,
                      max_font_px: int, out_dir: Path) -> dict:
    if image.isNull():
        raise ValueError('Cannot render an empty image')
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    result = {'blocks': {}}
    images = []
    window = overlay_window_rect(frame.geometry)
    for name, layout in (('before', baseline_layout), ('after', layout_blocks)):
        blocks = layout(frame, max_font_px=max_font_px)
        painted = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(painted)
        painter.scale(image.width()/window.width, image.height()/window.height)
        paint_blocks(painter, blocks, bg_color=QColor(30, 30, 46, 204), text_color=QColor('white'))
        painter.end()
        result[name] = _save(painted, out_dir/f'{name}.png')
        result['blocks'][name] = [asdict(block) for block in blocks]
        images.append(painted)
    result['comparison'] = _save(_paired(*images), out_dir/'comparison.png')
    return result


def _baseline(ref):
    if not ref or ref.startswith('-'):
        raise ValueError('Invalid baseline ref')
    commit = subprocess.run(['git', 'rev-parse', '--verify', ref+'^{commit}'], cwd=ROOT,
                            check=True, capture_output=True, text=True).stdout.strip()
    source = subprocess.run(['git', 'show', commit+':ui/block_layout.py'], cwd=ROOT,
                            check=True, capture_output=True).stdout.decode('utf-8')
    module = types.ModuleType('_compact_preview_baseline')
    sys.modules[module.__name__] = module
    exec(compile(source, f'{commit}:ui/block_layout.py', 'exec'), module.__dict__)
    return module.layout_blocks, commit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    cap = None
    try:
        if not args.video.is_file():
            raise ValueError(f'Video does not exist: {args.video}')
        import cv2
        cap = cv2.VideoCapture(str(args.video))
        if not cap.isOpened():
            raise ValueError(f'Cannot decode video: {args.video}')
        data = json.loads(args.fixture.read_text(encoding='utf-8'))
        baseline, commit = _baseline(args.baseline_ref)
        app = QApplication.instance() or QApplication([])
        results, panels = [], []
        for index, case in enumerate(data['frames']):
            cap.set(cv2.CAP_PROP_POS_MSEC, case['video_time_s']*1000)
            ok, pixels = cap.read()
            if not ok:
                raise ValueError(f'Cannot decode video at {case["video_time_s"]}s')
            h, w = pixels.shape[:2]
            x1, y1, x2, y2 = case['crop']
            size = tuple(case['image_size_px'])
            pixels = cv2.resize(pixels[int(h*y1):int(h*y2), int(w*x1):int(w*x2)], size)
            rgba = cv2.cvtColor(pixels, cv2.COLOR_BGR2RGBA)
            image = QImage(rgba.data, size[0], size[1], rgba.strides[0], QImage.Format_RGBA8888).copy()
            rect = Rect(0, 0, *size)
            geometry = CaptureGeometry(rect, ScreenMapping('video', rect, rect), size)
            blocks = tuple(OverlayBlock(b['block_id'], b['source_text'], b['translated_text'],
                                        Rect(**b['source_rect'])) for b in case['blocks'])
            result = render_comparison(image, OverlayFrame(1, index, geometry, blocks),
                                       baseline_layout=baseline, max_font_px=22, out_dir=args.out/f'frame-{index}')
            result.update(id=case['id'], video_time_s=case['video_time_s'])
            results.append(result); panels.append(QImage(result['comparison']))
        if not panels:
            raise ValueError('Fixture contains no frames')
        sheet = QImage(max(p.width() for p in panels), sum(p.height()+28 for p in panels),
                       QImage.Format_ARGB32_Premultiplied)
        sheet.fill(QColor('#171c24'))
        painter = QPainter(sheet); painter.setPen(QColor('white'))
        label_font = QFont('Segoe UI'); label_font.setPixelSize(14); painter.setFont(label_font)
        y = 0
        for case, panel in zip(data['frames'], panels):
            painter.drawText(8, y+20, f'{case["id"]} · {case["video_time_s"]:.3f}s')
            painter.drawImage(0, y+28, panel); y += panel.height()+28
        painter.end()
        comparison = _save(sheet, args.out/'comparison.png')
        metrics = dict(baseline_ref=commit, fixture=str(args.fixture), video=str(args.video),
                       font_family=QFontInfo(QFont('Segoe UI')).family(), frames=results,
                       method='real video crop + recorded OCR rectangles + fixed translations; offline Qt rendering')
        (args.out/'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'comparison': comparison, 'frames': len(results)}, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Preview error: {error}', file=sys.stderr)
        return 1
    finally:
        if cap is not None:
            cap.release()


if __name__ == '__main__':
    raise SystemExit(main())
