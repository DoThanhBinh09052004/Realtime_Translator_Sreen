import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from ui.styles import CYBER_PALETTE, get_app_stylesheet

def test_styles():
    assert "bg_primary" in CYBER_PALETTE
    assert "neon_green" in CYBER_PALETTE
    assert "neon_rose" in CYBER_PALETTE
    sheet = get_app_stylesheet()
    assert isinstance(sheet, str)
    assert len(sheet) > 50
    print("[PASS] test_styles passed")

if __name__ == "__main__":
    test_styles()
