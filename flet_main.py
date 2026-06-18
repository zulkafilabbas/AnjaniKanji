from __future__ import annotations

import flet as ft

from anjani_kanji_flet.app import main


if __name__ == "__main__":
    runner = getattr(ft, "run", None)
    if callable(runner):
        runner(main)
    else:
        ft.app(target=main)
