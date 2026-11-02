"""Isolated WGC feasibility probe. Only captures the two Qt windows it creates.

This is diagnostic tooling, not an application capture adapter. JSON contains
measurements only; images require --save-images. Native imports are lazy.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import threading
import time
import traceback


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    def duration(value):
        number = float(value)
        if not math.isfinite(number) or not 6 <= number <= 300:
            raise argparse.ArgumentTypeError("seconds must be finite and between 6 and 300")
        return number

    parser.add_argument("--seconds", type=duration, default=10.0)
    parser.add_argument("--output", type=Path, default=Path("scratch/window-capture-probe.json"))
    parser.add_argument("--save-images", action="store_true", help="save one owned-window PNG per HWND")
    args = parser.parse_args(argv)
    if args.output.is_dir() or not args.output.name or args.output.suffix.lower() != ".json":
        parser.error("output must be a JSON file path, not a directory")
    if any(parent.exists() and not parent.is_dir() for parent in args.output.parents):
        parser.error("output parent must be a directory")
    return args


def crop_client(frame, capture_bounds, client_bounds):
    """Crop using measured physical rectangles; never guess/scale a border."""
    if frame.ndim != 3 or frame.shape[2] != 4 or str(frame.dtype) != "uint8":
        raise ValueError("Only BGRA8 frames are supported")
    left, top, right, bottom = capture_bounds
    if frame.shape[:2] != (bottom - top, right - left):
        raise ValueError("Frame size does not match measured DWM capture bounds")
    x, y, end_x, end_y = client_bounds
    if not (left <= x < end_x <= right and top <= y < end_y <= bottom):
        raise ValueError("Client is outside measured capture surface")
    return frame[y - top:end_y - top, x - left:end_x - left]


def _native_probe(seconds, report, save_images, output):
    import ctypes
    from ctypes import wintypes
    from importlib.metadata import version
    import numpy as np
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QColor, QPainter
    from PyQt5.QtWidgets import QApplication, QWidget
    from windows_capture import WindowsCapture

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    def bounds(hwnd):
        rect = wintypes.RECT()
        if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)):
            raise OSError("DwmGetWindowAttribute(EXTENDED_FRAME_BOUNDS) failed")
        capture = (rect.left, rect.top, rect.right, rect.bottom)
        client = wintypes.RECT()
        origin = wintypes.POINT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise ctypes.WinError(ctypes.get_last_error())
        return capture, (origin.x, origin.y, origin.x + client.right, origin.y + client.bottom)

    if QApplication.instance() is not None:
        raise RuntimeError("Probe must run in its own process")
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication([])
    if app.platformName().lower() != "windows":
        raise RuntimeError(f"Native Windows desktop unavailable: Qt platform={app.platformName()!r}")
    app.setQuitOnLastWindowClosed(False)
    report["runtime"].update(windows_capture=version("windows-capture"), numpy=np.__version__, qt_platform=app.platformName())
    colors = [(32, 64, 224), (48, 208, 64), (224, 96, 32), (192, 48, 176)]

    class PatternWindow(QWidget):
        def __init__(self, identity):
            super().__init__()
            self.identity = identity
            self.tick = 0
            self.setAttribute(Qt.WA_DeleteOnClose)
            self.setWindowTitle("WGC probe — duplicate title")
            self.resize(320, 220)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(24, 28, 36))
            for (x, y), (b, g, r) in zip([(0, 0), (self.width()-20, 0), (0, self.height()-20), (self.width()-20, self.height()-20)], colors):
                painter.fillRect(x, y, 20, 20, QColor(r, g, b))
            painter.fillRect(self.width()//2-12, self.height()//2-12, 24, 24, QColor(70 + self.identity*100, 110, 210))
            painter.fillRect(32, 32, 30, 30, QColor(self.tick % 200 + 20, 120, 70))

    windows = [PatternWindow(0), PatternWindow(1)]
    screen = app.primaryScreen().availableGeometry()
    for index, window in enumerate(windows):
        window.move(screen.x() + 40 + index*380, screen.y() + 80)
        window.show()
    app.processEvents()
    hwnds = [int(window.winId()) for window in windows]
    if len(set(hwnds)) != 2 or not all(user32.IsWindow(hwnd) for hwnd in hwnds):
        raise RuntimeError("Unable to create two distinct native Qt HWNDs")
    report["owned_hwnds"] = hwnds
    lock = threading.Lock()
    phase = ["initial"]
    captures = []
    controls = []
    records = [dict(hwnd=hwnd, callbacks=0, processed=0, samples=[], errors=[], closed=False, callback_thread_ids=[]) for hwnd in hwnds]
    report["windows"] = records
    stop_requested = threading.Event()
    drained = threading.Event()
    start = time.perf_counter()
    gui_thread = threading.get_ident()
    report["gui_thread_id"] = gui_thread

    def make_capture(index):
        record = records[index]
        last_sample = [0.0]
        capture = WindowsCapture(window_hwnd=hwnds[index], cursor_capture=False, draw_border=False, minimum_update_interval=100)

        @capture.event
        def on_frame_arrived(frame, internal_control):
            now = time.perf_counter()
            with lock:
                record["callbacks"] += 1
                tid = threading.get_ident()
                if tid not in record["callback_thread_ids"]:
                    record["callback_thread_ids"].append(tid)
                if now - last_sample[0] < .1:
                    return
                last_sample[0] = now
                current_phase = phase[0]
            if user32.IsIconic(hwnds[index]):
                return
            try:
                pixels = frame.frame_buffer
                capture_rect, client_rect = bounds(hwnds[index])
                client = crop_client(pixels, capture_rect, client_rect)
                height, width = client.shape[:2]
                points = [(5, 5), (width-6, 5), (5, height-6), (width-6, height-6)]
                marker_ok = all(np.max(np.abs(client[y, x, :3].astype(int) - color)) <= 2 for (x, y), color in zip(points, colors))
                expected_identity = np.array([210, 110, 70 + index*100])
                identity_ok = bool(np.max(np.abs(client[height//2, width//2, :3].astype(int) - expected_identity)) <= 2)
                sample = dict(elapsed_s=round(now-start, 4), phase=current_phase, timespan=frame.timespan,
                              shape=list(pixels.shape), strides=list(pixels.strides), dtype=str(pixels.dtype),
                              capture_bounds=list(capture_rect), client_bounds=list(client_rect),
                              client_offset=[client_rect[0]-capture_rect[0], client_rect[1]-capture_rect[1]],
                              marker_ok=bool(marker_ok), identity_ok=identity_ok,
                              tick_rgb=client[40, 40, :3].tolist())
                with lock:
                    record["processed"] += 1
                    record["samples"].append(sample)
                if save_images and not record.get("image") and marker_ok and identity_ok:
                    import cv2
                    path = output.with_name(f"{output.stem}-{index}.png")
                    if not cv2.imwrite(str(path), client):
                        raise OSError(f"Could not save {path}")
                    record["image"] = str(path)
            except Exception as exc:
                with lock:
                    if len(record["errors"]) < 30:
                        record["errors"].append(dict(phase=current_phase, elapsed_s=round(now-start, 4), error=f"{type(exc).__name__}: {exc}"))

        @capture.event
        def on_closed():
            record["closed"] = True
            record["closed_elapsed_s"] = round(time.perf_counter()-start, 4)

        return capture

    def capture_owner():
        report["owner_thread_id"] = threading.get_ident()
        try:
            for index in range(2):
                capture = make_capture(index)
                captures.append(capture)
                controls.append(capture.start_free_threaded())
            report["native_started_s"] = round(time.perf_counter()-start, 4)
            stop_requested.wait()
        except Exception as exc:
            report["native_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            before = time.perf_counter()
            report["stop_thread_id"] = threading.get_ident()
            for control in controls:
                try:
                    control.stop()
                    control.wait()
                except Exception as exc:
                    report.setdefault("stop_errors", []).append(f"{type(exc).__name__}: {exc}")
            report["drain_s"] = round(time.perf_counter()-before, 6)
            drained.set()

    owner = threading.Thread(target=capture_owner, name="probe-native-owner", daemon=True)
    owner.start()
    events_done = set()
    heartbeat = []
    stop_time = [None]

    def transition(label, action):
        if label in events_done:
            return
        with lock:
            phase[0] = label
        action()
        events_done.add(label)
        report.setdefault("transitions", []).append(dict(phase=label, elapsed_s=round(time.perf_counter()-start, 4)))

    def tick():
        now = time.perf_counter()
        elapsed = now-start
        heartbeat.append(now)
        fraction = elapsed / seconds
        if fraction >= .15:
            transition("renamed", lambda: [window.setWindowTitle(f"WGC renamed {index}") for index, window in enumerate(windows)])
        if fraction >= .25:
            transition("moved", lambda: [window.move(window.x()+32, window.y()+36) for window in windows])
        if fraction >= .4:
            transition("resized", lambda: [window.resize(360, 250) for window in windows])
        if fraction >= .55:
            transition("minimized", lambda: [window.showMinimized() for window in windows])
        if fraction >= .65:
            transition("restored", lambda: [window.showNormal() for window in windows])
        if fraction >= .8:
            transition("static", lambda: None)
        if fraction >= .9:
            transition("closed_second", windows[1].close)
        if fraction < .8 and phase[0] != "minimized":
            for window in windows:
                window.tick += 7
                window.update()
        if elapsed >= seconds and stop_time[0] is None:
            stop_time[0] = now
            stop_requested.set()
        if stop_time[0] is not None and (drained.is_set() or now-stop_time[0] >= 3):
            report["drain_completed"] = drained.is_set()
            timer.stop()
            app.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(100)
    app.exec_()
    stop_requested.set()
    for window, hwnd in zip(windows, hwnds):
        if user32.IsWindow(hwnd):
            window.close()
    report["gui_heartbeat_max_gap_s"] = round(max((b-a for a, b in zip(heartbeat, heartbeat[1:])), default=0), 6)
    # A static surface is allowed to stop producing callbacks. It must not be
    # mistaken for lost capture; record its observed callback count separately.
    required_phases = {"initial", "renamed", "moved", "resized", "restored"}
    with lock:
        for record in records:
            samples = list(record["samples"])
            good = [sample for sample in samples if sample["marker_ok"] and sample["identity_ok"]]
            record["passed_phases"] = sorted({sample["phase"] for sample in good})
            record["first_frame_s"] = samples[0]["elapsed_s"] if samples else None
            record["mapping_pass"] = required_phases <= set(record["passed_phases"])
            record["static_samples"] = sum(sample["phase"] == "static" for sample in samples)
            before_minimize = [sample["timespan"] for sample in good if sample["phase"] == "resized"]
            after_restore = [sample["timespan"] for sample in good if sample["phase"] == "restored"]
            record["restore_fresh"] = bool(before_minimize and after_restore and min(after_restore) > max(before_minimize))
    checks = dict(
        distinct_hwnds=len(set(hwnds)) == 2,
        both_hwnd_marker_mapping=all(record["mapping_pass"] for record in records),
        fresh_frame_after_restore=all(record["restore_fresh"] for record in records),
        opening_within_2s=all(record["first_frame_s"] is not None and record["first_frame_s"] <= 2 for record in records),
        callback_off_gui=all(record["callback_thread_ids"] and gui_thread not in record["callback_thread_ids"] for record in records),
        stop_off_gui=report.get("stop_thread_id") != gui_thread,
        bounded_drain=len(controls) == 2 and report.get("drain_completed", False) and report.get("drain_s", 4) <= 3,
        close_notification=records[1]["closed"],
        gui_responsive=report["gui_heartbeat_max_gap_s"] < .5,
        no_native_error="native_error" not in report and not report.get("stop_errors"),
    )
    report["checks"] = checks
    report["pass"] = all(checks.values())


def run_probe(*, seconds: float, output: Path, save_images: bool = False) -> int:
    """Write native evidence JSON; return 0 only when every native gate passes."""
    if not math.isfinite(seconds) or not 6 <= seconds <= 300:
        raise ValueError("seconds must be finite and between 6 and 300")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(pass_=False, runtime=dict(python=sys.version, platform=sys.platform, executable=sys.executable),
                  seconds=seconds, images_saved=save_images, checks={}, limitations=[
                      "Owned Qt SDR test windows only; no game, HDR, protected content, negative-origin or mixed-DPI qualification.",
                      "This probe is feasibility evidence, not the production capture adapter.",
                  ])
    report.pop("pass_")
    report["pass"] = False
    started = time.perf_counter()
    try:
        if sys.platform != "win32" or sys.maxsize <= 2**32:
            raise RuntimeError("Windows x64 is required")
        if sys.getwindowsversion().build < 19041:
            raise RuntimeError("Windows build 19041 or newer is required")
        _native_probe(seconds, report, save_images, output)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
    report["elapsed_s"] = round(time.perf_counter()-started, 6)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(dict(output=str(output.resolve()), passed=report["pass"], error=report.get("error"), native_error=report.get("native_error"))))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(run_probe(seconds=args.seconds, output=args.output, save_images=args.save_images))
