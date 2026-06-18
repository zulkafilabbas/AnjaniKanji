"""Dashboard header component for the Anjani Kanji desktop app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import flet as ft

from ..theme import (
    ACCENT,
    ACCENT_DIM,
    DIVIDER,
    DURATION_WIDTH_IDLE,
    METRIC_LABEL_SIZE,
    METRIC_PADDING,
    METRIC_VALUE_SIZE,
    MUTED,
    PANEL_ALT,
    PANEL_RADIUS,
    SURFACE,
    SMALL_GAP,
    TEXT,
    TEXT_SOFT,
    border_all,
)
from ..view_models import DashboardSummaryViewModel


@dataclass(slots=True)
class DashboardHeader:
    """Render dashboard metrics and the top action row."""

    model: DashboardSummaryViewModel
    on_set_duration: Callable[[str], Any]
    on_start_queue: Callable[[], Any]
    on_start_selected: Callable[[], Any]
    on_end_session: Callable[[], Any]
    on_start_relearn: Callable[[], Any]
    on_start_review: Callable[[], Any]
    on_start_new: Callable[[], Any]

    def build_metrics(self) -> ft.Control:
        """Build the summary strip shown above the dashboard."""
        return ft.ResponsiveRow(
            controls=[
                self._metric_card("re-learn", self.model.relearn_count, self.on_start_relearn),
                self._metric_card("review", self.model.review_count, self.on_start_review),
                self._metric_card("new", self.model.new_count, self.on_start_new),
                self._metric_card("studied today", self.model.studied_today),
            ]
        )

    def build_actions(self) -> ft.Control:
        """Build the dashboard action row for both idle and study states."""
        return ft.Container(
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=METRIC_PADDING,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        wrap=True,
                        alignment=ft.MainAxisAlignment.START,
                        spacing=10,
                        controls=[
                            ft.ElevatedButton(
                                f"start daily queue ({self.model.queue_total})",
                                on_click=lambda _e: self.on_start_queue(),
                                bgcolor=ACCENT_DIM,
                                color=TEXT,
                                disabled=self.model.queue_total == 0,
                            ),
                            ft.ElevatedButton(
                                f"practice selected ({self.model.selected_count})",
                                on_click=lambda _e: self.on_start_selected(),
                                bgcolor=PANEL_ALT,
                                color=TEXT,
                                disabled=self.model.selected_count == 0,
                            ),
                            ft.Container(width=SMALL_GAP),
                            ft.Text("duration", color=MUTED, size=12),
                            self._duration_field(DURATION_WIDTH_IDLE),
                            ft.Text("s", color=MUTED),
                        ],
                    ),
                    ft.Text(self.model.queue_hint_text, color=TEXT_SOFT, size=11),
                    ft.Text(
                        f"next scheduled review {self.model.next_due_text}"
                        if self.model.next_due_text != "-"
                        else "next scheduled review -",
                        color=MUTED,
                        size=11,
                    ),
                ],
            ),
        )

    def _duration_field(self, width: float) -> ft.Control:
        """Build the shared duration editor."""
        return ft.TextField(
            value=str(self.model.duration_sec),
            width=width,
            on_submit=lambda e: self.on_set_duration(e.control.value),
            on_blur=lambda e: self.on_set_duration(e.control.value),
            color=TEXT,
            bgcolor=PANEL_ALT,
            border_color=DIVIDER,
            text_size=12,
        )

    def _metric_card(self, label: str, value: int, action: Callable[[], Any] | None = None) -> ft.Control:
        """Build one metric card."""
        return ft.Container(
            col={"sm": 6, "md": 3},
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=METRIC_PADDING,
            ink=action is not None and value > 0,
            on_click=(lambda _e: action()) if action is not None and value > 0 else None,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Text(label, color=MUTED, size=METRIC_LABEL_SIZE),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(str(value), color=TEXT, size=METRIC_VALUE_SIZE, weight=ft.FontWeight.BOLD),
                            ft.Text("open" if action is not None and value > 0 else "", color=TEXT_SOFT, size=10),
                        ],
                    ),
                ],
            ),
        )
