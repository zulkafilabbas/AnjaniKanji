"""Calendar screen component for the Anjani Kanji desktop app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import flet as ft

from ..theme import (
    ACCENT,
    ACCENT_DIM,
    BG,
    BORDER,
    CALENDAR_HEIGHT,
    MUTED,
    PAGE_PADDING,
    PANEL,
    SECTION_TITLE_SIZE,
    TEXT,
    TOOLTIP_WAIT_MS,
    align,
    border_all,
)


@dataclass(slots=True)
class CalendarView:
    """Render the study history calendar."""

    month: datetime
    by_day: dict[str, set[str]]
    session_count: int
    on_prev_month: Callable[[], Any]
    on_next_month: Callable[[], Any]

    def build(self) -> ft.Control:
        """Build the full calendar screen."""
        weekday_labels = [
            ft.Text(day, color=MUTED, size=11, width=48, text_align=ft.TextAlign.CENTER)
            for day in ["S", "M", "T", "W", "T", "F", "S"]
        ]
        return ft.Container(
            padding=PAGE_PADDING,
            content=ft.Column(
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("calendar", color=ACCENT, size=SECTION_TITLE_SIZE, weight=ft.FontWeight.BOLD),
                            ft.Row(
                                controls=[
                                    self._action_button("prev", self.on_prev_month),
                                    ft.Text(self.month.strftime("%B %Y"), color=TEXT),
                                    self._action_button("next", self.on_next_month),
                                ]
                            ),
                        ],
                    ),
                    ft.Row(controls=weekday_labels),
                    ft.Container(
                        height=CALENDAR_HEIGHT,
                        content=ft.GridView(
                            runs_count=7,
                            max_extent=48,
                            spacing=4,
                            run_spacing=4,
                            child_aspect_ratio=1.0,
                            controls=self._build_cells(),
                        ),
                    ),
                    ft.Text(
                        f"{self.session_count} session{'s' if self.session_count != 1 else ''} recorded",
                        color=MUTED,
                        size=11,
                    ),
                ],
            ),
        )

    def _build_cells(self) -> list[ft.Control]:
        """Build the month grid cells."""
        year = self.month.year
        month = self.month.month
        first = datetime(year, month, 1)
        next_month = datetime(year + (month // 12), (month % 12) + 1, 1)
        days_in_month = (next_month - first).days
        first_dow = int(first.strftime("%w"))

        cells: list[ft.Control] = []
        for _ in range(first_dow):
            cells.append(ft.Container(width=48, height=48))

        for day in range(1, days_in_month + 1):
            key = datetime(year, month, day).strftime("%Y-%m-%d")
            count = len(self.by_day.get(key, set()))
            intensity = min(1.0, count / 10) if count else 0.0
            bg = ACCENT_DIM if count else BG
            opacity = 0.25 + intensity * 0.75 if count else 0
            studied = " ".join(sorted(self.by_day.get(key, set()))[:40])
            tooltip_message = f"{key}\n{count} studied\n{studied}" if count else key
            cells.append(
                ft.Container(
                    width=48,
                    height=48,
                    bgcolor=bg,
                    opacity=opacity if count else 1.0,
                    border=border_all(BORDER),
                    border_radius=4,
                    alignment=align(-1, -1),
                    padding=6,
                    tooltip=ft.Tooltip(
                        message=tooltip_message,
                        bgcolor=PANEL,
                        border=border_all(BORDER),
                        text_style=ft.TextStyle(color=TEXT, size=12),
                        wait_duration=TOOLTIP_WAIT_MS,
                    ),
                    content=ft.Text(str(day), color=ACCENT if count else MUTED, size=11),
                )
            )
        return cells

    def _action_button(self, label: str, action: Callable[[], Any]) -> ft.Control:
        """Build a month navigation button."""
        return ft.ElevatedButton(label, on_click=lambda _e: action(), bgcolor=PANEL, color=TEXT)
