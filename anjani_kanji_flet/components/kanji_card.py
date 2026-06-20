"""Study surface component for the Anjani Kanji desktop app.

The main app owns state transitions and persistence. This component only turns
the current study state into Flet controls and routes user input back through
callbacks supplied by the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import flet as ft
import flet.canvas as cv

from ..strokes import StrokeFrameSet, canvas_shapes
from ..theme import (
    ACCENT,
    ACCENT_DIM,
    BG,
    CARD_EMPTY_PADDING,
    CARD_PADDING,
    CARD_RADIUS,
    DIVIDER,
    get_elevation_shadow,
    HOME_HINT_SIZE,
    KANJI_EMPTY_SIZE,
    KANJI_FOCUS_SIZE,
    KANJI_IDLE_SIZE,
    MUTED,
    PANEL_ALT,
    SURFACE,
    TEXT,
    TEXT_SOFT,
    WARN,
    align,
    border_all,
    pad_only,
)
from ..view_models import StudyCardViewModel


@dataclass(slots=True)
class KanjiCard:
    """Render the study card, rating controls, and footer."""

    model: StudyCardViewModel
    stroke_frame_set: StrokeFrameSet | None
    visible_strokes: float
    on_play: Callable[[], Any]
    on_flip: Callable[[], Any]
    on_prev: Callable[[], Any]
    on_next: Callable[[], Any]
    on_select: Callable[[], Any]
    on_rate: Callable[[str], Any]

    def build_card(self) -> ft.Control:
        """Build the central flashcard surface."""
        if not self.model.active:
            return ft.Container(
                width=self.model.card_size,
                height=self.model.card_size,
                bgcolor=SURFACE,
                border=border_all(DIVIDER),
                border_radius=CARD_RADIUS,
                padding=CARD_EMPTY_PADDING,
                shadow=get_elevation_shadow(),
                content=ft.Column(
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("KANJI", color=TEXT, size=KANJI_EMPTY_SIZE, weight=ft.FontWeight.BOLD),
                        ft.Text(self.model.stroke_message, color=MUTED, size=HOME_HINT_SIZE),
                        ft.Text("start a queue or select kanji to focus", color=TEXT_SOFT, size=11),
                    ],
                ),
            )

        if self.model.flipped:
            meaning_controls: list[ft.Control] = [ft.Text(self.model.active.character, color=MUTED, size=max(14, self.model.kanji_text_size * 0.24))]
            if self.model.active.meanings:
                meaning_controls.extend(ft.Text(item, color=TEXT, size=self.model.meaning_text_size) for item in self.model.active.meanings)
            else:
                meaning_controls.append(ft.Text("no meanings", color=MUTED, size=14))
            content: ft.Control = ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=meaning_controls,
            )
        elif self.stroke_frame_set and self.visible_strokes > 0:
            content = cv.Canvas(
                width=self.model.canvas_size,
                height=self.model.canvas_size,
                shapes=canvas_shapes(self.stroke_frame_set, self.visible_strokes, canvas_size=self.model.canvas_size),
            )
        else:
            content = ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        self.model.active.character,
                        color=TEXT,
                        size=self.model.kanji_text_size if self.model.focus_mode else max(56.0, self.model.kanji_text_size - 6.0),
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(self.model.stroke_message, color=MUTED, size=12, text_align=ft.TextAlign.CENTER),
                ],
            )

        return ft.Container(
            width=self.model.card_size,
            height=self.model.card_size,
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=CARD_RADIUS,
            padding=CARD_PADDING,
            shadow=get_elevation_shadow(),
            ink=True,
            on_click=lambda _e: self.on_play(),
            content=ft.Container(expand=True, alignment=align(0, 0), content=content),
        )

    def build_session_controls(self) -> ft.Control:
        """Build the primary rating and secondary navigation controls."""
        if not self.model.session_active:
            return ft.Container(height=0)

        primary_labels = [
            ("1 again", "again", WARN),
            ("2 hard", "hard", PANEL_ALT),
            ("3 good", "good", ACCENT_DIM),
            ("4 easy", "easy", ACCENT),
        ]
        return ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    wrap=True,
                    spacing=10,
                    controls=[
                        ft.ElevatedButton(
                            label,
                            on_click=lambda _e, value=rating: self.on_rate(value),
                            bgcolor=color,
                            color=BG if rating == "easy" else TEXT,
                        )
                        for label, rating, color in primary_labels
                    ],
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    wrap=True,
                    spacing=8,
                    controls=[
                        self._secondary_button("<", self.on_prev),
                        self._secondary_button("play", self.on_play),
                        self._secondary_button("flip", self.on_flip),
                        self._secondary_button(">", self.on_next),
                    ],
                ),
            ],
        )

    def build_footer(self) -> ft.Control:
        """Build the small study metadata footer."""
        return ft.Container(
            border=ft.Border(top=ft.BorderSide(1, DIVIDER)),
            padding=pad_only(top=10),
            content=ft.Row(
                wrap=True,
                spacing=14,
                controls=[
                    ft.Text(f"current {self.model.current_character}", color=MUTED, size=11),
                    ft.Text(f"last seen {self.model.last_seen_text}", color=MUTED, size=11),
                    ft.Text(f"due {self.model.due_text}", color=MUTED, size=11),
                    ft.Text(f"session {self.model.session_text}", color=MUTED, size=11),
                    ft.Text(f"deck total {self.model.deck_total}", color=MUTED, size=11),
                ],
            ),
        )

    def _secondary_button(self, label: str, action: Callable[[], Any]) -> ft.Control:
        """Build a lower-emphasis session control button."""
        return ft.ElevatedButton(
            label,
            on_click=lambda _e: action(),
            bgcolor=PANEL_ALT,
            color=TEXT,
            style=ft.ButtonStyle(padding=ft.Padding(12, 10, 12, 10)),
        )
