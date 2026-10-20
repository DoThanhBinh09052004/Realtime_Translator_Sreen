import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from ui.styles import CYBER_PALETTE, get_app_stylesheet

def test_pro_palette():
    assert CYBER_PALETTE["bg_main"] == "#0e0f12"
    assert CYBER_PALETTE["bg_sidebar"] == "#14151a"
    assert CYBER_PALETTE["bg_card"] == "#191a21"
    assert CYBER_PALETTE["border"] == "#23252e"
    sheet = get_app_stylesheet()
    assert "#0e0f12" in sheet
    print("[PASS] test_pro_styles passed")

if __name__ == "__main__":
    test_pro_palette()
