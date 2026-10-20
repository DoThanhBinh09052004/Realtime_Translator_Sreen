# Modern Cyber Dark Controller UI Redesign Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Redesign the PyQt5 `ControllerWindow` into a sleek, modern Split-View Cyber Dark Dashboard with Sidebar navigation, status metric cards, hero action buttons, and a real-time Subtitle Live Preview box.

**Architecture:** Refactor `ui/controller.py` into a modern split layout (Fixed Left Sidebar + Right `QStackedWidget` multi-page view). The 4 pages will be: 🕹️ Console (Overview & Action Hub), 🤖 AI Engine (Provider, Model, Key), 🌐 Translation & OCR (Languages, Interval, Region info), and 🎨 Subtitle Style (Color pickers, Opacity slider, and Live Subtitle Preview). All underlying signals to `TranslationWorker`, `Overlay`, and configuration helpers remain 100% compatible.

**Tech Stack:** Python 3, PyQt5 (QWidget, QStackedWidget, QScrollArea, QFrame, QPushButton, QComboBox, QSlider, QSS).

---

### Task 1: Design Tokens & Reusable UI Components

**Files:**
- Create: `ui/styles.py`
- Test: `scratch/test_styles.py`

**Step 1: Write verification test for design tokens and components**
Verify `CYBER_THEME` dictionary and helper stylesheet generators exist and return valid QSS strings.

```python
# scratch/test_styles.py
from ui.styles import CYBER_PALETTE, get_app_stylesheet

def test_styles():
    assert "bg_primary" in CYBER_PALETTE
    assert "neon_green" in CYBER_PALETTE
    assert "neon_rose" in CYBER_PALETTE
    sheet = get_app_stylesheet()
    assert isinstance(sheet, str)
    assert len(sheet) > 50
    print("✅ test_styles passed")

if __name__ == "__main__":
    test_styles()
```

**Step 2: Run test to verify it fails**
Run: `python scratch/test_styles.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'ui.styles'`)

**Step 3: Implement `ui/styles.py`**
Implement the color palette, QSS style definitions for Window, Sidebar, Nav buttons, Card frames, Inputs, Combos, Sliders, and Scrollbars.

**Step 4: Run test to verify it passes**
Run: `python scratch/test_styles.py`
Expected: PASS (`✅ test_styles passed`)

**Step 5: Commit**
```bash
git add ui/styles.py scratch/test_styles.py
git commit -m "feat(ui): add modern cyber dark design tokens and stylesheet helper"
```

---

### Task 2: Implement Sidebar Navigation & Core Controller Layout

**Files:**
- Modify: `ui/controller.py`
- Test: `scratch/test_layout.py`

**Step 1: Write test for Split View controller layout**
Verify `ControllerWindow` initializes with Left Sidebar (Logo, 4 Nav Buttons, Status indicator, Quit) and a `QStackedWidget` with 4 page slots.

```python
# scratch/test_layout.py
import sys
from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
controller = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None)
assert controller.pages.count() == 4
assert controller.sidebar is not None
print("✅ test_layout passed")
```

**Step 2: Run test to verify failure/status**
Run: `python scratch/test_layout.py`

**Step 3: Refactor `ControllerWindow` structure in `ui/controller.py`**
Implement Split View layout:
- Left Sidebar (~190px) with app brand `⚡ TRANSLATE HUD`, 4 Nav Buttons (`Console`, `AI Engine`, `Dịch & OCR`, `Giao diện Phụ đề`), live status badge, and Quit button.
- Right `QStackedWidget` with page containers and smooth tab switching signal.

**Step 4: Run test to verify it passes**
Run: `python scratch/test_layout.py`
Expected: PASS

**Step 5: Commit**
```bash
git add ui/controller.py scratch/test_layout.py
git commit -m "feat(ui): implement split view sidebar layout and navigation stack"
```

---

### Task 3: Implement Page 1 (Console) and Page 2 (AI Engine)

**Files:**
- Modify: `ui/controller.py`
- Test: `scratch/test_pages_1_2.py`

**Step 1: Write verification test for Console & AI Engine pages**
Check existence of START / STOP buttons, 4 status metric cards, provider dropdown, model dropdown, and API key input with toggle.

