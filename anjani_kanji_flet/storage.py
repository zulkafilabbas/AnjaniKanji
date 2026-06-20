from __future__ import annotations

import base64
import json
import os
import sys
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar, cast

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidTag

from .fsrs_scheduler import (
    DEFAULT_DESIRED_RETENTION,
    DEFAULT_SCHEDULER_MODE,
    PACKAGE_DR_SCHEDULER_MODE,
    GRADE_BY_RATING,
    schedule_fsrs,
)
from .scheduler_runtime import is_package_mode, package_dr_interval_days


DEFAULT_PROFILE_ID = "local-default"
DEFAULT_DECK_ID = "deck-default"
F = TypeVar("F", bound=Callable[..., Any])
APP_DIR_NAME = "AnjaniKanji"
APP_DB_NAME = "anjani_kanji.db"


def data_dir() -> Path:
    """Return the canonical cross-platform app data directory."""
    return _preferred_data_dir()


def _preferred_data_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_DIR_NAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def db_path() -> Path:
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    preferred_path = root / APP_DB_NAME
    return preferred_path


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def day_start_ms(ts: int | None = None) -> int:
    dt = datetime.fromtimestamp((ts or now_ms()) / 1000)
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


@dataclass
class Profile:
    id: str
    name: str
    created_at: int
    daily_new_target: int
    active_deck_id: str | None
    scheduler_mode: str
    desired_retention: float


@dataclass
class Deck:
    id: str
    name: str
    filename: str
    imported_at: int
    count: int
    characters: list[str]


@dataclass
class Kanji:
    character: str
    meanings: list[str]
    sources: list[str]
    deck_ids: list[str]
    created_at: int
    last_seen_at: int | None


@dataclass
class CardState:
    id: str
    profile_id: str
    deck_id: str
    character: str
    state: str
    stability: float
    difficulty: float
    retrievability: float
    due: int
    elapsed_days: int
    scheduled_days: int
    reps: int
    lapses: int
    last_review: int | None
    relearn_until: int | None
    created_at: int


@dataclass
class Session:
    id: str
    profile_id: str
    deck_id: str
    started_at: int
    ended_at: int | None
    mode: str
    sample_size: int
    kanji: list[str]
    seen: list[str]


@dataclass
class Source:
    filename: str
    imported_at: int
    count: int
    deck_id: str | None


@dataclass
class DashboardData:
    profile: Profile
    deck: Deck | None
    decks: list[Deck]
    new_queue: list[CardState]
    review_queue: list[CardState]
    relearn_queue: list[CardState]
    total_cards: int
    studied_today: int
    next_due_at: int | None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def _card_id(profile_id: str, deck_id: str, character: str) -> str:
    return f"{profile_id}::{deck_id}::{character}"


def _initial_card(profile_id: str, deck_id: str, character: str, created_at: int | None = None) -> CardState:
    return CardState(
        id=_card_id(profile_id, deck_id, character),
        profile_id=profile_id,
        deck_id=deck_id,
        character=character,
        state="new",
        stability=0.0,
        difficulty=5.0,
        retrievability=0.0,
        due=0,
        elapsed_days=0,
        scheduled_days=0,
        reps=0,
        lapses=0,
        last_review=None,
        relearn_until=None,
        created_at=created_at or now_ms(),
    )


