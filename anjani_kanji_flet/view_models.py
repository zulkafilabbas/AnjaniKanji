"""Typed UI-facing view models for the Anjani Kanji desktop app."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KanjiEntryView:
    """Minimal kanji data needed by the desktop UI."""

    character: str
    meanings: list[str]
    last_seen_at: int | None
    practice_count: int
    study_state: str
    lapses: int


@dataclass(frozen=True, slots=True)
class StudyCardViewModel:
    """Typed state consumed by the study card component."""

    active: KanjiEntryView | None
    flipped: bool
    focus_mode: bool
    session_active: bool
    current_character: str
    last_seen_text: str
    due_text: str
    session_text: str
    deck_total: int
    stroke_message: str
    card_size: float
    canvas_size: float
    kanji_text_size: float
    flipped_kanji_text_size: float
    meaning_text_size: float
    kanji_font_family: str
    meaning_font_family: str


@dataclass(frozen=True, slots=True)
class FilmstripTileViewModel:
    """Typed state consumed by each kanji filmstrip tile."""

    character: str
    meanings: list[str]
    selected: bool
    active: bool


@dataclass(frozen=True, slots=True)
class DashboardSummaryViewModel:
    """Typed state consumed by the dashboard summary and action header."""

    focus_mode: bool
    deck_name: str
    progress_text: str
    relearn_count: int
    review_count: int
    new_count: int
    studied_today: int
    queue_total: int
    selected_count: int
    duration_sec: float
    queue_hint_text: str
    next_due_text: str


@dataclass(frozen=True, slots=True)
class StatusLogEntryViewModel:
    """Typed status/log entry shown in the import and backup activity log."""

    level: str
    message: str
