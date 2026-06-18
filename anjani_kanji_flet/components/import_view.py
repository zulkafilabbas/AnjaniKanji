"""Import screen component for the Anjani Kanji desktop app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import flet as ft

from ..storage import Source
from ..theme import ACCENT, BORDER, IMPORT_LOG_HEIGHT, MUTED, PAGE_PADDING, PANEL, SECTION_TITLE_SIZE, TEXT, WARN, border_all
from ..view_models import StatusLogEntryViewModel


@dataclass(slots=True)
class ImportView:
    """Render the CSV import view."""

    sources: list[Source]
    import_log: list[StatusLogEntryViewModel]
    on_choose_files: Callable[[], Any]
    on_load_example: Callable[[], Any]
    on_reset_all: Callable[[], Any]

    def build(self) -> ft.Control:
        """Build the full import screen."""
        return ft.Container(
            padding=PAGE_PADDING,
            content=ft.Column(
                controls=[
                    ft.Text("import csv", color=ACCENT, size=SECTION_TITLE_SIZE, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "column 1 = Kanji, columns 2..N = English meanings. Each CSV becomes its own deck.",
                        color=MUTED,
                        size=12,
                    ),
                    ft.Row(
                        wrap=True,
                        controls=[
                            self._action_button("choose files", self.on_choose_files),
                            self._action_button("load example", self.on_load_example),
                            self._action_button("reset all data", self.on_reset_all),
                        ],
                    ),
                    ft.Text("import log", color=MUTED, size=11),
                    ft.Container(
                        bgcolor=PANEL,
                        border=border_all(BORDER),
                        border_radius=4,
                        padding=12,
                        height=IMPORT_LOG_HEIGHT,
                        content=ft.Column(
                            scroll=ft.ScrollMode.AUTO,
                            controls=[
                                self._log_entry(entry)
                                for entry in (
                                    self.import_log
                                    or [StatusLogEntryViewModel(level="info", message="// nothing imported this session")]
                                )
                            ],
                        ),
                    ),
                    ft.Text(f"sources ({len(self.sources)})", color=MUTED, size=11),
                    ft.Container(
                        bgcolor=PANEL,
                        border=border_all(BORDER),
                        border_radius=4,
                        padding=12,
                        content=ft.Column(spacing=8, controls=self._build_source_rows()),
                    ),
                ],
            ),
        )

    def _build_source_rows(self) -> list[ft.Control]:
        """Build the imported sources list."""
        if not self.sources:
            return [ft.Text("no sources yet", color=MUTED, size=12)]

        return [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(source.filename, color=ACCENT),
                    ft.Text(
                        f"{source.count} rows · {datetime.fromtimestamp(source.imported_at / 1000).strftime('%Y-%m-%d %H:%M')}",
                        color=MUTED,
                        size=11,
                    ),
                ],
            )
            for source in self.sources
        ]

    def _action_button(self, label: str, action: Callable[[], Any]) -> ft.Control:
        """Build an import action button."""
        return ft.ElevatedButton(label, on_click=lambda _e: action(), bgcolor=PANEL, color=TEXT)

    def _log_entry(self, entry: StatusLogEntryViewModel) -> ft.Control:
        """Build one typed log line."""
        color = WARN if entry.level == "error" else ACCENT if entry.level == "success" else TEXT
        return ft.Text(entry.message, color=color, size=11)