def synchronized(method: F) -> F:
    @wraps(method)
    def wrapper(self: "AppStorage", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return cast(F, wrapper)


class AppStorage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    @synchronized
    def close(self) -> None:
        self.conn.close()

    @synchronized
    def _migrate(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=30000;

            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                daily_new_target INTEGER NOT NULL,
                active_deck_id TEXT,
                scheduler_mode TEXT NOT NULL DEFAULT 'fsrs',
                desired_retention REAL NOT NULL DEFAULT 0.9
            );

            CREATE TABLE IF NOT EXISTS decks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                filename TEXT NOT NULL,
                imported_at INTEGER NOT NULL,
                count INTEGER NOT NULL,
                characters_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kanji (
                character TEXT PRIMARY KEY,
                meanings_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                deck_ids_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_seen_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                deck_id TEXT NOT NULL,
                character TEXT NOT NULL,
                state TEXT NOT NULL,
                stability REAL NOT NULL,
                difficulty REAL NOT NULL,
                retrievability REAL NOT NULL,
                due INTEGER NOT NULL,
                elapsed_days INTEGER NOT NULL,
                scheduled_days INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                lapses INTEGER NOT NULL,
                last_review INTEGER,
                relearn_until INTEGER,
                created_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cards_profile_deck_due
            ON cards (profile_id, deck_id, due);

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                deck_id TEXT NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER,
                mode TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                kanji_json TEXT NOT NULL,
                seen_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sources (
                filename TEXT NOT NULL,
                imported_at INTEGER NOT NULL,
                count INTEGER NOT NULL,
                deck_id TEXT,
                PRIMARY KEY (filename, imported_at)
            );

            CREATE TABLE IF NOT EXISTS review_logs (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                deck_id TEXT NOT NULL,
                character TEXT NOT NULL,
                rating TEXT NOT NULL,
                reviewed_at INTEGER NOT NULL,
                previous_due INTEGER NOT NULL,
                next_due INTEGER NOT NULL,
                stability REAL NOT NULL,
                difficulty REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stroke_cache (
                character TEXT PRIMARY KEY,
                svg TEXT NOT NULL,
                cached_at INTEGER NOT NULL
            );
            """
        )
        profile_columns = {
            str(row["name"])
            for row in cur.execute("PRAGMA table_info(profiles)").fetchall()
        }
        if "scheduler_mode" not in profile_columns:
            cur.execute("ALTER TABLE profiles ADD COLUMN scheduler_mode TEXT NOT NULL DEFAULT 'fsrs'")
        if "desired_retention" not in profile_columns:
            cur.execute("ALTER TABLE profiles ADD COLUMN desired_retention REAL NOT NULL DEFAULT 0.9")
        self.conn.commit()
        self.ensure_default_profile()

    @synchronized
    def ensure_default_profile(self) -> Profile:
        row = self.conn.execute("SELECT * FROM profiles WHERE id = ?", (DEFAULT_PROFILE_ID,)).fetchone()
        if row:
            profile = self._profile_from_row(row)
            self._ensure_profile_cards(profile)
            return profile
        created_at = now_ms()
        first_deck = self.conn.execute("SELECT id FROM decks ORDER BY imported_at DESC LIMIT 1").fetchone()
        profile = Profile(
            id=DEFAULT_PROFILE_ID,
            name="Local",
            created_at=created_at,
            daily_new_target=10,
            active_deck_id=first_deck["id"] if first_deck else None,
            scheduler_mode=DEFAULT_SCHEDULER_MODE,
            desired_retention=DEFAULT_DESIRED_RETENTION,
        )
        self.conn.execute(
            """
            INSERT INTO profiles
            (id, name, created_at, daily_new_target, active_deck_id, scheduler_mode, desired_retention)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.id,
                profile.name,
                profile.created_at,
                profile.daily_new_target,
                profile.active_deck_id,
                profile.scheduler_mode,
                profile.desired_retention,
            ),
        )
        self.conn.commit()
        self._ensure_profile_cards(profile)
        return profile

    @synchronized
    def _ensure_profile_cards(self, profile: Profile) -> None:
        decks = self.all_decks()
        for deck in decks:
            for character in deck.characters:
                card_id = _card_id(profile.id, deck.id, character)
                exists = self.conn.execute("SELECT 1 FROM cards WHERE id = ?", (card_id,)).fetchone()
                if exists:
                    continue
                card = _initial_card(profile.id, deck.id, character)
                self._upsert_card(card)
        self.conn.commit()

    @synchronized
    def all_profiles(self) -> list[Profile]:
        rows = self.conn.execute("SELECT * FROM profiles ORDER BY created_at ASC").fetchall()
        if not rows:
            return [self.ensure_default_profile()]
        profiles = [self._profile_from_row(row) for row in rows]
        for profile in profiles:
            self._ensure_profile_cards(profile)
        return profiles

    @synchronized
    def create_profile(self, name: str) -> Profile:
        decks = self.all_decks()
        profile = Profile(
            id=str(uuid.uuid4()),
            name=name.strip() or "Profile",
            created_at=now_ms(),
            daily_new_target=10,
            active_deck_id=decks[0].id if decks else None,
            scheduler_mode=DEFAULT_SCHEDULER_MODE,
            desired_retention=DEFAULT_DESIRED_RETENTION,
        )
        self.conn.execute(
            """
            INSERT INTO profiles
            (id, name, created_at, daily_new_target, active_deck_id, scheduler_mode, desired_retention)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.id,
                profile.name,
                profile.created_at,
                profile.daily_new_target,
                profile.active_deck_id,
                profile.scheduler_mode,
                profile.desired_retention,
            ),
        )
        for deck in decks:
            for character in deck.characters:
                self._upsert_card(_initial_card(profile.id, deck.id, character))
        self.conn.commit()
        return profile

    @synchronized
    def update_profile(self, profile: Profile) -> None:
        self.conn.execute(
            """
            UPDATE profiles
            SET name = ?, daily_new_target = ?, active_deck_id = ?, scheduler_mode = ?, desired_retention = ?
            WHERE id = ?
            """,
            (
                profile.name,
                profile.daily_new_target,
                profile.active_deck_id,
                profile.scheduler_mode,
                profile.desired_retention,
                profile.id,
            ),
        )
        self.conn.commit()

    @synchronized
    def all_decks(self) -> list[Deck]:
        rows = self.conn.execute("SELECT * FROM decks ORDER BY imported_at DESC").fetchall()
        return [self._deck_from_row(row) for row in rows]

    @synchronized
    def all_sources(self) -> list[Source]:
        rows = self.conn.execute("SELECT * FROM sources ORDER BY imported_at DESC").fetchall()
        return [
            Source(
                filename=row["filename"],
                imported_at=row["imported_at"],
                count=row["count"],
                deck_id=row["deck_id"],
            )
            for row in rows
        ]

    @synchronized
    def all_kanji(self, deck_id: str | None = None) -> list[Kanji]:
        rows = self.conn.execute("SELECT * FROM kanji ORDER BY created_at ASC").fetchall()
        kanji = [self._kanji_from_row(row) for row in rows]
        if deck_id:
            return [item for item in kanji if deck_id in item.deck_ids]
        return kanji

    @synchronized
    def cards_for_deck(self, profile_id: str, deck_id: str) -> list[CardState]:
        rows = self.conn.execute(
            "SELECT * FROM cards WHERE profile_id = ? AND deck_id = ? ORDER BY created_at ASC",
            (profile_id, deck_id),
        ).fetchall()
        return [self._card_from_row(row) for row in rows]

    @synchronized
    def get_card(self, profile_id: str, deck_id: str, character: str) -> CardState | None:
        row = self.conn.execute(
            "SELECT * FROM cards WHERE id = ?",
            (_card_id(profile_id, deck_id, character),),
        ).fetchone()
        return self._card_from_row(row) if row else None

    @synchronized
    def dashboard_data(self, profile_id: str | None = None) -> DashboardData:
        fallback = self.ensure_default_profile()
        if profile_id:
            row = self.conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
            profile = self._profile_from_row(row) if row else fallback
        else:
            profile = fallback
        self._ensure_profile_cards(profile)
        decks = self.all_decks()
        deck = next((item for item in decks if item.id == profile.active_deck_id), decks[0] if decks else None)
        if not deck:
            return DashboardData(
                profile=profile,
                deck=None,
                decks=decks,
                new_queue=[],
                review_queue=[],
                relearn_queue=[],
                total_cards=0,
                studied_today=0,
                next_due_at=None,
            )
        cards = self.cards_for_deck(profile.id, deck.id)
        now = now_ms()
        relearn = sorted(
            [card for card in cards if card.state == "relearning" and (card.relearn_until or card.due) <= now],
            key=lambda card: (card.relearn_until or card.due),
        )
        review = sorted(
            [card for card in cards if card.state == "review" and card.due <= now],
            key=lambda card: (card.stability, card.due),
        )
        fresh = sorted(
            [card for card in cards if card.state == "new"],
            key=lambda card: card.created_at,
        )[: profile.daily_new_target]
        studied_today = len([card for card in cards if (card.last_review or 0) >= day_start_ms(now)])
        future_due = [
            (card.relearn_until or card.due)
            for card in cards
            if card.state in {"relearning", "review"} and (card.relearn_until or card.due) > now
        ]
        return DashboardData(
            profile=profile,
            deck=deck,
            decks=decks,
            new_queue=fresh,
            review_queue=review,
            relearn_queue=relearn,
            total_cards=len(cards),
            studied_today=studied_today,
            next_due_at=min(future_due) if future_due else None,
        )

    @synchronized
    def import_rows(self, filename: str, rows: list[dict[str, object]]) -> tuple[int, int, str]:
        current = now_ms()
        deck_id = str(uuid.uuid4())
        characters: list[str] = []
        added = 0
        merged = 0
        for row in rows:
            character = str(row["character"])
            meanings = [str(item) for item in row["meanings"]]
            if character not in characters:
                characters.append(character)
            existing_row = self.conn.execute("SELECT * FROM kanji WHERE character = ?", (character,)).fetchone()
            if existing_row:
                existing = self._kanji_from_row(existing_row)
                merged_meanings = list(dict.fromkeys([*existing.meanings, *meanings]))
                merged_sources = list(dict.fromkeys([*existing.sources, filename]))
                merged_decks = list(dict.fromkeys([*existing.deck_ids, deck_id]))
                self.conn.execute(
                    """
                    UPDATE kanji
                    SET meanings_json = ?, sources_json = ?, deck_ids_json = ?, last_seen_at = ?
                    WHERE character = ?
                    """,
                    (
                        _json(merged_meanings),
                        _json(merged_sources),
                        _json(merged_decks),
                        existing.last_seen_at,
                        character,
                    ),
                )
                merged += 1
            else:
                self.conn.execute(
                    """
                    INSERT INTO kanji (character, meanings_json, sources_json, deck_ids_json, created_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (character, _json(meanings), _json([filename]), _json([deck_id]), current + added, None),
                )
                added += 1
        deck = Deck(id=deck_id, name=filename.removesuffix(".csv"), filename=filename, imported_at=current, count=len(characters), characters=characters)
        self.conn.execute(
            "INSERT INTO decks (id, name, filename, imported_at, count, characters_json) VALUES (?, ?, ?, ?, ?, ?)",
            (deck.id, deck.name, deck.filename, deck.imported_at, deck.count, _json(deck.characters)),
        )
        self.conn.execute(
            "INSERT INTO sources (filename, imported_at, count, deck_id) VALUES (?, ?, ?, ?)",
            (filename, current, len(rows), deck_id),
        )
        profiles = self.all_profiles()
        for profile in profiles:
            if not profile.active_deck_id:
                profile.active_deck_id = deck_id
                self.update_profile(profile)
            for character in characters:
                self._upsert_card(_initial_card(profile.id, deck_id, character, current))
        self.conn.commit()
        return added, merged, deck_id

    @synchronized
    def mark_seen(self, character: str, when: int | None = None) -> None:
        stamp = when or now_ms()
        self.conn.execute("UPDATE kanji SET last_seen_at = ? WHERE character = ?", (stamp, character))
        self.conn.commit()

    @synchronized
    def rate_card(self, profile_id: str, deck_id: str, character: str, rating: str, when: int | None = None) -> CardState | None:
        stamp = when or now_ms()
        profile_row = self.conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        profile = self._profile_from_row(profile_row) if profile_row else self.ensure_default_profile()
        row = self.conn.execute("SELECT * FROM cards WHERE id = ?", (_card_id(profile_id, deck_id, character),)).fetchone()
        if not row:
            return None
        existing = self._card_from_row(row)
        updated = schedule_card(
            existing,
            rating,
            stamp,
            scheduler_mode=profile.scheduler_mode,
            desired_retention=profile.desired_retention,
        )
        self._upsert_card(updated)
        self.conn.execute(
            """
            INSERT INTO review_logs
            (id, profile_id, deck_id, character, rating, reviewed_at, previous_due, next_due, stability, difficulty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                profile_id,
                deck_id,
                character,
                rating,
                stamp,
                existing.due,
                updated.due,
                updated.stability,
                updated.difficulty,
            ),
        )
        self.conn.execute("UPDATE kanji SET last_seen_at = ? WHERE character = ?", (stamp, character))
        self.conn.commit()
        return updated

    @synchronized
    def get_stroke_cache(self, character: str) -> str | None:
        row = self.conn.execute("SELECT svg FROM stroke_cache WHERE character = ?", (character,)).fetchone()
        return str(row["svg"]) if row else None

    @synchronized
    def put_stroke_cache(self, character: str, svg: str) -> None:
        self.conn.execute(
            """
            INSERT INTO stroke_cache (character, svg, cached_at)
            VALUES (?, ?, ?)
            ON CONFLICT(character) DO UPDATE SET svg = excluded.svg, cached_at = excluded.cached_at
            """,
            (character, svg, now_ms()),
        )
        self.conn.commit()

    @synchronized
    def save_session(self, session: Session) -> None:
        self.conn.execute(
            """
            INSERT INTO sessions (id, profile_id, deck_id, started_at, ended_at, mode, sample_size, kanji_json, seen_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                ended_at = excluded.ended_at,
                seen_json = excluded.seen_json,
                kanji_json = excluded.kanji_json,
                sample_size = excluded.sample_size,
                mode = excluded.mode
            """,
            (
                session.id,
                session.profile_id,
                session.deck_id,
                session.started_at,
                session.ended_at,
                session.mode,
                session.sample_size,
                _json(session.kanji),
                _json(session.seen),
            ),
        )
        self.conn.commit()

    @synchronized
    def restore_session_snapshot(
        self,
        *,
        profile_id: str,
        deck_id: str,
        started_at: int,
        cards: list[CardState],
        kanji_last_seen: dict[str, int | None],
    ) -> None:
        """Restore cards and last-seen timestamps after a session reset."""
        for card in cards:
            self._upsert_card(card)
        for character, last_seen_at in kanji_last_seen.items():
            self.conn.execute(
                "UPDATE kanji SET last_seen_at = ? WHERE character = ?",
                (last_seen_at, character),
            )
        if cards:
            placeholders = ",".join("?" for _ in cards)
            characters = [card.character for card in cards]
            self.conn.execute(
                f"""
                DELETE FROM review_logs
                WHERE profile_id = ? AND deck_id = ? AND reviewed_at >= ? AND character IN ({placeholders})
                """,
                (profile_id, deck_id, started_at, *characters),
            )
        self.conn.commit()

    @synchronized
    def all_sessions(self, profile_id: str | None = None) -> list[Session]:
        if profile_id:
            rows = self.conn.execute(
                "SELECT * FROM sessions WHERE profile_id = ? ORDER BY started_at ASC",
                (profile_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM sessions ORDER BY started_at ASC").fetchall()
        return [self._session_from_row(row) for row in rows]

    @synchronized
    def export_profile(self, profile_id: str, passphrase: str = "") -> str:
        profile_row = self.conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not profile_row:
            raise ValueError("Profile not found")
        payload = {
            "exported_at": now_ms(),
            "profile": asdict(self._profile_from_row(profile_row)),
            "decks": [asdict(deck) for deck in self.all_decks()],
            "sources": [asdict(source) for source in self.all_sources()],
            "kanji": [asdict(item) for item in self.all_kanji()],
            "cards": [asdict(self._card_from_row(row)) for row in self.conn.execute("SELECT * FROM cards WHERE profile_id = ?", (profile_id,)).fetchall()],
            "sessions": [asdict(session) for session in self.all_sessions(profile_id)],
            "review_logs": [dict(row) for row in self.conn.execute("SELECT * FROM review_logs WHERE profile_id = ?", (profile_id,)).fetchall()],
        }
        if not passphrase:
            return json.dumps({"encrypted": False, "data": payload}, ensure_ascii=False, indent=2)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return json.dumps(_encrypt_text(text, passphrase), ensure_ascii=False, indent=2)

    def load_export_payload(self, export_text: str, passphrase: str = "") -> dict[str, Any]:
        """Parse an exported profile payload, supporting legacy unencrypted backups."""
        try:
            root = json.loads(export_text)
        except json.JSONDecodeError as exc:
            raise ValueError("Backup file is not valid JSON") from exc
        if not isinstance(root, dict):
            raise ValueError("Backup payload must be a JSON object")

        encrypted = bool(root.get("encrypted"))
        if encrypted:
            if not passphrase:
                raise ValueError("Passphrase required for encrypted backup")
            try:
                decrypted_text = _decrypt_text(root, passphrase)
                payload = json.loads(decrypted_text)
            except (InvalidTag, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("Could not decrypt backup. Check the passphrase and file contents.") from exc
        else:
            data = root.get("data")
            if isinstance(data, str):
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise ValueError("Legacy backup payload contains invalid embedded JSON") from exc
            elif isinstance(data, dict):
                payload = data
            else:
                raise ValueError("Unencrypted backup must contain an object or JSON string in 'data'")

        if not isinstance(payload, dict):
            raise ValueError("Decoded backup payload must be a JSON object")

        required_keys = {"profile", "decks", "kanji", "cards", "sessions", "review_logs"}
        missing = sorted(required_keys.difference(payload.keys()))
        if missing:
            raise ValueError(f"Backup payload missing required keys: {', '.join(missing)}")
        return payload

    @synchronized
    def import_profile_payload(self, payload: dict[str, Any], *, duplicate_profile: bool = False) -> Profile:
        """Import a decoded profile backup into local storage."""
        profile = self._profile_from_mapping(payload["profile"])
        profile_id = profile.id
        if duplicate_profile:
            profile_id = str(uuid.uuid4())
            profile = Profile(
                id=profile_id,
                name=self._next_imported_profile_name(profile.name),
                created_at=now_ms(),
                daily_new_target=profile.daily_new_target,
                active_deck_id=profile.active_deck_id,
                scheduler_mode=profile.scheduler_mode,
                desired_retention=profile.desired_retention,
            )
        self.conn.execute(
            """
            INSERT INTO profiles
            (id, name, created_at, daily_new_target, active_deck_id, scheduler_mode, desired_retention)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                created_at = excluded.created_at,
                daily_new_target = excluded.daily_new_target,
                active_deck_id = excluded.active_deck_id,
                scheduler_mode = excluded.scheduler_mode,
                desired_retention = excluded.desired_retention
            """,
            (
                profile.id,
                profile.name,
                profile.created_at,
                profile.daily_new_target,
                profile.active_deck_id,
                profile.scheduler_mode,
                profile.desired_retention,
            ),
        )

        for deck_data in payload["decks"]:
            deck = Deck(**deck_data)
            self.conn.execute(
                """
                INSERT INTO decks (id, name, filename, imported_at, count, characters_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    filename = excluded.filename,
                    imported_at = excluded.imported_at,
                    count = excluded.count,
                    characters_json = excluded.characters_json
                """,
                (deck.id, deck.name, deck.filename, deck.imported_at, deck.count, _json(deck.characters)),
            )

        for source_data in payload.get("sources", []):
            source = Source(**source_data)
            self.conn.execute(
                """
                INSERT INTO sources (filename, imported_at, count, deck_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(filename, imported_at) DO UPDATE SET
                    count = excluded.count,
                    deck_id = excluded.deck_id
                """,
                (source.filename, source.imported_at, source.count, source.deck_id),
            )

        for kanji_data in payload["kanji"]:
            item = Kanji(**kanji_data)
            existing_row = self.conn.execute("SELECT * FROM kanji WHERE character = ?", (item.character,)).fetchone()
            if existing_row:
                existing = self._kanji_from_row(existing_row)
                merged_meanings = list(dict.fromkeys([*existing.meanings, *item.meanings]))
                merged_sources = list(dict.fromkeys([*existing.sources, *item.sources]))
                merged_decks = list(dict.fromkeys([*existing.deck_ids, *item.deck_ids]))
                last_seen_at = max(filter(None, [existing.last_seen_at, item.last_seen_at]), default=None)
                created_at = min(existing.created_at, item.created_at)
                self.conn.execute(
                    """
                    UPDATE kanji
                    SET meanings_json = ?, sources_json = ?, deck_ids_json = ?, created_at = ?, last_seen_at = ?
                    WHERE character = ?
                    """,
                    (
                        _json(merged_meanings),
                        _json(merged_sources),
                        _json(merged_decks),
                        created_at,
                        last_seen_at,
                        item.character,
                    ),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO kanji (character, meanings_json, sources_json, deck_ids_json, created_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.character,
                        _json(item.meanings),
                        _json(item.sources),
                        _json(item.deck_ids),
                        item.created_at,
                        item.last_seen_at,
                    ),
                )

        if not duplicate_profile:
            self.conn.execute("DELETE FROM cards WHERE profile_id = ?", (profile.id,))
            self.conn.execute("DELETE FROM sessions WHERE profile_id = ?", (profile.id,))
            self.conn.execute("DELETE FROM review_logs WHERE profile_id = ?", (profile.id,))

        for card_data in payload["cards"]:
            card = CardState(**card_data)
            if duplicate_profile:
                card = CardState(
                    **{
                        **asdict(card),
                        "id": _card_id(profile_id, card.deck_id, card.character),
                        "profile_id": profile_id,
                    }
                )
            self._upsert_card(card)

        for session_data in payload["sessions"]:
            session = Session(**session_data)
            if duplicate_profile:
                session = Session(
                    id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    deck_id=session.deck_id,
                    started_at=session.started_at,
                    ended_at=session.ended_at,
                    mode=session.mode,
                    sample_size=session.sample_size,
                    kanji=session.kanji,
                    seen=session.seen,
                )
            self.save_session(session)

        for row in payload["review_logs"]:
            review_log_id = row["id"] if not duplicate_profile else str(uuid.uuid4())
            review_profile_id = row["profile_id"] if not duplicate_profile else profile_id
            self.conn.execute(
                """
                INSERT INTO review_logs
                (id, profile_id, deck_id, character, rating, reviewed_at, previous_due, next_due, stability, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_log_id,
                    review_profile_id,
                    row["deck_id"],
                    row["character"],
                    row["rating"],
                    row["reviewed_at"],
                    row["previous_due"],
                    row["next_due"],
                    row["stability"],
                    row["difficulty"],
                ),
            )

        self.conn.commit()
        self._ensure_profile_cards(profile)
        return profile

    def _next_imported_profile_name(self, base_name: str) -> str:
        existing_names = {profile.name for profile in self.all_profiles()}
        if base_name not in existing_names:
            return base_name
        suffix = " (Imported)"
        candidate = f"{base_name}{suffix}"
        if candidate not in existing_names:
            return candidate
        index = 2
        while True:
            candidate = f"{base_name}{suffix} {index}"
            if candidate not in existing_names:
                return candidate
            index += 1

    @synchronized
    def delete_all(self) -> None:
        for table in ["kanji", "cards", "decks", "sessions", "sources", "review_logs", "stroke_cache", "profiles"]:
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()
        self.ensure_default_profile()

    @synchronized
    def delete_profile(self, profile_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return False
        self.conn.execute("DELETE FROM cards WHERE profile_id = ?", (profile_id,))
        self.conn.execute("DELETE FROM review_logs WHERE profile_id = ?", (profile_id,))
        self.conn.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
        self.conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        self.conn.commit()
        remaining = self.conn.execute("SELECT 1 FROM profiles LIMIT 1").fetchone()
        if not remaining:
            self.ensure_default_profile()
        return True

    @synchronized
    def delete_deck(self, deck_id: str) -> bool:
        row = self.conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        if not row:
            return False
        deck = self._deck_from_row(row)
        self.conn.execute("DELETE FROM cards WHERE deck_id = ?", (deck_id,))
        self.conn.execute("DELETE FROM review_logs WHERE deck_id = ?", (deck_id,))
        self.conn.execute("DELETE FROM sessions WHERE deck_id = ?", (deck_id,))
        self.conn.execute("DELETE FROM sources WHERE deck_id = ?", (deck_id,))
        self.conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))

        kanji_rows = self.conn.execute("SELECT * FROM kanji").fetchall()
        for kanji_row in kanji_rows:
            item = self._kanji_from_row(kanji_row)
            if deck_id not in item.deck_ids:
                continue
            remaining_decks = [item_id for item_id in item.deck_ids if item_id != deck_id]
            if remaining_decks:
                self.conn.execute(
                    "UPDATE kanji SET deck_ids_json = ? WHERE character = ?",
                    (_json(remaining_decks), item.character),
                )
            else:
                self.conn.execute("DELETE FROM kanji WHERE character = ?", (item.character,))

        fallback_row = self.conn.execute(
            "SELECT id FROM decks WHERE id != ? ORDER BY imported_at DESC LIMIT 1",
            (deck_id,),
        ).fetchone()
        fallback_deck_id = str(fallback_row["id"]) if fallback_row else None
        self.conn.execute(
            "UPDATE profiles SET active_deck_id = ? WHERE active_deck_id = ?",
            (fallback_deck_id, deck_id),
        )
        self.conn.commit()
        return True

    def _profile_from_row(self, row: sqlite3.Row) -> Profile:
        row_keys = set(row.keys())
        return Profile(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            daily_new_target=row["daily_new_target"],
            active_deck_id=row["active_deck_id"],
            scheduler_mode=row["scheduler_mode"] if "scheduler_mode" in row_keys else DEFAULT_SCHEDULER_MODE,
            desired_retention=(
                float(row["desired_retention"])
                if "desired_retention" in row_keys and row["desired_retention"] is not None
                else DEFAULT_DESIRED_RETENTION
            ),
        )

    def _profile_from_mapping(self, data: dict[str, Any]) -> Profile:
        return Profile(
            id=str(data["id"]),
            name=str(data["name"]),
            created_at=int(data["created_at"]),
            daily_new_target=int(data.get("daily_new_target", 10)),
            active_deck_id=str(data["active_deck_id"]) if data.get("active_deck_id") else None,
            scheduler_mode=str(data.get("scheduler_mode", DEFAULT_SCHEDULER_MODE)),
            desired_retention=float(data.get("desired_retention", DEFAULT_DESIRED_RETENTION)),
        )

    def _deck_from_row(self, row: sqlite3.Row) -> Deck:
        return Deck(
            id=row["id"],
            name=row["name"],
            filename=row["filename"],
            imported_at=row["imported_at"],
            count=row["count"],
            characters=_loads_json(row["characters_json"], []),
        )

    def _kanji_from_row(self, row: sqlite3.Row) -> Kanji:
        return Kanji(
            character=row["character"],
            meanings=_loads_json(row["meanings_json"], []),
            sources=_loads_json(row["sources_json"], []),
            deck_ids=_loads_json(row["deck_ids_json"], []),
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
        )

    def _card_from_row(self, row: sqlite3.Row) -> CardState:
        return CardState(
            id=row["id"],
            profile_id=row["profile_id"],
            deck_id=row["deck_id"],
            character=row["character"],
            state=row["state"],
            stability=row["stability"],
            difficulty=row["difficulty"],
            retrievability=row["retrievability"],
            due=row["due"],
            elapsed_days=row["elapsed_days"],
            scheduled_days=row["scheduled_days"],
            reps=row["reps"],
            lapses=row["lapses"],
            last_review=row["last_review"],
            relearn_until=row["relearn_until"],
            created_at=row["created_at"],
        )

    def _session_from_row(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            profile_id=row["profile_id"],
            deck_id=row["deck_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            mode=row["mode"],
            sample_size=row["sample_size"],
            kanji=_loads_json(row["kanji_json"], []),
            seen=_loads_json(row["seen_json"], []),
        )

    @synchronized
    def _upsert_card(self, card: CardState) -> None:
        self.conn.execute(
            """
            INSERT INTO cards
            (id, profile_id, deck_id, character, state, stability, difficulty, retrievability, due,
             elapsed_days, scheduled_days, reps, lapses, last_review, relearn_until, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state = excluded.state,
                stability = excluded.stability,
                difficulty = excluded.difficulty,
                retrievability = excluded.retrievability,
                due = excluded.due,
                elapsed_days = excluded.elapsed_days,
                scheduled_days = excluded.scheduled_days,
                reps = excluded.reps,
                lapses = excluded.lapses,
                last_review = excluded.last_review,
                relearn_until = excluded.relearn_until,
                created_at = excluded.created_at
            """,
            (
                card.id,
                card.profile_id,
                card.deck_id,
                card.character,
                card.state,
                card.stability,
                card.difficulty,
                card.retrievability,
                card.due,
                card.elapsed_days,
                card.scheduled_days,
                card.reps,
                card.lapses,
                card.last_review,
                card.relearn_until,
                card.created_at,
            ),
        )


def schedule_card(
    card: CardState,
    rating: str,
    when: int,
    *,
    scheduler_mode: str = DEFAULT_SCHEDULER_MODE,
    desired_retention: float = DEFAULT_DESIRED_RETENTION,
) -> CardState:
    interval_override_days: int | None = None
    if rating != "again" and is_package_mode(scheduler_mode):
        previous_interval = max(0, card.scheduled_days)
        try:
            interval_override_days = package_dr_interval_days(
                stability=max(card.stability, 0.1),
                difficulty=card.difficulty,
                prev_interval=previous_interval,
                grade=GRADE_BY_RATING[rating],
                desired_retention=desired_retention,
            )
        except Exception:
            interval_override_days = None
    update = schedule_fsrs(
        card,
        rating,
        when,
        desired_retention=desired_retention,
        interval_override_days=interval_override_days,
    )
    return CardState(
        **{
            **asdict(card),
            "state": update.state,
            "stability": update.stability,
            "difficulty": update.difficulty,
            "retrievability": update.retrievability,
            "due": update.due,
            "elapsed_days": update.elapsed_days,
            "scheduled_days": update.scheduled_days,
            "reps": update.reps,
            "lapses": update.lapses,
            "last_review": update.last_review,
            "relearn_until": update.relearn_until,
        }
    )


def queue_characters(relearn: Iterable[CardState], review: Iterable[CardState], fresh: Iterable[CardState]) -> list[str]:
    return [card.character for card in [*relearn, *review, *fresh]]


def queue_mode(relearn: list[CardState], review: list[CardState], fresh: list[CardState]) -> str:
    if relearn:
        return "relearn"
    if review:
        return "review"
    return "new" if fresh else "review"


def new_session(mode: str, kanji: list[str], sample_size: int, profile_id: str, deck_id: str) -> Session:
    return Session(
        id=str(uuid.uuid4()),
        profile_id=profile_id,
        deck_id=deck_id,
        started_at=now_ms(),
        ended_at=None,
        mode=mode,
        sample_size=sample_size,
        kanji=kanji,
        seen=[],
    )


def relative_time(ts: int | None) -> str:
    if not ts:
        return "never"
    diff = now_ms() - ts
    sec = diff // 1000
    if sec < 60:
        return "just now"
    minutes = sec // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        today = datetime.now().date()
        then = datetime.fromtimestamp(ts / 1000).date()
        if today == then:
            return "today"
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    weeks = days // 7
    if weeks < 8:
        return f"{weeks} weeks ago"
    months = days // 30
    if months < 12:
        return f"{months} months ago"
    return f"{days // 365} years ago"


def day_key(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")


def _encrypt_text(text: str, passphrase: str) -> dict[str, object]:
    salt = os.urandom(16)
    iv = os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=150_000)
    key = kdf.derive(passphrase.encode("utf-8"))
    encrypted = AESGCM(key).encrypt(iv, text.encode("utf-8"), None)
    return {
        "encrypted": True,
        "algorithm": "AES-GCM",
        "kdf": "PBKDF2-SHA256",
        "iterations": 150_000,
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "data": base64.b64encode(encrypted).decode("ascii"),
    }


def _decrypt_text(payload: dict[str, Any], passphrase: str) -> str:
    salt = base64.b64decode(str(payload["salt"]))
    iv = base64.b64decode(str(payload["iv"]))
    encrypted = base64.b64decode(str(payload["data"]))
    iterations = int(payload.get("iterations", 150_000))
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    key = kdf.derive(passphrase.encode("utf-8"))
    decrypted = AESGCM(key).decrypt(iv, encrypted, None)
    return decrypted.decode("utf-8")
