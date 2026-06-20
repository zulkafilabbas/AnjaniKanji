from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import flet as ft
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Flet is not installed. Install requirements.txt before launching the Anjani Kanji desktop app."
    ) from exc

from .components.kanji_card import KanjiCard
from .components.calendar_view import CalendarView
from .components.dashboard_header import DashboardHeader
from .components.import_view import ImportView
from .components.sidebar_panel import SidebarPanel
from .controllers.study_controller import CalendarStudyData, StudyController
from .fsrs_scheduler import DEFAULT_SCHEDULER_MODE, PACKAGE_DR_SCHEDULER_MODE
from .scheduler_runtime import SchedulerRuntimeStatus
from .storage import (
    AppStorage,
    CardState,
    DashboardData,
    Profile,
    Session,
    now_ms,
)
from .strokes import StrokeFrameSet, build_stroke_frames, load_stroke_svg
from .theme import (
    ACCENT,
    ACCENT_DIM,
    BG,
    CARD_CANVAS_INSET,
    CARD_COMPACT_MARGIN,
    CARD_COMPACT_MAX,
    CARD_COMPACT_MIN,
    CARD_WIDE_GUTTER,
    CARD_WIDE_MAX,
    CARD_WIDE_MIN,
    CARD_WIDE_RATIO,
    COMPACT_BREAKPOINT,
    DIVIDER,
    FILMSTRIP_FADE_COMPACT,
    FILMSTRIP_FADE_DESKTOP,
    FILMSTRIP_GAP,
    FILMSTRIP_TEXT_COMPACT,
    FILMSTRIP_TEXT_DESKTOP,
    FILMSTRIP_TILE_COMPACT,
    FILMSTRIP_TILE_DESKTOP,
    FILMSTRIP_VISIBLE_COMPACT,
    FILMSTRIP_VISIBLE_DESKTOP,
    MUTED,
    PAGE_PADDING,
    PANEL_ALT,
    PANEL_RADIUS,
    PANEL_SOFT,
    SURFACE,
    SURFACE_RAISED,
    SIDEBAR_MAX_WIDTH,
    SIDEBAR_MIN_WIDTH,
    SIDEBAR_WIDTH_RATIO,
    TEXT,
    TEXT_SOFT,
    align,
    border_all,
    get_elevation_shadow,
    pad_symmetric,
)
from .view_models import FilmstripTileViewModel, KanjiEntryView, StatusLogEntryViewModel


