import sys
import json
import numpy as np
import mss
import gc  
import cv2 


from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPalette, QColor

from select_region import RegionSelector
from ocr_engine import ocr_image
from translator import translate
from overlay import Overlay
from controller import ControllerWindow


# ===== STATE =====
class State:
    def __init__(self):
        self.source = "English"  # Default Eng
        self.target = "Vietnamese"  # Luôn Viet

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ===== MASK OVERLAY KHỎI OCR =====
def mask_overlay(img, overlay, region):
    if not overlay.isVisible():
        return img

    geo = overlay.geometry()
    ox, oy = geo.x(), geo.y()
    ow, oh = geo.width(), geo.height()

    rx, ry = region["left"], region["top"]

    x1 = max(0, ox - rx)
    y1 = max(0, oy - ry)
    x2 = min(img.shape[1], x1 + ow)
    y2 = min(img.shape[0], y1 + oh)

    if x1 < x2 and y1 < y2:
        img[y1:y2, x1:x2] = 0

    return img


# ===== LOAD REGION =====
def load_region():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("region")
    except Exception:
        pass

    return {
        "top": 0,
        "left": 0,
        "width": 800,
        "height": 600
    }


# ===== MAIN =====
def main():
    app = QApplication(sys.argv)

    # ===== DARK THEME =====
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 46))
    palette.setColor(QPalette.WindowText, QColor(205, 214, 244))
    palette.setColor(QPalette.Base, QColor(46, 46, 68))
    palette.setColor(QPalette.Text, QColor(205, 214, 244))
    palette.setColor(QPalette.Button, QColor(69, 71, 90))
    palette.setColor(QPalette.ButtonText, QColor(205, 214, 244))
    palette.setColor(QPalette.Highlight, QColor(88, 91, 112))
    palette.setColor(QPalette.HighlightedText, QColor(205, 214, 244))
    app.setPalette(palette)

    # ===== STATE & REGION =====
    state = State()
    region = load_region()

    # ===== OVERLAY =====
    overlay = Overlay()
    overlay.show()

    # ===== SCREEN CAPTURE =====
    sct = mss.mss()
    prev_text = ""

    # ===== TIMER =====
    timer = QTimer()
    timer.setInterval(500)  

    def capture_and_process():
        nonlocal prev_text, region

        # Chụp màn hình (không dùng with cho grab, vì không cần)
        monitor = {"top": region["top"], "left": region["left"], "width": region["width"], "height": region["height"]}
        img_raw = sct.grab(monitor)  # ← Chỉ cần gọi grab bình thường
        img = np.array(img_raw)
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # Chuyển grayscale để tiết kiệm RAM

        img_gray = mask_overlay(img_gray, overlay, region)

        # Map ngôn ngữ OCR
        ocr_lang = 'en'
        if state.source == 'Japanese':
            ocr_lang = 'japan'

        text = ocr_image(img_gray, lang=ocr_lang).strip()
        del img_gray  # Giải phóng ngay
        del img       # Giải phóng thêm array gốc
        del img_raw   # Giải phóng ScreenShot object (mss khuyến nghị)

        if not text:
            gc.collect()
            return

        if text != prev_text:
            translated = translate(
                text,
                source_lang=state.source,
                target_lang=state.target
            )
            overlay.update_text(translated)
            prev_text = text
        else:
            overlay.refresh()

        gc.collect()  # Thu gom rác sau mỗi lần
    timer.timeout.connect(capture_and_process)

    # ===== CONTROLLER =====
    controller = None
    selector = None   # <<< GIỮ REFERENCE (RẤT QUAN TRỌNG)

    def on_select_region():
        nonlocal region, selector

        # 1. Ẩn UI đang chiếm focus
        controller.hide()
        overlay.hide()

        # 2. Tạo selector (GIỮ REFERENCE)
        selector = RegionSelector()
        selector.show()
        selector.raise_()
        selector.activateWindow()

        def on_region_selected(new_region):
            nonlocal region
            region = new_region

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump({"region": region}, f, ensure_ascii=False, indent=2)

            # 3. Hiện lại UI
            controller.show()
            overlay.show()

        selector.region_selected.connect(on_region_selected)

    def on_quit():
        timer.stop()
        overlay.close()
        app.quit()

    controller = ControllerWindow(
        timer=timer,
        state=state,
        on_select_region=on_select_region,
        on_quit=on_quit
    )
    controller.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()