```python
# scratch/test_pages_1_2.py
import sys
from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
c = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None)

# Verify Page 1 elements
assert hasattr(c, "start_btn")
assert hasattr(c, "stop_btn")
assert hasattr(c, "metric_cards")

# Verify Page 2 elements
assert hasattr(c, "provider_combo")
assert hasattr(c, "model_combo")
assert hasattr(c, "api_key_input")
print("✅ test_pages_1_2 passed")
```

**Step 2: Run test to verify failure**
Run: `python scratch/test_pages_1_2.py`

**Step 3: Implement Page 1 & Page 2**
- Page 1 (Console): Hero Start/Stop button row, 4 Quick Status cards (Status, Provider/Model, Languages, OCR Region), Quick Region Select button.
- Page 2 (AI Engine): Provider combobox, Model combobox, Password/Show API key input, .env status indicator, validation logic that redirects to Page 2 if API key is missing when START is clicked.

**Step 4: Run test to verify it passes**
Run: `python scratch/test_pages_1_2.py`
Expected: PASS

**Step 5: Commit**
```bash
git add ui/controller.py scratch/test_pages_1_2.py
git commit -m "feat(ui): build console action hub and ai engine configuration pages"
```

---

### Task 4: Implement Page 3 (Translation & OCR) and Page 4 (Subtitle Style & Live Preview)

**Files:**
- Modify: `ui/controller.py`
- Test: `scratch/test_pages_3_4.py`

**Step 1: Write test for Translation/OCR and Subtitle Style with Live Preview**
Verify Language combos, Interval spinbox, Color pickers, Opacity slider, and `subtitle_preview_box` exist and update properly.

```python
# scratch/test_pages_3_4.py
import sys
from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
c = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None)

# Verify Page 3
assert hasattr(c, "src_combo")
assert hasattr(c, "tgt_combo")
assert hasattr(c, "interval_spin")

# Verify Page 4 & Live Preview
assert hasattr(c, "live_preview_box")
assert hasattr(c, "opacity_slider")
print("✅ test_pages_3_4 passed")
```

**Step 2: Run test to verify failure**
Run: `python scratch/test_pages_3_4.py`

**Step 3: Implement Page 3 & Page 4**
- Page 3: Source and Target language dropdowns, OCR interval spinbox with helper note, region dimension summary card.
- Page 4: Background & Text color dialog buttons with live swatch badges, opacity slider, and the **Live Preview Box** displaying simulated subtitle text matching current styling in real time.

**Step 4: Run test to verify it passes**
Run: `python scratch/test_pages_3_4.py`
Expected: PASS

**Step 5: Commit**
```bash
git add ui/controller.py scratch/test_pages_3_4.py
git commit -m "feat(ui): build translation/ocr page and subtitle style with live preview"
```

---

### Task 5: End-to-End Integration, Visual Polish & Verification

**Files:**
- Modify: `main.py` (if theme adjustment or title is needed)
- Modify: `ui/controller.py` (polish hover effects, tooltips, responsive layout)
- Test: `scratch/test_full_ui.py`

**Step 1: Write comprehensive integration test**
Test switching providers, updating interval, changing subtitle style with live preview update, and clicking start without API key.

```python
# scratch/test_full_ui.py
import sys
from PyQt5.QtWidgets import QApplication
from ui.controller import ControllerWindow
from ui.overlay import Overlay
from core.config import State

app = QApplication.instance() or QApplication(sys.argv)
state = State()
overlay = Overlay()
c = ControllerWindow(worker=None, state=state, on_select_region=lambda: None, on_quit=lambda: None, overlay=overlay)

# Verify initial states
assert c.pages.currentIndex() == 0
# Switch to AI page
c._switch_to_page(1)
assert c.pages.currentIndex() == 1
# Switch to Subtitle page & change opacity
c._switch_to_page(3)
c.opacity_slider.setValue(65)
assert state.bg_opacity == 65
print("✅ Full integration test passed successfully!")
```

**Step 2: Run full integration test**
Run: `python scratch/test_full_ui.py`
Expected: PASS

**Step 3: Verification with actual application run**
Launch application in dry-run/preview mode to verify visual rendering and absence of Qt layout warnings.

**Step 4: Update task tracking & Final Commit**
```bash
git add ui/controller.py main.py docs/plans/task.md
git commit -m "feat(ui): finalize modern cyber dark dashboard controller redesign"
```
