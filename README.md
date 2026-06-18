# Anjani Kanji
A Flet Flash card application for studying Kanji. 
Import your CSV of Kanji with Text labels. 
The Dashboard is a convienent way of viewing and selecting them for practice.
Once you start practice, you are taken to the Flash Card view, where, 
you can play to view stroke order animation or flip to view text labels.

Mostly vibe-coded AI Slop, but still convienient,
do not rely on FSRS or SSP-MMC-FSRS, they're mostly untested.

## User Guide
0. Setup a virtual environment venv, uv, whatever.
1. Install, tested this on 3.11
2. Basic dependencies are: `pip install -r requirements.txt`
3. Optional: if you want the local `SSP-MMC-FSRS` package-backed scheduler mode instead of the built-in FSRS mode, also install:
   - `pip install numpy`
   - `pip install torch --index-url https://download.pytorch.org/whl/cpu`
   - `pip install tqdm matplotlib`
4. Launch the application: `python flet_main.py`

---

## Developer Guide

**Architecture**
The codebase strictly separates presentation (how it looks) from logic (how it works).

* **Views:** UI components like `dashboard_header.py`, `sidebar_panel.py`, and `kanji_card.py` handle what the user sees.
* **Models:** Data structures and persistence are managed by `view_models.py`, `csv_utils.py`, and `storage.py`.
* **Controllers:** The core study session logic and review sequencing are driven by `study_controller.py`.

**Development**
Create a virtual environment, install the dependencies, and run `flet_main.py` to test your local changes.

**Dependency Notes**

* `requirements.txt` is enough for the desktop app and the built-in FSRS scheduler.
* The local `SSP-MMC-FSRS` bridge has extra runtime dependencies taken from `SSP-MMC-FSRS/pyproject.toml`: `numpy`, `torch`, `tqdm`, and `matplotlib`.
* If the app says package mode is unavailable, check those packages in the same Python environment used to launch `flet_main.py`.