class AnjaniKanjiDesktop:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.storage = AppStorage()
        self.controller = StudyController(self.storage)
        self.view = "dashboard"
        self.data: DashboardData | None = None
        self.profiles: list[Profile] = []
        self.profile_id: str | None = None
        self.scheduler_status: SchedulerRuntimeStatus = self.controller.scheduler_status()
        self.kanji: list[KanjiEntryView] = []
        self.selected: set[str] = set()
        self.preview_character: str | None = None
        self.session: Session | None = None
        self.session_snapshot_cards: dict[str, CardState] = {}
        self.session_snapshot_last_seen: dict[str, int | None] = {}
        self.pos = 0
        self.flipped = False
        self.duration_sec = 3.0
        self.new_profile_name = ""
        self.import_log: list[StatusLogEntryViewModel] = []
        self.pending_export_text: str | None = None
        self.pending_export_name = "kanji-profile.json"
        today = datetime.now()
        self.month = datetime(today.year, today.month, 1)
        self.stroke_message = "start the daily queue"
        self.stroke_frame_set: StrokeFrameSet | None = None
        self.visible_strokes = 0.0
        self.play_token = 0
        self.pending_picker_action: str | None = None
        self.sidebar_expanded = True
        self.dashboard_root: ft.Container | None = None
        self.dashboard_metrics_host: ft.Container | None = None
        self.dashboard_actions_host: ft.Container | None = None
        self.dashboard_filmstrip_host: ft.Container | None = None
        self.dashboard_card_host: ft.Container | None = None
        self.dashboard_session_host: ft.Container | None = None
        self.dashboard_footer_host: ft.Container | None = None
        self.filmstrip_list: ft.Row | None = None
        self.filmstrip_scroll_offset = 0.0
        self.dashboard_grid: ft.GridView | None = None
        self.dashboard_grid_scroll_offset = 0.0
        self.sidebar_host: ft.Container | None = None
        self.main_host: ft.Container | None = None
        self.shell_host: ft.Container | None = None
        self.sidebar_open = False
        self.dashboard_library_open = False

        self.file_picker = ft.FilePicker(on_result=self.on_files_picked)
        self.save_picker = ft.FilePicker(on_result=self.on_save_picked)
        self.page.overlay.extend([self.file_picker, self.save_picker])
        self.configure_page()
        self.root = ft.Container(expand=True, padding=0, bgcolor=BG)
        self.page.add(self.root)
        self.refresh_data()
        self.render()

    def configure_page(self) -> None:
        self.page.title = "Anjani Kanji"
        self.page.bgcolor = BG
        self.page.window_bgcolor = BG
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.scroll = ft.ScrollMode.AUTO
        self.page.on_resized = lambda _e: self.render()

    def viewport_width(self) -> float:
        width = float(getattr(self.page, "width", 0) or 0)
        if width <= 0:
            width = float(getattr(self.page, "window_width", 0) or 0)
        return width or 1280.0

    def is_compact_layout(self) -> bool:
        return self.viewport_width() < COMPACT_BREAKPOINT

    def in_focus_mode(self) -> bool:
        return self.view == "learn" and self.session is not None

    def sidebar_detail_visible(self) -> bool:
        if self.is_compact_layout():
            return self.sidebar_open
        return self.sidebar_expanded

    def sidebar_panel_width(self) -> float:
        width = self.viewport_width()
        return max(SIDEBAR_MIN_WIDTH, min(SIDEBAR_MAX_WIDTH, width * SIDEBAR_WIDTH_RATIO))

    def card_size(self) -> float:
        width = self.viewport_width()
        if self.is_compact_layout():
            return max(CARD_COMPACT_MIN, min(CARD_COMPACT_MAX, width - CARD_COMPACT_MARGIN))
        available = width - self.sidebar_panel_width() - CARD_WIDE_GUTTER
        return max(CARD_WIDE_MIN, min(CARD_WIDE_MAX, available * CARD_WIDE_RATIO))

    def canvas_size(self) -> float:
        return max(SIDEBAR_MIN_WIDTH, self.card_size() - CARD_CANVAS_INSET)

    def filmstrip_tile_size(self) -> float:
        return FILMSTRIP_TILE_COMPACT if self.is_compact_layout() else FILMSTRIP_TILE_DESKTOP

    def filmstrip_visible_count(self) -> int:
        return FILMSTRIP_VISIBLE_COMPACT if self.is_compact_layout() else FILMSTRIP_VISIBLE_DESKTOP

    def filmstrip_fade_width(self) -> float:
        return FILMSTRIP_FADE_COMPACT if self.is_compact_layout() else FILMSTRIP_FADE_DESKTOP

    def filmstrip_viewport_width(self) -> float:
        tile = self.filmstrip_tile_size()
        visible = self.filmstrip_visible_count()
        return tile * visible + FILMSTRIP_GAP * max(0, visible - 1) + self.filmstrip_fade_width() * 2

    def refresh_data(self, next_profile_id: str | None = None) -> None:
        self.scheduler_status = self.controller.scheduler_status()
        state = self.controller.load_dashboard_state(self.profile_id, next_profile_id)
        self.profiles = state.profiles
        self.profile_id = state.profile_id
        self.data = state.data
        self.kanji = state.kanji
        self.sync_preview_character()
        if not self.profile_id:
            return
        self.load_active_stroke()

    def sync_preview_character(self) -> None:
        """Keep the non-session preview on a valid kanji in the active deck."""
        if self.session:
            return
        available = [item.character for item in self.kanji]
        if self.preview_character in available:
            return
        selected_available = [character for character in available if character in self.selected]
        if selected_available:
            self.preview_character = selected_available[0]
            return
        self.preview_character = available[0] if available else None

    def active_character(self) -> str | None:
        if not self.session:
            return self.preview_character
        if self.pos < 0 or self.pos >= len(self.session.kanji):
            return None
        return self.session.kanji[self.pos]

    def active_kanji(self) -> KanjiEntryView | None:
        active = self.active_character()
        if not active:
            return None
        for item in self.kanji:
            if item.character == active:
                return item
        return None

    def add_status_log(self, message: str, *, level: str = "info") -> None:
        """Push a typed status message into the import/backup activity log."""
        self.import_log.insert(0, StatusLogEntryViewModel(level=level, message=message))

    def reset_study_state(self, *, clear_selection: bool = False) -> None:
        """Clear the active study session while keeping profile/deck context intact."""
        self.play_token += 1
        self.session = None
        self.session_snapshot_cards = {}
        self.session_snapshot_last_seen = {}
        self.pos = 0
        self.flipped = False
        if clear_selection:
            self.selected.clear()
        self.sync_preview_character()

    def capture_session_snapshot(self, session: Session) -> None:
        """Cache the starting state of cards touched by the active session."""
        cards: dict[str, CardState] = {}
        kanji_last_seen: dict[str, int | None] = {}
        kanji_map = {item.character: item for item in self.kanji}
        for character in session.kanji:
            card = self.storage.get_card(session.profile_id, session.deck_id, character)
            if card is not None:
                cards[character] = card
            kanji_last_seen[character] = kanji_map.get(character).last_seen_at if character in kanji_map else None
        self.session_snapshot_cards = cards
        self.session_snapshot_last_seen = kanji_last_seen

    def begin_session(self, session: Session) -> None:
        """Activate a new study session and prepare the focused study surface."""
        if not self.is_compact_layout():
            self.sidebar_expanded = False
        self.play_token += 1
        self.session = session
        self.capture_session_snapshot(session)
        self.pos = 0
        self.flipped = False
        self.controller.save_session(self.session)
        self.ensure_active_seen()
        self.load_active_stroke()

    def refresh_profile_view(self, profile_id: str | None, *, full_render: bool = True) -> None:
        """Reload dashboard data for a profile and refresh the current view."""
        self.refresh_data(profile_id)
        if full_render:
            self.render()
            return
        self.refresh_dashboard_regions("metrics", "actions", "filmstrip", "card", "session", "footer")

    def ensure_active_seen(self) -> None:
        if not self.session:
            return
        active = self.active_character()
        if not active or active in self.session.seen:
            return
        updated = replace(self.session, seen=[*self.session.seen, active])
        self.session = updated
        self.controller.mark_seen(active)
        self.controller.save_session(updated)
        self.flipped = False
        self.refresh_data(self.session.profile_id)

    def load_active_stroke(self) -> None:
        active = self.active_character()
        if not active:
            self.stroke_frame_set = None
            self.visible_strokes = 0.0
            if self.data and self.data.deck:
                total = len(self.data.new_queue) + len(self.data.review_queue) + len(self.data.relearn_queue)
                self.stroke_message = "daily queue clear" if total == 0 else "start the daily queue"
            else:
                self.stroke_message = "import a CSV deck to begin"
            return
        svg_text = load_stroke_svg(self.storage, active)
        if not svg_text:
            self.stroke_frame_set = None
            self.visible_strokes = 0.0
            self.stroke_message = "no stroke data for this character"
            return
        self.stroke_frame_set = build_stroke_frames(svg_text)
        self.visible_strokes = 0.0
        self.stroke_message = "press play to animate strokes" if self.stroke_frame_set else "no stroke data for this character"

    async def animate_strokes(self) -> None:
        if not self.stroke_frame_set or not self.stroke_frame_set.strokes:
            return
        self.play_token += 1
        token = self.play_token
        stroke_count = len(self.stroke_frame_set.strokes)
        duration = max(0.05, self.duration_sec)
        frame_delay = 1 / 60
        self.visible_strokes = 0.0
        self.stroke_message = ""
        self.refresh_dashboard_regions("card")
        await asyncio.sleep(0.02)
        started = time.perf_counter()
        while True:
            if token != self.play_token:
                return
            elapsed = time.perf_counter() - started
            progress = min(1.0, elapsed / duration)
            self.visible_strokes = stroke_count * progress
            self.refresh_dashboard_regions("card")
            if progress >= 1.0:
                break
            await asyncio.sleep(frame_delay)
        self.visible_strokes = float(stroke_count)
        self.refresh_dashboard_regions("card")

    def set_view(self, view: str) -> None:
        self.view = view
        if self.is_compact_layout():
            self.sidebar_open = False
        if view != "dashboard":
            self.dashboard_library_open = False
        self.render()

    def build_primary_nav(self) -> ft.Control:
        tabs = [
            ("dashboard", "dashboard"),
            ("learn", "learn"),
            ("library", "library"),
            ("import", "import"),
            ("settings", "settings"),
            ("calendar", "calendar"),
        ]
        return ft.Row(
            spacing=8,
            wrap=True,
            controls=[
                ft.Container(
                    bgcolor=ACCENT_DIM if self.view == value else PANEL_ALT,
                    border=border_all(ACCENT if self.view == value else DIVIDER),
                    border_radius=PANEL_RADIUS,
                    padding=pad_symmetric(horizontal=14, vertical=8),
                    ink=True,
                    on_click=lambda _e, value=value: self.set_view(value),
                    content=ft.Text(label, color=TEXT, size=12),
                )
                for value, label in tabs
            ],
        )

    def set_deck(self, deck_id: str) -> None:
        if not self.data:
            return
        self.controller.set_active_deck(self.data.profile, deck_id)
        if self.is_compact_layout():
            self.sidebar_open = False
        self.reset_study_state(clear_selection=True)
        self.refresh_profile_view(self.data.profile.id)

    def set_daily_target(self, value: str) -> None:
        if not self.data:
            return
        self.controller.set_daily_target(self.data.profile, value)
        self.refresh_profile_view(self.data.profile.id)

    def set_scheduler_mode(self, value: str) -> None:
        if not self.data:
            return
        mode = self.controller.set_scheduler_mode(self.data.profile, value)
        if mode == PACKAGE_DR_SCHEDULER_MODE and not self.scheduler_status.package_available:
            self.add_status_log(
                "package mode requested, but the local SSP-MMC-FSRS runtime is unavailable in this environment",
                level="info",
            )
        self.refresh_profile_view(self.data.profile.id)

    def set_desired_retention(self, value: str) -> None:
        if not self.data:
            return
        self.controller.set_desired_retention(self.data.profile, value)
        self.refresh_profile_view(self.data.profile.id)

    def set_kanji_text_size(self, value: str) -> None:
        if not self.data:
            return
        self.controller.set_kanji_text_size(self.data.profile, value)
        self.refresh_profile_view(self.data.profile.id)

    def set_meaning_text_size(self, value: str) -> None:
        if not self.data:
            return
        self.controller.set_meaning_text_size(self.data.profile, value)
        self.refresh_profile_view(self.data.profile.id)

    def add_profile(self) -> None:
        profile = self.controller.create_profile(self.new_profile_name)
        if not profile:
            return
        self.new_profile_name = ""
        self.refresh_profile_view(profile.id)

    def set_new_profile_name(self, value: str) -> None:
        self.new_profile_name = value

    def switch_profile(self, profile_id: str | None) -> None:
        if not profile_id:
            return
        if self.is_compact_layout():
            self.sidebar_open = False
        self.reset_study_state(clear_selection=True)
        self.refresh_profile_view(profile_id)

    def toggle_sidebar(self) -> None:
        if self.is_compact_layout():
            self.sidebar_open = not self.sidebar_open
        else:
            self.sidebar_expanded = not self.sidebar_expanded
        self.render()

    def delete_current_profile(self) -> None:
        if not self.profile_id:
            return
        profile_name = self.data.profile.name if self.data else self.profile_id
        if not self.controller.delete_profile(self.profile_id):
            return
        self.reset_study_state(clear_selection=True)
        self.profile_id = None
        self.add_status_log(f"deleted profile {profile_name}")
        self.refresh_profile_view(None)

    def delete_current_deck(self) -> None:
        if not self.data or not self.data.deck:
            return
        deck_name = self.data.deck.name
        if not self.controller.delete_deck(self.data.deck.id):
            return
        self.reset_study_state(clear_selection=True)
        self.add_status_log(f"deleted deck {deck_name}")
        self.refresh_profile_view(self.profile_id)

    def toggle_selected(self, character: str) -> None:
        if not character:
            return
        if character in self.selected:
            self.selected.remove(character)
        else:
            self.selected.add(character)
        self.preview_character = character
        if self.view == "dashboard":
            self.render()
            self.restore_dashboard_grid_position()
            return
        self.load_active_stroke()
        self.refresh_dashboard_regions("actions", "filmstrip", "card", "footer")

    def handle_dashboard_grid_scroll(self, event: ft.OnScrollEvent) -> None:
        self.dashboard_grid_scroll_offset = float(event.pixels or 0.0)

    def restore_dashboard_grid_position(self) -> None:
        if not self.dashboard_grid:
            return
        try:
            self.dashboard_grid.scroll_to(offset=self.dashboard_grid_scroll_offset, duration=0)
        except AssertionError:
            pass

    def set_preview_character(self, character: str) -> None:
        if self.session or not character or character == self.preview_character:
            return
        self.play_token += 1
        self.preview_character = character
        self.flipped = False
        self.load_active_stroke()
        self.refresh_dashboard_regions("actions", "filmstrip", "card", "footer")

    def handle_filmstrip_scroll(self, event: ft.OnScrollEvent) -> None:
        del event

    def handle_filmstrip_wheel(self, event: ft.ScrollEvent) -> None:
        delta = float(event.scroll_delta_y or event.scroll_delta_x or 0.0)
        if delta == 0:
            return
        self.scroll_filmstrip(delta)

    def scroll_filmstrip(self, delta: float) -> None:
        if not self.filmstrip_list:
            return
        self.filmstrip_scroll_offset = max(0.0, self.filmstrip_scroll_offset + delta)
        try:
            self.filmstrip_list.scroll_to(
                offset=self.filmstrip_scroll_offset,
                duration=160,
                curve=ft.AnimationCurve.EASE_OUT,
            )
        except AssertionError:
            pass

    def restore_filmstrip_position(self) -> None:
        if not self.filmstrip_list:
            return
        try:
            self.filmstrip_list.scroll_to(offset=self.filmstrip_scroll_offset, duration=0)
        except AssertionError:
            pass

    def start_queue(self) -> None:
        if not self.data or not self.data.deck:
            return
        session = self.controller.start_queue_session(self.data)
        if not session:
            return
        self.view = "learn"
        self.begin_session(session)
        self.render()

    def start_manual(self) -> None:
        if not self.data or not self.data.deck or not self.selected:
            return
        session = self.controller.start_manual_session(self.data, self.selected, self.kanji)
        if not session:
            return
        self.view = "learn"
        self.begin_session(session)
        self.render()

    def start_named_queue(self, queue_name: str) -> None:
        if not self.data or not self.data.deck:
            return
        session = self.controller.start_named_queue_session(self.data, queue_name)
        if not session:
            return
        self.view = "learn"
        self.begin_session(session)
        self.render()

    def end_session(self) -> None:
        if self.session:
            self.session = self.controller.finish_session(self.session)
        if not self.is_compact_layout():
            self.sidebar_expanded = True
        self.reset_study_state()
        self.view = "dashboard"
        self.refresh_data(self.profile_id)
        self.render()

    def reset_session(self) -> None:
        """Restart the current session from its original pre-session state."""
        if not self.session:
            return
        if self.session_snapshot_cards:
            self.controller.restore_session_snapshot(
                self.session,
                self.session_snapshot_cards,
                self.session_snapshot_last_seen,
            )
        restarted = replace(
            self.session,
            started_at=now_ms(),
            ended_at=None,
            seen=[],
        )
        self.refresh_data(self.session.profile_id)
        self.session = restarted
        self.capture_session_snapshot(restarted)
        self.pos = 0
        self.flipped = False
        self.controller.save_session(restarted)
        self.ensure_active_seen()
        self.load_active_stroke()
        self.refresh_dashboard_regions("metrics", "actions", "filmstrip", "card", "session", "footer")

    def move_prev(self) -> None:
        if not self.kanji:
            return
        if not self.session:
            characters = [item.character for item in self.kanji]
            active = self.active_character()
            if not active or active not in characters:
                self.set_preview_character(characters[0])
                return
            self.set_preview_character(characters[max(0, characters.index(active) - 1)])
            return
        self.pos = max(0, self.pos - 1)
        self.flipped = False
        self.ensure_active_seen()
        self.load_active_stroke()
        self.refresh_dashboard_regions("filmstrip", "card", "footer")

    def move_next(self) -> None:
        if not self.kanji:
            return
        if not self.session:
            characters = [item.character for item in self.kanji]
            active = self.active_character()
            if not active or active not in characters:
                self.set_preview_character(characters[0])
                return
            self.set_preview_character(characters[min(len(characters) - 1, characters.index(active) + 1)])
            return
        self.pos = min(len(self.session.kanji) - 1, self.pos + 1)
        self.flipped = False
        self.ensure_active_seen()
        self.load_active_stroke()
        self.refresh_dashboard_regions("filmstrip", "card", "footer")

    def jump_to_session_character(self, character: str) -> None:
        if not self.session or character not in self.session.kanji:
            return
        self.pos = self.session.kanji.index(character)
        self.flipped = False
        self.ensure_active_seen()
        self.load_active_stroke()
        self.refresh_dashboard_regions("filmstrip", "card", "footer")

    def toggle_flip(self) -> None:
        if not self.active_character():
            return
        self.flipped = not self.flipped
        self.refresh_dashboard_regions("card")

    def submit_rating(self, rating: str) -> None:
        if not self.session:
            return
        active = self.active_character()
        if not active:
            return
        self.controller.rate_card(self.session.profile_id, self.session.deck_id, active, rating)
        at_end = self.pos >= len(self.session.kanji) - 1
        self.refresh_data(self.session.profile_id)
        if at_end:
            self.end_session()
            return
        self.pos += 1
        self.flipped = False
        self.ensure_active_seen()
        self.load_active_stroke()
        self.refresh_dashboard_regions("metrics", "actions", "filmstrip", "card", "session", "footer")

    def pick_import_files(self) -> None:
        self.pending_picker_action = "import"
        self.file_picker.pick_files(allow_multiple=True, allowed_extensions=["csv"])

    def pick_import_backup(self) -> None:
        self.pending_picker_action = "import_backup"
        self.file_picker.pick_files(allow_multiple=False, allowed_extensions=["json"])

    def pick_import_backup_copy(self) -> None:
        self.pending_picker_action = "import_backup_copy"
        self.file_picker.pick_files(allow_multiple=False, allowed_extensions=["json"])

    def on_files_picked(self, event: Any) -> None:
        action = self.pending_picker_action
        if action not in {"import", "import_backup", "import_backup_copy"}:
            return
        self.pending_picker_action = None
        files = getattr(event, "files", None) or []
        for picked in files:
            path = getattr(picked, "path", None)
            if path:
                if action == "import":
                    self.import_csv_path(Path(path))
                elif action == "import_backup_copy":
                    self.import_profile_backup_path(Path(path), as_copy=True)
                else:
                    self.import_profile_backup_path(Path(path), as_copy=False)

    def load_example(self) -> None:
        path = Path(__file__).resolve().parent.parent / "examples" / "example.csv"
        self.import_csv_path(path)

    def import_csv_path(self, path: Path) -> None:
        result = self.controller.import_deck(path)
        self.add_status_log(
            f"ok {result.filename}: deck created, {result.added} new, {result.merged} shared ({result.row_count} rows)",
            level="success",
        )
        self.refresh_profile_view(self.profile_id)

    def import_profile_backup_path(self, path: Path, *, as_copy: bool) -> None:
        try:
            result = self.controller.import_profile_backup(path, as_copy=as_copy)
        except ValueError as exc:
            self.add_status_log(f"error {path.name}: {exc}", level="error")
            self.render()
            return
        self.reset_study_state(clear_selection=True)
        outcome = "copied into new profile" if result.imported_as_copy else "restored profile"
        replace_note = " and replaced existing study data" if result.replaced_existing else ""
        self.add_status_log(
            f"ok {path.name}: {outcome} {result.profile_name} ({result.deck_count} decks, {result.card_count} cards){replace_note}",
            level="success",
        )
        self.refresh_profile_view(result.profile_id)

    def begin_export(self) -> None:
        if not self.data:
            return
        export_result = self.controller.prepare_profile_export(self.data.profile, "")
        self.pending_export_text = export_result.export_text
        self.pending_export_name = export_result.suggested_file_name
        self.pending_picker_action = "export"
        self.save_picker.save_file(file_name=self.pending_export_name, allowed_extensions=["json"])

    def on_save_picked(self, event: Any) -> None:
        if self.pending_picker_action != "export":
            return
        self.pending_picker_action = None
        path = getattr(event, "path", None)
        if not path or self.pending_export_text is None:
            return
        Path(path).write_text(self.pending_export_text, encoding="utf-8")
        self.add_status_log(f"exported profile to {Path(path).name}", level="success")
        self.pending_export_text = None
        self.render()

    def reset_all(self) -> None:
        self.controller.reset_all_data()
        self.reset_study_state(clear_selection=True)
        self.add_status_log("all local data cleared")
        self.refresh_profile_view(None)

    def shift_month(self, delta: int) -> None:
        month = self.month.month - 1 + delta
        year = self.month.year + month // 12
        month = month % 12 + 1
        self.month = datetime(year, month, 1)
        self.render()

    def ensure_app_shell(self) -> None:
        if self.main_host is not None and self.shell_host is not None:
            return
        self.main_host = ft.Container(expand=True)
        self.shell_host = ft.Container(expand=True)
        self.root.content = self.shell_host

    def build_shell_content(self) -> ft.Control:
        if not self.main_host:
            return ft.Container()
        return ft.Container(expand=True, content=self.main_host)

    def build_sidebar(self) -> ft.Control:
        return SidebarPanel(
            detail_visible=self.sidebar_detail_visible(),
            compact_layout=self.is_compact_layout(),
            focus_mode=self.in_focus_mode(),
            panel_width=None if self.is_compact_layout() else self.sidebar_panel_width(),
            view=self.view,
            profiles=self.profiles,
            profile_id=self.profile_id,
            new_profile_name=self.new_profile_name,
            data=self.data,
            on_toggle_sidebar=self.toggle_sidebar,
            on_set_view=self.set_view,
            on_switch_profile=self.switch_profile,
            on_new_profile_name_change=self.set_new_profile_name,
            on_add_profile=self.add_profile,
            on_delete_profile=self.delete_current_profile,
            on_set_deck=self.set_deck,
            on_delete_deck=self.delete_current_deck,
            on_daily_target_change=self.set_daily_target,
            on_scheduler_mode_change=self.set_scheduler_mode,
            on_desired_retention_change=self.set_desired_retention,
            on_import_backup=self.pick_import_backup,
            on_import_backup_copy=self.pick_import_backup_copy,
            on_begin_export=self.begin_export,
            scheduler_package_available=self.scheduler_status.package_available,
            scheduler_status_text=self.scheduler_status.status_text,
            scheduler_detail_text=self.scheduler_status.detail_text,
            builtin_scheduler_mode=DEFAULT_SCHEDULER_MODE,
            package_scheduler_mode=PACKAGE_DR_SCHEDULER_MODE,
        ).build()

    def build_main(self) -> ft.Control:
        if self.view == "learn":
            return self.build_learning_view()
        if self.view == "calendar":
            return self.build_calendar_view()
        if self.view == "library":
            return self.build_library_view()
        if self.view == "settings":
            return self.build_settings_view()
        if self.view == "import":
            return self.build_import_view()
        return self.build_dashboard_view()

    def ensure_dashboard_shell(self) -> None:
        if self.dashboard_root is not None:
            return
        self.dashboard_metrics_host = ft.Container()
        self.dashboard_actions_host = ft.Container()
        self.dashboard_filmstrip_host = ft.Container()
        self.dashboard_card_host = ft.Container(expand=True, alignment=align(0, 0))
        self.dashboard_session_host = ft.Container()
        self.dashboard_footer_host = ft.Container()
        self.dashboard_root = ft.Container(
            expand=True,
            padding=PAGE_PADDING,
            content=ft.Column(
                expand=True,
                controls=[
                    self.dashboard_metrics_host,
                    self.dashboard_actions_host,
                    self.dashboard_filmstrip_host,
                    self.dashboard_card_host,
                    self.dashboard_session_host,
                    self.dashboard_footer_host,
                ],
            ),
        )

    def refresh_dashboard_regions(self, *regions: str, update: bool = True) -> None:
        if self.view != "learn":
            if update:
                self.render()
            return

        self.ensure_dashboard_shell()
        hosts = [
            self.dashboard_metrics_host,
            self.dashboard_actions_host,
            self.dashboard_filmstrip_host,
            self.dashboard_card_host,
            self.dashboard_session_host,
            self.dashboard_footer_host,
        ]
        if any(host is None for host in hosts):
            return

        requested = set(regions or ("metrics", "actions", "filmstrip", "card", "session", "footer"))
        if "metrics" in requested and self.dashboard_metrics_host:
            self.dashboard_metrics_host.content = self.build_learning_top()

        if "actions" in requested and self.dashboard_actions_host:
            self.dashboard_actions_host.content = self.build_learning_actions()

        if "filmstrip" in requested and self.dashboard_filmstrip_host:
            self.dashboard_filmstrip_host.content = self.build_filmstrip()

        if "card" in requested and self.dashboard_card_host:
            self.dashboard_card_host.content = self.build_card()

        if "session" in requested and self.dashboard_session_host:
            self.dashboard_session_host.content = self.build_session_controls()

        if "footer" in requested and self.dashboard_footer_host:
            self.dashboard_footer_host.content = self.build_footer()

        if update:
            try:
                if self.dashboard_root:
                    self.dashboard_root.update()
                    if "filmstrip" in requested:
                        self.restore_filmstrip_position()
                else:
                    self.render()
            except AssertionError:
                self.render()

    def build_dashboard_view(self) -> ft.Control:
        header_component = self.build_dashboard_header_component()
        return ft.Container(
            expand=True,
            padding=PAGE_PADDING,
            content=ft.Column(
                spacing=16,
                controls=[
                    self.build_dashboard_top_bar(),
                    self.build_dashboard_summary_strip(),
                    header_component.build_metrics(),
                    header_component.build_actions(),
                    self.build_dashboard_selection_grid(),
                    ft.Text(
                        "Click re-learn, review, or new to jump straight into that queue.",
                        color=MUTED,
                        size=11,
                    ),
                ],
            ),
        )

    def build_learning_view(self) -> ft.Control:
        self.refresh_dashboard_regions("metrics", "actions", "filmstrip", "card", "session", "footer", update=False)
        return self.dashboard_root or ft.Container()

    def build_learning_top(self) -> ft.Control:
        progress_text = f"{self.pos + 1} / {len(self.session.kanji)}" if self.session else "browse deck"
        deck_name = self.data.deck.name if self.data and self.data.deck else "no deck selected"
        return ft.Container(
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=pad_symmetric(horizontal=16, vertical=12),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text("Anjani Kanji", color=TEXT, size=18, weight=ft.FontWeight.BOLD),
                            self.build_primary_nav(),
                        ],
                    ),
                    ft.Column(
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        controls=[
                            ft.Text(deck_name, color=TEXT_SOFT, size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(progress_text, color=ACCENT, size=14, weight=ft.FontWeight.BOLD),
                        ],
                    ),
                ],
            ),
        )

    def build_learning_actions(self) -> ft.Control:
        duration_controls: list[ft.Control] = [
            ft.Text("duration", color=MUTED, size=12),
            ft.TextField(
                value=str(self.duration_sec),
                width=88,
                on_submit=lambda e: self.set_duration(e.control.value),
                on_blur=lambda e: self.set_duration(e.control.value),
                color=TEXT,
                bgcolor=PANEL_ALT,
                border_color=DIVIDER,
                text_size=12,
            ),
            ft.Text("s", color=MUTED),
        ]
        if self.session:
            controls: list[ft.Control] = [
                ft.Text("space play | F flip | arrows move | 1-4 rate", color=TEXT_SOFT, size=12),
                *duration_controls,
                ft.ElevatedButton(
                    "reset session",
                    on_click=lambda _e: self.reset_session(),
                    bgcolor=PANEL_ALT,
                    color=TEXT,
                ),
                ft.ElevatedButton(
                    "end session",
                    on_click=lambda _e: self.end_session(),
                    bgcolor=PANEL_ALT,
                    color=TEXT,
                ),
            ]
        else:
            controls = [
                ft.Text("No active session. Start from the dashboard.", color=TEXT_SOFT, size=12),
            ]
        return ft.Container(
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=pad_symmetric(horizontal=14, vertical=10),
            content=ft.Row(
                wrap=True,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
                controls=controls,
            ),
        )

    def build_dashboard_top_bar(self, *, show_library_toggle: bool = True) -> ft.Control:
        return ft.Container(
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=pad_symmetric(horizontal=16, vertical=12),
            shadow=get_elevation_shadow(),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text("Anjani Kanji", color=TEXT, size=18, weight=ft.FontWeight.BOLD),
                            self.build_primary_nav(),
                        ],
                    ),
                ],
            ),
        )

    def build_dashboard_summary_strip(self) -> ft.Control:
        profile_name = self.data.profile.name if self.data else "no profile"
        deck_name = self.data.deck.name if self.data and self.data.deck else "no deck selected"
        if self.data and self.data.decks:
            deck_selector: ft.Control = ft.Dropdown(
                value=self.data.deck.id if self.data.deck else None,
                options=[ft.dropdown.Option(deck.id, deck.name) for deck in self.data.decks],
                on_change=lambda e: self.set_deck(e.control.value),
                text_style=ft.TextStyle(color=TEXT),
                bgcolor=PANEL_ALT,
                color=TEXT,
                border_color=DIVIDER,
                width=min(360, max(220, self.card_size() * 0.72)),
            )
        else:
            deck_selector = ft.Text("import a CSV to create a deck", color=TEXT_SOFT, size=12)
        return ft.Container(
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=pad_symmetric(horizontal=16, vertical=12),
            content=ft.Row(
                wrap=True,
                spacing=18,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(f"profile {profile_name}", color=TEXT_SOFT, size=12),
                    ft.Text(f"deck {deck_name}", color=TEXT_SOFT, size=12),
                    deck_selector,
                ],
            ),
        )

    def dashboard_tile_background(self, item: KanjiEntryView) -> str:
        """Choose a quiet study-status color for dashboard kanji tiles."""
        if item.practice_count == 0:
            return PANEL_SOFT
        if item.study_state == "relearning" or item.lapses >= 2:
            return "#35191D"
        if item.study_state == "review":
            return ACCENT_DIM
        return "#3A3213"

    def dashboard_tile_border(self, item: KanjiEntryView) -> str:
        if item.character in self.selected:
            return ACCENT
        if item.practice_count == 0:
            return DIVIDER
        if item.study_state == "relearning" or item.lapses >= 2:
            return "#B45357"
        if item.study_state == "review":
            return "#4ADE80"
        return "#D4B14A"

    def dashboard_tile_shadow(self, item: KanjiEntryView) -> ft.BoxShadow | None:
        """Add a subtle lift for selected dashboard tiles."""
        if item.character not in self.selected:
            return None
        return ft.BoxShadow(
            blur_radius=18,
            spread_radius=1,
            color="#34D39933",
            offset=ft.Offset(0, 6),
        )

    def build_dashboard_selection_grid(self) -> ft.Control:
        """Build the manual selection grid for dashboard practice."""
        if not self.kanji:
            return ft.Container(
                bgcolor=SURFACE,
                border=border_all(DIVIDER),
                border_radius=PANEL_RADIUS,
                padding=pad_symmetric(horizontal=16, vertical=16),
                content=ft.Text("Import a deck to start selecting kanji.", color=TEXT_SOFT, size=12),
            )
        tiles = [
            ft.Container(
                key=f"dashboard-grid-{item.character}",
                bgcolor=self.dashboard_tile_background(item),
                border=border_all(self.dashboard_tile_border(item), 2 if item.character in self.selected else 1),
                border_radius=PANEL_RADIUS,
                margin=ft.Margin(0, -4 if item.character in self.selected else 0, 0, 4 if item.character in self.selected else 0),
                padding=pad_symmetric(horizontal=8, vertical=8),
                shadow=self.dashboard_tile_shadow(item),
                ink=True,
                on_click=lambda _e, ch=item.character: self.toggle_selected(ch),
                tooltip=", ".join(item.meanings),
                content=ft.Stack(
                    expand=True,
                    controls=[
                        ft.Container(
                            alignment=align(0, 0),
                            content=ft.Text(item.character, color=TEXT, size=26, weight=ft.FontWeight.BOLD),
                        ),
                        ft.Container(
                            alignment=align(1, 1),
                            content=ft.Text(str(item.practice_count), color=TEXT_SOFT, size=10),
                        ),
                    ],
                ),
            )
            for item in self.kanji
        ]
        return ft.Container(
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=pad_symmetric(horizontal=12, vertical=12),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("manual selection", color=TEXT, size=13, weight=ft.FontWeight.BOLD),
                            ft.Text(f"{len(self.selected)} selected", color=TEXT_SOFT, size=11),
                        ],
                    ),
                    ft.Container(
                        height=420,
                        content=self._build_dashboard_grid_view(tiles),
                    ),
                ],
            ),
        )

    def _build_dashboard_grid_view(self, tiles: list[ft.Control]) -> ft.GridView:
        if self.dashboard_grid is None:
            self.dashboard_grid = ft.GridView(
                max_extent=72,
                spacing=8,
                run_spacing=8,
                child_aspect_ratio=1.0,
                controls=tiles,
                on_scroll=self.handle_dashboard_grid_scroll,
            )
        else:
            self.dashboard_grid.max_extent = 72
            self.dashboard_grid.spacing = 8
            self.dashboard_grid.run_spacing = 8
            self.dashboard_grid.child_aspect_ratio = 1.0
            self.dashboard_grid.controls = tiles
        return self.dashboard_grid

    def build_library_view(self) -> ft.Control:
        deck_rows = []
        if not self.data or not self.data.decks:
            deck_rows = [ft.Text("no decks yet - import a CSV", color=TEXT_SOFT, size=12)]
        else:
            for deck in self.data.decks:
                active = self.data.deck and self.data.deck.id == deck.id
                deck_rows.append(
                    ft.Container(
                        bgcolor=ACCENT_DIM if active else PANEL_ALT,
                        border=border_all(ACCENT if active else DIVIDER),
                        border_radius=PANEL_RADIUS,
                        padding=pad_symmetric(horizontal=12, vertical=10),
                        ink=True,
                        on_click=lambda _e, deck_id=deck.id: self.set_deck(deck_id),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(deck.name, color=TEXT, size=13),
                                ft.Text(f"{deck.count} cards", color=TEXT_SOFT, size=11),
                            ],
                        ),
                    )
                )
        return ft.Container(
            expand=True,
            padding=PAGE_PADDING,
            content=ft.Column(
                spacing=16,
                controls=[
                    self.build_dashboard_top_bar(show_library_toggle=False),
                    ft.Text("library", color=TEXT, size=22, weight=ft.FontWeight.BOLD),
                    ft.Text("Decks and deck-level stats live here. Import is separate.", color=TEXT_SOFT, size=12),
                    ft.Column(spacing=8, controls=deck_rows),
                ],
            ),
        )

    def build_settings_view(self) -> ft.Control:
        profile = self.data.profile if self.data else None
        return ft.Container(
            expand=True,
            padding=PAGE_PADDING,
            content=ft.Column(
                spacing=16,
                controls=[
                    self.build_dashboard_top_bar(show_library_toggle=False),
                    ft.Text("settings", color=TEXT, size=22, weight=ft.FontWeight.BOLD),
                    ft.Text("Adjust how Japanese and English text appears on the card.", color=TEXT_SOFT, size=12),
                    ft.Container(
                        bgcolor=SURFACE,
                        border=border_all(DIVIDER),
                        border_radius=PANEL_RADIUS,
                        padding=pad_symmetric(horizontal=16, vertical=14),
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Text("Japanese text size", color=TEXT, size=13),
                                ft.TextField(
                                    value=f"{profile.kanji_text_size:.0f}" if profile else "72",
                                    on_submit=lambda e: self.set_kanji_text_size(e.control.value),
                                    on_blur=lambda e: self.set_kanji_text_size(e.control.value),
                                    color=TEXT,
                                    bgcolor=PANEL_ALT,
                                    border_color=DIVIDER,
                                    text_size=12,
                                ),
                                ft.Text("Meaning text size", color=TEXT, size=13),
                                ft.TextField(
                                    value=f"{profile.meaning_text_size:.0f}" if profile else "26",
                                    on_submit=lambda e: self.set_meaning_text_size(e.control.value),
                                    on_blur=lambda e: self.set_meaning_text_size(e.control.value),
                                    color=TEXT,
                                    bgcolor=PANEL_ALT,
                                    border_color=DIVIDER,
                                    text_size=12,
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def toggle_dashboard_library(self) -> None:
        self.dashboard_library_open = not self.dashboard_library_open
        self.render()

    def build_dashboard_header_component(self) -> DashboardHeader:
        """Create the dashboard summary/action component from current app state."""
        model = self.controller.build_dashboard_summary_model(
            data=self.data,
            session=self.session,
            position=self.pos,
            selected_count=len(self.selected),
            duration_sec=self.duration_sec,
            focus_mode=self.in_focus_mode(),
        )
        return DashboardHeader(
            model=model,
            on_set_duration=self.set_duration,
            on_start_queue=self.start_queue,
            on_start_selected=self.start_manual,
            on_end_session=self.end_session,
            on_start_relearn=lambda: self.start_named_queue("relearn"),
            on_start_review=lambda: self.start_named_queue("review"),
            on_start_new=lambda: self.start_named_queue("new"),
        )

    def build_filmstrip(self) -> ft.Control:
        tile_size = self.filmstrip_tile_size()
        text_size = FILMSTRIP_TEXT_COMPACT if self.is_compact_layout() else FILMSTRIP_TEXT_DESKTOP
        tiles = self.build_filmstrip_tile_controls(tile_size, text_size)
        if self.filmstrip_list is None:
            self.filmstrip_list = ft.Row(
                spacing=FILMSTRIP_GAP,
                auto_scroll=False,
                scroll=ft.ScrollMode.HIDDEN,
                controls=tiles,
            )
        else:
            self.filmstrip_list.spacing = FILMSTRIP_GAP
            self.filmstrip_list.controls = tiles

        viewport_width = self.filmstrip_viewport_width()
        fade_width = self.filmstrip_fade_width()
        rail = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.CLICK,
            on_scroll=self.handle_filmstrip_wheel,
            content=ft.ShaderMask(
                blend_mode=ft.BlendMode.DST_IN,
                shader=ft.LinearGradient(
                    begin=ft.Alignment(-1, 0),
                    end=ft.Alignment(1, 0),
                    colors=[
                        ft.Colors.TRANSPARENT,
                        ft.Colors.BLACK,
                        ft.Colors.BLACK,
                        ft.Colors.TRANSPARENT,
                    ],
                    stops=[0.0, fade_width / viewport_width, 1.0 - fade_width / viewport_width, 1.0],
                ),
                content=ft.Container(
                    width=viewport_width,
                    height=tile_size,
                    content=self.filmstrip_list,
                ),
            ),
        )
        return ft.Container(
            bgcolor=SURFACE_RAISED,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=pad_symmetric(vertical=12),
            content=ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[rail]),
        )

    def build_filmstrip_tile_controls(self, tile_size: float, text_size: float) -> list[ft.Control]:
        if not self.kanji:
            return [ft.Text("no kanji yet - import a CSV", color=MUTED, size=12)]
        items = self.build_filmstrip_tiles()
        if not items:
            return [ft.Text("start a session from the dashboard", color=MUTED, size=12)]
        controls: list[ft.Control] = []
        for item in items:
            tile_action = (
                (lambda ch=item.character: self.jump_to_session_character(ch))
                if self.view == "learn" and self.session is not None
                else (lambda ch=item.character: self.set_preview_character(ch))
            )
            controls.append(
                ft.Container(
                    key=f"filmstrip-{item.character}",
                    width=tile_size,
                    height=tile_size,
                    bgcolor=ACCENT_DIM if item.active else SURFACE if item.selected else PANEL_SOFT,
                    border=border_all(ACCENT if item.active else DIVIDER),
                    border_radius=PANEL_RADIUS,
                    alignment=align(0, 0),
                    ink=True,
                    on_click=lambda _e, action=tile_action: action(),
                    tooltip=", ".join(item.meanings),
                    content=ft.Text(item.character, color=TEXT, size=text_size),
                )
            )
        return controls

    def build_filmstrip_tiles(self) -> list[FilmstripTileViewModel]:
        """Create typed tile state for the dashboard filmstrip."""
        active_character = self.active_character()
        if self.view == "learn" and self.session:
            kanji_map = {item.character: item for item in self.kanji}
            return [
                FilmstripTileViewModel(
                    character=character,
                    meanings=kanji_map.get(character).meanings if kanji_map.get(character) else [],
                    selected=False,
                    active=character == active_character,
                )
                for character in self.session.kanji
            ]
        if self.view == "learn":
            return []
        return [
            FilmstripTileViewModel(
                character=item.character,
                meanings=item.meanings,
                selected=item.character in self.selected,
                active=item.character == active_character,
            )
            for item in self.kanji
        ]

    def build_kanji_card_component(self) -> KanjiCard:
        """Create the study surface component from current app state."""
        model = self.controller.build_study_card_model(
            kanji=self.kanji,
            session=self.session,
            position=self.pos,
            active_character=self.active_character() if self.session is not None or self.view != "learn" else None,
            profile_id=self.profile_id,
            deck_id=self.data.deck.id if self.data and self.data.deck else None,
            flipped=self.flipped,
            focus_mode=self.in_focus_mode(),
            stroke_message=self.stroke_message,
            card_size=self.card_size(),
            canvas_size=self.canvas_size(),
            kanji_text_size=self.data.profile.kanji_text_size if self.data else 72.0,
            meaning_text_size=self.data.profile.meaning_text_size if self.data else 26.0,
            deck_total=self.data.total_cards if self.data else 0,
        )
        return KanjiCard(
            model=model,
            stroke_frame_set=self.stroke_frame_set,
            visible_strokes=self.visible_strokes,
            on_play=lambda: self.page.run_task(self.animate_strokes),
            on_flip=self.toggle_flip,
            on_prev=self.move_prev,
            on_next=self.move_next,
            on_select=lambda: self.toggle_selected(self.active_character() or ""),
            on_rate=self.submit_rating,
        )

    def build_card(self) -> ft.Control:
        return self.build_kanji_card_component().build_card()

    def build_session_controls(self) -> ft.Control:
        return self.build_kanji_card_component().build_session_controls()

    def action_button(self, label: str, action) -> ft.Control:
        return ft.ElevatedButton(label, on_click=lambda _e: action(), bgcolor=PANEL_ALT, color=TEXT)

    def build_footer(self) -> ft.Control:
        model = self.controller.build_study_card_model(
            kanji=self.kanji,
            session=self.session,
            position=self.pos,
            active_character=self.active_character() if self.session is not None or self.view != "learn" else None,
            profile_id=self.profile_id,
            deck_id=self.data.deck.id if self.data and self.data.deck else None,
            flipped=self.flipped,
            focus_mode=self.in_focus_mode(),
            stroke_message=self.stroke_message,
            card_size=self.card_size(),
            canvas_size=self.canvas_size(),
            kanji_text_size=self.data.profile.kanji_text_size if self.data else 72.0,
            meaning_text_size=self.data.profile.meaning_text_size if self.data else 26.0,
            deck_total=self.data.total_cards if self.data else 0,
        )
        if not model.active:
            return ft.Container(
                padding=pad_symmetric(vertical=2),
                content=ft.Text(
                    "Use the dashboard counts to jump straight into re-learn, review, or new cards.",
                    color=MUTED,
                    size=11,
                ),
            )
        details = [f"current {model.current_character}"]
        if self.session:
            details.extend([f"due {model.due_text}", f"session {model.session_text}"])
        elif model.current_character in self.selected:
            details.append("selected for custom session")
        return ft.Container(
            bgcolor=SURFACE,
            border=border_all(DIVIDER),
            border_radius=PANEL_RADIUS,
            padding=pad_symmetric(horizontal=12, vertical=8),
            content=ft.Row(
                wrap=True,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=14,
                controls=[ft.Text(item, color=MUTED, size=11) for item in details],
            ),
        )

    def build_import_view_component(self) -> ImportView:
        """Create the import screen component from current app state."""
        return ImportView(
            sources=self.controller.list_sources(),
            import_log=self.import_log,
            on_choose_files=self.pick_import_files,
            on_load_example=self.load_example,
            on_reset_all=self.reset_all,
        )

    def build_import_view(self) -> ft.Control:
        return ft.Container(
            expand=True,
            padding=PAGE_PADDING,
            content=ft.Column(
                spacing=16,
                controls=[
                    self.build_dashboard_top_bar(show_library_toggle=False),
                    self.build_import_view_component().build(),
                ],
            ),
        )

    def build_calendar_view_component(self) -> CalendarView:
        """Create the calendar screen component from current app state."""
        calendar_data: CalendarStudyData = self.controller.calendar_study_data(self.profile_id)

        return CalendarView(
            month=self.month,
            by_day=calendar_data.by_day,
            session_count=calendar_data.session_count,
            on_prev_month=lambda: self.shift_month(-1),
            on_next_month=lambda: self.shift_month(1),
        )

    def build_calendar_view(self) -> ft.Control:
        return ft.Container(
            expand=True,
            padding=PAGE_PADDING,
            content=ft.Column(
                spacing=16,
                controls=[
                    self.build_dashboard_top_bar(show_library_toggle=False),
                    self.build_calendar_view_component().build(),
                ],
            ),
        )

    def set_duration(self, value: str) -> None:
        try:
            self.duration_sec = max(0.5, float(value))
        except ValueError:
            pass
        if self.view == "dashboard":
            self.refresh_dashboard_regions("actions")
        else:
            self.render()

    def render(self) -> None:
        self.ensure_app_shell()
        if self.main_host:
            self.main_host.content = self.build_main()
        if self.shell_host:
            self.shell_host.content = self.build_shell_content()
        try:
            self.root.update()
        except AssertionError:
            self.page.update()
        if self.view == "dashboard":
            self.restore_dashboard_grid_position()


def main(page: ft.Page) -> None:
    app = AnjaniKanjiDesktop(page)

    async def on_keyboard(event: ft.KeyboardEvent) -> None:
        if event.key == "Arrow Left":
            if app.session:
                app.move_prev()
            elif app.view == "learn":
                app.move_prev()
            elif app.view == "dashboard":
                app.scroll_filmstrip(-(app.filmstrip_tile_size() + FILMSTRIP_GAP))
        elif event.key == "Arrow Right":
            if app.session:
                app.move_next()
            elif app.view == "learn":
                app.move_next()
            elif app.view == "dashboard":
                app.scroll_filmstrip(app.filmstrip_tile_size() + FILMSTRIP_GAP)
        elif event.key == " ":
            await app.animate_strokes()
        elif event.key.lower() == "f":
            app.toggle_flip()
        elif event.key.lower() == "s" and app.active_character():
            app.toggle_selected(app.active_character() or "")
        elif event.key == "1":
            app.submit_rating("again")
        elif event.key == "2":
            app.submit_rating("hard")
        elif event.key == "3":
            app.submit_rating("good")
        elif event.key == "4":
            app.submit_rating("easy")

    page.on_keyboard_event = lambda e: page.run_task(on_keyboard, e)

