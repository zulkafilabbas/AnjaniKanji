"""Sidebar component for the Anjani Kanji desktop app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import flet as ft

from ..storage import DashboardData, Profile
from ..theme import (
    ACCENT,
    ACCENT_DIM,
    BG,
    BORDER,
    CONTROL_RADIUS,
    DIVIDER,
    MUTED,
    PANEL,
    PANEL_ALT,
    PANEL_PADDING,
    PANEL_SOFT,
    SIDEBAR_MENU_BUTTON_WIDTH,
    SIDEBAR_RAIL_WIDTH,
    TEXT,
    align,
    border_all,
    pad_only,
    pad_symmetric,
)


@dataclass(slots=True)
class SidebarPanel:
    """Render the navigation and management sidebar."""

    detail_visible: bool
    compact_layout: bool
    focus_mode: bool
    panel_width: float | None
    view: str
    profiles: list[Profile]
    profile_id: str | None
    new_profile_name: str
    data: DashboardData | None
    on_toggle_sidebar: Callable[[], Any]
    on_set_view: Callable[[str], Any]
    on_switch_profile: Callable[[str | None], Any]
    on_new_profile_name_change: Callable[[str], Any]
    on_add_profile: Callable[[], Any]
    on_delete_profile: Callable[[], Any]
    on_set_deck: Callable[[str], Any]
    on_delete_deck: Callable[[], Any]
    on_daily_target_change: Callable[[str], Any]
    on_scheduler_mode_change: Callable[[str], Any]
    on_desired_retention_change: Callable[[str], Any]
    on_import_backup: Callable[[], Any]
    on_import_backup_copy: Callable[[], Any]
    on_begin_export: Callable[[], Any]
    scheduler_package_available: bool
    scheduler_status_text: str
    scheduler_detail_text: str
    builtin_scheduler_mode: str
    package_scheduler_mode: str
    embedded: bool = False

    def build(self) -> ft.Control:
        """Build the full sidebar control."""
        if self.embedded:
            return self._build_expanded_sidebar()
        if not self.detail_visible:
            return self._build_compact_rail()
        return self._build_expanded_sidebar()

    def _build_compact_rail(self) -> ft.Control:
        return ft.Container(
            width=SIDEBAR_RAIL_WIDTH,
            bgcolor=PANEL_SOFT,
            padding=pad_only(top=18, left=10, right=10, bottom=12),
            content=ft.Column(
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("kt", color=ACCENT, size=18, weight=ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    self._nav_button("dashboard", "dashboard"),
                    self._nav_button("library", "library"),
                    self._nav_button("calendar", "calendar"),
                    self._nav_button("learn", "learn"),
                    self._nav_button("settings", "settings"),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        ">>",
                        on_click=lambda _e: self.on_toggle_sidebar(),
                        bgcolor=ACCENT_DIM,
                        color=TEXT,
                        width=SIDEBAR_MENU_BUTTON_WIDTH,
                    ),
                ],
            ),
        )

    def _build_expanded_sidebar(self) -> ft.Control:
        profile_options = [ft.dropdown.Option(profile.id, profile.name) for profile in self.profiles]
        deck_buttons: list[ft.Control] = []
        if self.data and self.data.decks:
            for deck in self.data.decks:
                active = self.data.deck and self.data.deck.id == deck.id
                deck_buttons.append(
                    ft.Container(
                        bgcolor=ACCENT_DIM if active else PANEL,
                        border=border_all(ACCENT if active else BORDER),
                        border_radius=4,
                        padding=pad_symmetric(horizontal=10, vertical=8),
                        ink=True,
                        on_click=lambda _e, deck_id=deck.id: self.on_set_deck(deck_id),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(deck.name, color=TEXT, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                                ft.Text(str(deck.count), color=MUTED),
                            ],
                        ),
                    )
                )
        else:
            deck_buttons.append(ft.Text("import a CSV deck to begin", color=MUTED, size=12))

        header_controls: list[ft.Control] = []
        if not self.embedded:
            header_controls.extend(
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Anjani Kanji", color=TEXT, size=18, weight=ft.FontWeight.BOLD),
                            ft.ElevatedButton(
                                "hide",
                                on_click=lambda _e: self.on_toggle_sidebar(),
                                bgcolor=ACCENT_DIM,
                                color=TEXT,
                                visible=not self.compact_layout,
                            ),
                        ],
                    ),
                    ft.Row(
                        wrap=True,
                        spacing=8,
                        controls=[
                            self._nav_button("dashboard", "dashboard"),
                            self._nav_button("library", "library"),
                            self._nav_button("calendar", "calendar"),
                            self._nav_button("learn", "learn"),
                            self._nav_button("settings", "settings"),
                        ],
                    ),
                    ft.Divider(color=DIVIDER),
                ]
            )

        return ft.Container(
            width=self.panel_width,
            bgcolor=PANEL_SOFT,
            padding=PANEL_PADDING,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    *header_controls,
                    ft.Text("profile", color=MUTED, size=11),
                    ft.Dropdown(
                        value=self.profile_id,
                        options=profile_options,
                        on_change=lambda e: self.on_switch_profile(e.control.value),
                        text_style=ft.TextStyle(color=TEXT),
                        bgcolor=BG,
                        color=TEXT,
                        border_color=BORDER,
                    ),
                    ft.Row(
                        controls=[
                            ft.TextField(
                                value=self.new_profile_name,
                                hint_text="new profile",
                                on_change=lambda e: self.on_new_profile_name_change(e.control.value),
                                expand=True,
                                color=TEXT,
                                bgcolor=BG,
                                border_color=BORDER,
                                text_size=12,
                            ),
                            ft.ElevatedButton("add", on_click=lambda _e: self.on_add_profile(), bgcolor=ACCENT_DIM, color=TEXT),
                        ]
                    ),
                    ft.ElevatedButton(
                        "delete current profile",
                        on_click=lambda _e: self.on_delete_profile(),
                        bgcolor=PANEL_ALT, # Changed from "#ef7d73"
                        color=TEXT,
                        disabled=self.profile_id is None,
                    ),
                    ft.Divider(color=DIVIDER),
                    ft.Text("decks", color=MUTED, size=11),
                    ft.Column(spacing=8, controls=deck_buttons),
                    ft.ElevatedButton(
                        "delete active deck",
                        on_click=lambda _e: self.on_delete_deck(),
                        bgcolor=PANEL_ALT, # Changed from "#ef7d73"
                        color=TEXT,
                        disabled=not (self.data and self.data.deck),
                    ),
                    ft.Divider(color=DIVIDER),
                    ft.Text("daily new", color=MUTED, size=11),
                    ft.TextField(
                        value=str(self.data.profile.daily_new_target if self.data else 10),
                        on_submit=lambda e: self.on_daily_target_change(e.control.value),
                        on_blur=lambda e: self.on_daily_target_change(e.control.value),
                        color=TEXT,
                        bgcolor=BG,
                        border_color=BORDER,
                        text_size=12,
                    ),
                    ft.Divider(color=DIVIDER),
                    ft.Text("scheduler", color=MUTED, size=11),
                    ft.Dropdown(
                        value=self.data.profile.scheduler_mode if self.data else self.builtin_scheduler_mode,
                        options=[
                            ft.dropdown.Option(self.builtin_scheduler_mode, "fsrs built-in"),
                            ft.dropdown.Option(self.package_scheduler_mode, "ssp-mmc-fsrs package"),
                        ],
                        on_change=lambda e: self.on_scheduler_mode_change(e.control.value),
                        text_style=ft.TextStyle(color=TEXT),
                        bgcolor=BG,
                        color=TEXT,
                        border_color=BORDER,
                    ),
                    ft.TextField(
                        value=f"{self.data.profile.desired_retention:.2f}" if self.data else "0.90",
                        hint_text="desired retention (0.70-0.99)",
                        on_submit=lambda e: self.on_desired_retention_change(e.control.value),
                        on_blur=lambda e: self.on_desired_retention_change(e.control.value),
                        color=TEXT,
                        bgcolor=BG,
                        border_color=BORDER,
                        text_size=12,
                    ),
                    ft.Text(self.scheduler_status_text, color=TEXT, size=11),
                    ft.Text(
                        self.scheduler_detail_text,
                        color=MUTED if self.scheduler_package_available else ACCENT,
                        size=11,
                    ),
                    ft.Divider(color=DIVIDER),
                    ft.Text("backup", color=MUTED, size=11),
                    ft.Row(
                        wrap=True,
                        controls=[
                            ft.ElevatedButton("import profile", on_click=lambda _e: self.on_import_backup(), bgcolor=PANEL_ALT, color=TEXT),
                            ft.ElevatedButton("import as copy", on_click=lambda _e: self.on_import_backup_copy(), bgcolor=PANEL_ALT, color=TEXT),
                            ft.ElevatedButton("export profile", on_click=lambda _e: self.on_begin_export(), bgcolor=ACCENT_DIM, color=TEXT),
                        ],
                    ),
                ],
            ),
        )

    def _nav_button(self, key: str, label: str) -> ft.Control:
        active = self.view == key
        compact = not self.detail_visible
        return ft.Container(
            bgcolor=ACCENT_DIM if active else PANEL_ALT,
            border=border_all(ACCENT if active else DIVIDER),
            border_radius=CONTROL_RADIUS,
            padding=pad_symmetric(horizontal=12 if not compact else 0, vertical=8),
            width=SIDEBAR_MENU_BUTTON_WIDTH if compact else None,
            ink=True,
            on_click=lambda _e, value=key: self.on_set_view(value),
            tooltip=label,
            content=ft.Text(label[0].upper() if compact else label, color=TEXT, size=12, text_align=ft.TextAlign.CENTER),
        )
