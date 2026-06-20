"""Light controller layer for app actions that touch storage."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from ..csv_utils import parse_csv, rows_to_kanji
from ..fsrs_scheduler import DEFAULT_DESIRED_RETENTION, DEFAULT_SCHEDULER_MODE, PACKAGE_DR_SCHEDULER_MODE
from ..scheduler_runtime import SchedulerRuntimeStatus, scheduler_runtime_status
from ..storage import CardState, DashboardData, Profile, Session, Source, day_key, now_ms, new_session, queue_characters, queue_mode, relative_time
from ..view_models import DashboardSummaryViewModel, KanjiEntryView, StudyCardViewModel


@dataclass(slots=True)
class ImportDeckResult:
    """Summarize a completed deck import for the UI layer."""

    filename: str
    row_count: int
    added: int
    merged: int
    deck_id: str


@dataclass(slots=True)
class ExportProfileResult:
    """Summarize a prepared profile export for the UI layer."""

    profile_id: str
    profile_name: str
    export_text: str
    suggested_file_name: str


@dataclass(slots=True)
class ImportProfileResult:
    """Summarize a completed profile backup import for the UI layer."""

    profile_id: str
    profile_name: str
    deck_count: int
    card_count: int
    imported_as_copy: bool
    replaced_existing: bool


@dataclass(slots=True)
class DashboardStateResult:
    """Bundle the dashboard-facing state assembled from storage."""

    profiles: list[Profile]
    profile_id: str | None
    data: DashboardData | None
    kanji: list[KanjiEntryView]


@dataclass(slots=True)
class CalendarStudyData:
    """Provide calendar activity grouped by day for one profile."""

    by_day: dict[str, set[str]]
    session_count: int


class StudyController:
    """Coordinate storage-backed study and deck actions for the UI."""

    def __init__(self, storage) -> None:
        self.storage = storage

    def create_profile(self, name: str) -> Profile | None:
        """Create a profile when given a non-empty name."""
        cleaned = name.strip()
        if not cleaned:
            return None
        return self.storage.create_profile(cleaned)

    def load_dashboard_state(
        self, current_profile_id: str | None = None, next_profile_id: str | None = None
    ) -> DashboardStateResult:
        """Load the profile list, active dashboard data, and filtered kanji for the UI."""
        profiles = self.storage.all_profiles()
        profile_id = next((profile.id for profile in profiles if profile.id == next_profile_id), None) if next_profile_id else current_profile_id
        if not profile_id and profiles:
            profile_id = profiles[0].id
        if not profile_id:
            return DashboardStateResult(profiles=profiles, profile_id=None, data=None, kanji=[])

        data = self.storage.dashboard_data(profile_id)
        active_deck_id = data.deck.id if data.deck else None
        cards_by_character = (
            {card.character: card for card in self.storage.cards_for_deck(profile_id, active_deck_id)}
            if active_deck_id
            else {}
        )
        kanji = [
            KanjiEntryView(
                character=item.character,
                meanings=item.meanings,
                last_seen_at=item.last_seen_at,
                practice_count=cards_by_character[item.character].reps if item.character in cards_by_character else 0,
                study_state=cards_by_character[item.character].state if item.character in cards_by_character else "new",
                lapses=cards_by_character[item.character].lapses if item.character in cards_by_character else 0,
            )
            for item in self.storage.all_kanji(active_deck_id)
        ]
        return DashboardStateResult(profiles=profiles, profile_id=profile_id, data=data, kanji=kanji)

    def list_sources(self) -> list[Source]:
        """Return imported CSV sources for the import screen."""
        return self.storage.all_sources()

    def calendar_study_data(self, profile_id: str | None) -> CalendarStudyData:
        """Return study activity grouped by day for the calendar view."""
        sessions = self.storage.all_sessions(profile_id)
        by_day: dict[str, set[str]] = {}
        for session in sessions:
            key = day_key(session.started_at)
            by_day.setdefault(key, set()).update(session.seen)
        return CalendarStudyData(by_day=by_day, session_count=len(sessions))

    def build_study_card_model(
        self,
        *,
        kanji: list[KanjiEntryView],
        session: Session | None,
        position: int,
        active_character: str | None,
        profile_id: str | None,
        deck_id: str | None,
        flipped: bool,
        focus_mode: bool,
        stroke_message: str,
        card_size: float,
        canvas_size: float,
        kanji_text_size: float,
        flipped_kanji_text_size: float,
        meaning_text_size: float,
        kanji_font_family: str,
        meaning_font_family: str,
        deck_total: int,
    ) -> StudyCardViewModel:
        """Build the typed study-card state used by the flashcard component."""
        active = self._active_kanji_entry(kanji, active_character)
        active_card = self._active_card(session, profile_id, deck_id, active_character)
        return StudyCardViewModel(
            active=active,
            flipped=flipped,
            focus_mode=focus_mode,
            session_active=session is not None,
            current_character=active_character or "-",
            last_seen_text=relative_time(active.last_seen_at) if active else "-",
            due_text=self._due_text(active_card),
            session_text=f"{position + 1} / {len(session.kanji)}" if session else "-",
            deck_total=deck_total,
            stroke_message=stroke_message,
            card_size=card_size,
            canvas_size=canvas_size,
            kanji_text_size=kanji_text_size,
            flipped_kanji_text_size=flipped_kanji_text_size,
            meaning_text_size=meaning_text_size,
            kanji_font_family=kanji_font_family,
            meaning_font_family=meaning_font_family,
        )

    def build_dashboard_summary_model(
        self,
        *,
        data: DashboardData | None,
        session: Session | None,
        position: int,
        selected_count: int,
        duration_sec: float,
        focus_mode: bool,
    ) -> DashboardSummaryViewModel:
        """Build the typed dashboard summary model shown above the study surface."""
        relearn_count = len(data.relearn_queue) if data else 0
        review_count = len(data.review_queue) if data else 0
        new_count = len(data.new_queue) if data else 0
        queue_total = relearn_count + review_count + new_count
        next_due_text = self._next_due_text(data.next_due_at if data else None)
        if not data or not data.deck:
            queue_hint_text = "daily queue builds automatically once you import and select a deck"
        elif queue_total > 0:
            queue_hint_text = (
                f"auto-queue = {relearn_count} re-learn due now + "
                f"{review_count} review due now + {new_count} new today"
            )
        elif next_due_text != "-":
            queue_hint_text = "nothing is due right now; the next scheduled review starts automatically when it unlocks"
        else:
            queue_hint_text = "nothing is due right now; new cards appear here up to your daily cap"

        return DashboardSummaryViewModel(
            focus_mode=focus_mode,
            deck_name=data.deck.name if data and data.deck else "session",
            progress_text=f"{position + 1} / {len(session.kanji)}" if session else "-",
            relearn_count=relearn_count,
            review_count=review_count,
            new_count=new_count,
            studied_today=data.studied_today if data else 0,
            queue_total=queue_total,
            selected_count=selected_count,
            duration_sec=duration_sec,
            queue_hint_text=queue_hint_text,
            next_due_text=next_due_text,
        )

    def set_active_deck(self, profile: Profile, deck_id: str) -> None:
        """Persist the active deck selection."""
        profile.active_deck_id = deck_id
        self.storage.update_profile(profile)

    def set_daily_target(self, profile: Profile, value: str) -> int:
        """Persist the daily new-card target and return the final value."""
        try:
            target = max(0, min(200, int(value)))
        except ValueError:
            target = profile.daily_new_target
        profile.daily_new_target = target
        self.storage.update_profile(profile)
        return target

    def set_scheduler_mode(self, profile: Profile, value: str) -> str:
        """Persist the selected scheduler mode for a profile."""
        cleaned = value.strip()
        if cleaned not in {DEFAULT_SCHEDULER_MODE, PACKAGE_DR_SCHEDULER_MODE}:
            cleaned = DEFAULT_SCHEDULER_MODE
        profile.scheduler_mode = cleaned
        self.storage.update_profile(profile)
        return cleaned

    def set_desired_retention(self, profile: Profile, value: str) -> float:
        """Persist desired retention and return the clamped value."""
        try:
            retention = float(value)
        except ValueError:
            retention = profile.desired_retention
        retention = max(0.7, min(0.99, retention))
        profile.desired_retention = retention
        self.storage.update_profile(profile)
        return retention

    def set_kanji_text_size(self, profile: Profile, value: str) -> float:
        """Persist the kanji font size and return the clamped value."""
        try:
            size = float(value)
        except ValueError:
            size = profile.kanji_text_size
        size = max(36.0, min(120.0, size))
        profile.kanji_text_size = size
        self.storage.update_profile(profile)
        return size

    def set_meaning_text_size(self, profile: Profile, value: str) -> float:
        """Persist the meaning font size and return the clamped value."""
        try:
            size = float(value)
        except ValueError:
            size = profile.meaning_text_size
        size = max(14.0, min(48.0, size))
        profile.meaning_text_size = size
        self.storage.update_profile(profile)
        return size

    def set_flipped_kanji_text_size(self, profile: Profile, value: str) -> float:
        """Persist the flipped kanji font size and return the clamped value."""
        try:
            size = float(value)
        except ValueError:
            size = profile.flipped_kanji_text_size
        size = max(12.0, min(48.0, size))
        profile.flipped_kanji_text_size = size
        self.storage.update_profile(profile)
        return size

    def set_kanji_font_family(self, profile: Profile, value: str) -> str:
        """Persist the Japanese font family."""
        profile.kanji_font_family = value.strip() or profile.kanji_font_family
        self.storage.update_profile(profile)
        return profile.kanji_font_family

    def set_meaning_font_family(self, profile: Profile, value: str) -> str:
        """Persist the meaning font family."""
        profile.meaning_font_family = value.strip() or profile.meaning_font_family
        self.storage.update_profile(profile)
        return profile.meaning_font_family

    def scheduler_status(self) -> SchedulerRuntimeStatus:
        """Return runtime package availability for the untouched local scheduler package."""
        return scheduler_runtime_status()

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile and its related records."""
        return self.storage.delete_profile(profile_id)

    def delete_deck(self, deck_id: str) -> bool:
        """Delete a deck and its related joins."""
        return self.storage.delete_deck(deck_id)

    def save_session(self, session: Session) -> None:
        """Persist the session snapshot."""
        self.storage.save_session(session)

    def finish_session(self, session: Session | None) -> Session | None:
        """Mark a session complete and persist it."""
        if not session:
            return None
        finished = replace(session, ended_at=now_ms())
        self.storage.save_session(finished)
        return finished

    def restore_session_snapshot(
        self,
        session: Session,
        cards_by_character: dict[str, CardState],
        kanji_last_seen: dict[str, int | None],
    ) -> None:
        """Restore card and kanji state for a reset session."""
        self.storage.restore_session_snapshot(
            profile_id=session.profile_id,
            deck_id=session.deck_id,
            started_at=session.started_at,
            cards=list(cards_by_character.values()),
            kanji_last_seen=kanji_last_seen,
        )

    def mark_seen(self, character: str) -> None:
        """Stamp a character as seen."""
        self.storage.mark_seen(character)

    def rate_card(self, profile_id: str, deck_id: str, character: str, rating: str) -> None:
        """Persist a rating event for the active card."""
        self.storage.rate_card(profile_id, deck_id, character, rating)

    def export_profile(self, profile_id: str, passphrase: str) -> str:
        """Build an export payload for a profile."""
        return self.storage.export_profile(profile_id, passphrase)

    def prepare_profile_export(self, profile: Profile, passphrase: str) -> ExportProfileResult:
        """Build export text and a suggested file name for a profile."""
        safe_name = profile.name.lower().replace(" ", "-")
        return ExportProfileResult(
            profile_id=profile.id,
            profile_name=profile.name,
            export_text=self.storage.export_profile(profile.id, passphrase),
            suggested_file_name=f"{safe_name}-kanji-profile.json",
        )

    def load_profile_export(self, export_text: str, passphrase: str = "") -> dict[str, object]:
        """Decode a profile backup payload for future restore/import flows."""
        return self.storage.load_export_payload(export_text, passphrase)

    def import_profile_backup(self, path: Path, passphrase: str = "", *, as_copy: bool = False) -> ImportProfileResult:
        """Read a profile backup file and import its payload."""
        export_text = path.read_text(encoding="utf-8")
        payload = self.storage.load_export_payload(export_text, passphrase)
        original_profile_id = str(payload["profile"]["id"])
        replaced_existing = any(profile.id == original_profile_id for profile in self.storage.all_profiles())
        profile = self.storage.import_profile_payload(payload, duplicate_profile=as_copy)
        return ImportProfileResult(
            profile_id=profile.id,
            profile_name=profile.name,
            deck_count=len(payload.get("decks", [])),
            card_count=len(payload.get("cards", [])),
            imported_as_copy=as_copy,
            replaced_existing=replaced_existing and not as_copy,
        )

    def reset_all_data(self) -> None:
        """Clear all local data and restore defaults."""
        self.storage.delete_all()

    def import_rows(self, filename: str, rows) -> tuple[int, int, str]:
        """Import parsed CSV rows into storage."""
        return self.storage.import_rows(filename, rows)

    def import_deck(self, path: Path) -> ImportDeckResult:
        """Read a CSV file from disk and import it as a deck."""
        text = path.read_text(encoding="utf-8", errors="ignore")
        rows = rows_to_kanji(parse_csv(text))
        added, merged, deck_id = self.storage.import_rows(path.name, rows)
        return ImportDeckResult(
            filename=path.name,
            row_count=len(rows),
            added=added,
            merged=merged,
            deck_id=deck_id,
        )

    def start_queue_session(self, data: DashboardData) -> Session | None:
        """Build a daily queue session from the dashboard queues."""
        if not data.deck:
            return None
        queue = queue_characters(data.relearn_queue, data.review_queue, data.new_queue)
        if not queue:
            return None
        return new_session(
            queue_mode(data.relearn_queue, data.review_queue, data.new_queue),
            queue,
            len(queue),
            data.profile.id,
            data.deck.id,
        )

    def start_named_queue_session(self, data: DashboardData, queue_name: str) -> Session | None:
        """Build a session from one dashboard queue only."""
        if not data.deck:
            return None
        queue_map = {
            "relearn": data.relearn_queue,
            "review": data.review_queue,
            "new": data.new_queue,
        }
        cards = queue_map.get(queue_name, [])
        if not cards:
            return None
        queue = [card.character for card in cards]
        return new_session(queue_name, queue, len(queue), data.profile.id, data.deck.id)

    def start_manual_session(
        self, data: DashboardData, selected: set[str], kanji: list[KanjiEntryView]
    ) -> Session | None:
        """Build a manual session from the current selection."""
        if not data.deck or not selected:
            return None
        ordered = [item.character for item in kanji if item.character in selected]
        if not ordered:
            return None
        return new_session("manual", ordered, len(ordered), data.profile.id, data.deck.id)

    def _active_character(self, session: Session | None, position: int) -> str | None:
        """Return the current session character for a queue position."""
        if not session or position < 0 or position >= len(session.kanji):
            return None
        return session.kanji[position]

    def _active_kanji_entry(self, kanji: list[KanjiEntryView], character: str | None) -> KanjiEntryView | None:
        """Find the current kanji entry in the active filtered list."""
        if not character:
            return None
        for item in kanji:
            if item.character == character:
                return item
        return None

    def _active_card(
        self,
        session: Session | None,
        profile_id: str | None,
        deck_id: str | None,
        character: str | None,
    ) -> CardState | None:
        """Fetch the current card state for the active session character."""
        if not character:
            return None
        if session:
            return self.storage.get_card(session.profile_id, session.deck_id, character)
        if not profile_id or not deck_id:
            return None
        return self.storage.get_card(profile_id, deck_id, character)

    def _due_text(self, card: CardState | None) -> str:
        """Format the current card due state for the study footer."""
        if not card:
            return "-"
        if card.state == "new":
            return "new"
        if card.due <= now_ms():
            return "now"
        return datetime.fromtimestamp(card.due / 1000).strftime("%Y-%m-%d %H:%M")

    def _next_due_text(self, due_at: int | None) -> str:
        """Format the next future dashboard review time."""
        if not due_at:
            return "-"
        if due_at <= now_ms():
            return "now"
        return datetime.fromtimestamp(due_at / 1000).strftime("%Y-%m-%d %H:%M")
