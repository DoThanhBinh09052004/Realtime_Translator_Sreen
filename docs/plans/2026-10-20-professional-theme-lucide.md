# Professional Theme (Linear / Raycast Pro) & Lucide Icons Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Upgrade the application's visual aesthetics to a modern, professional developer style (Linear / Raycast Pro) and replace all emoji icons with authentic, crisp vector Lucide SVG icons rendered via `PyQt5.QtSvg`.

**Architecture:** Create `ui/icons.py` containing clean SVG definitions of selected Lucide icons rendered dynamically with `QSvgRenderer` into `QIcon` objects with configurable colors and sizes. Update `ui/styles.py` to Linear Pro tokens (`#0e0f12`, `#14151a`, `#191a21`, `#23252e`, `#282a36`). Refactor `ui/controller.py` to use Lucide icons across the sidebar navigation, hero buttons, metrics cards, and inputs.

**Tech Stack:** Python 3, PyQt5 (QWidget, QtSvg, QSvgRenderer, QIcon, QPixmap, QPainter, QSS).

---

### Task 1: Create Vector Lucide Icon Provider (`ui/icons.py`)

**Files:**
- Create: `ui/icons.py`
- Test: `scratch/test_lucide_icons.py`

**Step 1: Write test for Lucide icon generator**
Verify `get_lucide_icon(name, color, size)` returns a valid non-null `QIcon` for all required icons: `zap`, `layout-dashboard`, `bot`, `languages`, `palette`, `play`, `square`, `scan`, `sliders`, `eye`, `eye-off`, `check-circle`, `alert-circle`, `log-out`, `activity`, `maximize-2`.

```python
# scratch/test_lucide_icons.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from ui.icons import get_lucide_icon, LUCIDE_ICONS

app = QApplication.instance() or QApplication(sys.argv)

def test_icons():
    assert len(LUCIDE_ICONS) >= 12
    for name in ["zap", "layout-dashboard", "bot", "languages", "palette", "play", "square", "scan", "eye", "log-out"]:
        icon = get_lucide_icon(name, color="#6366f1", size=20)
        assert not icon.isNull(), f"Icon {name} is null"
    print("[PASS] test_lucide_icons passed")

if __name__ == "__main__":
    test_icons()
```

**Step 2: Run test to verify it fails**
Run: `python scratch/test_lucide_icons.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'ui.icons'`)

**Step 3: Implement `ui/icons.py`**
Implement the Lucide SVG definitions and `get_lucide_icon` function.

**Step 4: Run test to verify it passes**
Run: `python scratch/test_lucide_icons.py`
Expected: PASS (`[PASS] test_lucide_icons passed`)

**Step 5: Commit**
```bash
git add ui/icons.py scratch/test_lucide_icons.py
git commit -m "feat(ui): add vector lucide svg icon provider"
```

---

### Task 2: Update Design Tokens to Linear / Raycast Pro (`ui/styles.py`)

**Files:**
- Modify: `ui/styles.py`
- Test: `scratch/test_pro_styles.py`

**Step 1: Write test for professional style tokens**
Verify tokens match Linear Pro palette (`#0e0f12`, `#14151a`, `#191a21`, `#23252e`, `#282a36`).

```python
# scratch/test_pro_styles.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from ui.styles import CYBER_PALETTE, get_app_stylesheet

def test_pro_palette():
    assert CYBER_PALETTE["bg_main"] == "#0e0f12"
    assert CYBER_PALETTE["bg_sidebar"] == "#14151a"
    assert CYBER_PALETTE["bg_card"] == "#191a21"
    sheet = get_app_stylesheet()
    assert "#0e0f12" in sheet
    print("[PASS] test_pro_styles passed")

if __name__ == "__main__":
    test_pro_palette()
```

**Step 2: Run test to verify it fails on old palette**
Run: `python scratch/test_pro_styles.py`

**Step 3: Update `ui/styles.py`**
Apply the Linear / Raycast Pro design tokens, refined 1px borders, subtle button states, and clean inputs.

**Step 4: Run test to verify it passes**
Run: `python scratch/test_pro_styles.py`
Expected: PASS

**Step 5: Commit**
```bash
git add ui/styles.py scratch/test_pro_styles.py
git commit -m "feat(ui): upgrade design tokens to linear pro dark palette"
```

---

### Task 3: Integrate Lucide Icons & Professional Theme into `ui/controller.py`

**Files:**
- Modify: `ui/controller.py`
- Test: `scratch/test_controller_icons.py`

**Step 1: Write test for Lucide icon integration in ControllerWindow**
Verify nav buttons have icons and no unicode emojis remain in labels or button texts.

```python
# scratch/test_controller_icons.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
c = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None)

for btn in c.nav_buttons:
    assert not btn.icon().isNull(), f"Nav button {btn.text()} missing Lucide icon"
    assert not any(ord(char) > 10000 for char in btn.text()), f"Emoji still found in {btn.text()}"

assert not c.start_btn.icon().isNull(), "start_btn missing icon"
assert not c.stop_btn.icon().isNull(), "stop_btn missing icon"
print("[PASS] test_controller_icons passed")
```

**Step 2: Run test to verify failure**
Run: `python scratch/test_controller_icons.py`

**Step 3: Update `ui/controller.py`**
- Replace all unicode emojis with `get_lucide_icon(...)`.
- Set icons with proper sizes (`QSize(16, 16)`, `QSize(18, 18)`).
- Update button texts cleanly (e.g. "Tổng quan", "Cấu hình AI", "Dịch thuật & OCR", "Giao diện Phụ đề", "Bắt đầu", "Dừng").
- Update Metric cards to use Lucide vector icons instead of unicode emojis.
- Update eye toggle to use `eye` and `eye-off` Lucide icons.

**Step 4: Run test to verify it passes**
Run: `python scratch/test_controller_icons.py`
Expected: PASS

**Step 5: Commit**
```bash
git add ui/controller.py scratch/test_controller_icons.py
git commit -m "feat(ui): integrate lucide vector icons into dashboard controller"
```

---

### Task 4: Harmonize `main.py` Fusion Palette with Linear Pro

**Files:**
- Modify: `main.py`

**Step 1: Verify `setup_dark_theme` references `CYBER_PALETTE`**
Ensure native dialogs and window elements use the new `#0e0f12` and `#14151a` dark theme.

**Step 2: Verify `main.py` imports cleanly**
Run: `python -c "import main; print('[PASS]')"`

**Step 3: Commit**
```bash
git add main.py
git commit -m "feat(ui): harmonize main window palette with linear pro theme"
```

---

### Task 5: End-to-End Verification & Quality Review

**Files:**
- Test: `scratch/test_full_ui.py`
- Modify: `docs/plans/task.md`

**Step 1: Run complete test suite**
Run:
- `python scratch/test_lucide_icons.py`
- `python scratch/test_pro_styles.py`
- `python scratch/test_controller_icons.py`
- `python scratch/test_full_ui.py`

**Step 2: Verify zero regressions & visually inspect rendering**

**Step 3: Update `docs/plans/task.md` & Commit**
```bash
git add docs/plans/task.md
git commit -m "chore: mark linear pro and lucide icon redesign completed"
```
