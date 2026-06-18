"""Pure-Python FSRS scheduling helpers used by the desktop app.

This module mirrors the memory-state formulas used in the local
`SSP-MMC-FSRS` reference implementation, but keeps the runtime light enough
for the desktop app by avoiding the research package's torch dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import CardState


DEFAULT_FSRS_WEIGHTS = (
    0.4002,
    0.1813,
    0.6958,
    3.1337,
    6.6154,
    0.565,
    2.999,
    0.0759,
    1.568,
    0.248,
    0.4816,
    1.7469,
    0.0247,
    0.5986,
    1.8441,
    0.4189,
    1.81,
    0.5784,
    0.1924,
    0.0658,
    0.4444,
)

DEFAULT_DESIRED_RETENTION = 0.9
DEFAULT_SCHEDULER_MODE = "fsrs"
PACKAGE_DR_SCHEDULER_MODE = "ssp-mmc-fsrs-dr"
DEFAULT_RELEARN_MINUTES = 10
MILLIS_PER_DAY = 86_400_000
MILLIS_PER_MINUTE = 60_000
S_MIN = 0.1
S_MAX = 365 * 25
EASE_MIN = 1.0
EASE_MAX = 10.0
GRADE_BY_RATING = {"again": 1, "hard": 2, "good": 3, "easy": 4}


@dataclass(frozen=True, slots=True)
class FSRSUpdate:
    """Calculated scheduling fields to merge into the stored card state."""

    state: str
    stability: float
    difficulty: float
    retrievability: float
    due: int
    elapsed_days: int
    scheduled_days: int
    reps: int
    lapses: int
    last_review: int
    relearn_until: int | None


def schedule_fsrs(
    card: "CardState",
    rating: str,
    when: int,
    *,
    desired_retention: float = DEFAULT_DESIRED_RETENTION,
    interval_override_days: int | None = None,
) -> FSRSUpdate:
    """Schedule the next review using FSRS state transitions plus same-day relearn."""
    grade = GRADE_BY_RATING[rating]
    elapsed = _elapsed_days(card.last_review, when)
    retrievability = _retrievability(elapsed, card.stability)

    if card.state == "new" or card.reps == 0 or card.stability <= 0:
        return _schedule_first_learning(
            card,
            grade,
            when,
            desired_retention=desired_retention,
            interval_override_days=interval_override_days,
        )

    if grade == 1:
        new_stability = _stability_after_failure(card.stability, card.difficulty, retrievability)
        new_difficulty = _next_difficulty(card.difficulty, grade)
        due = when + DEFAULT_RELEARN_MINUTES * MILLIS_PER_MINUTE
        return FSRSUpdate(
            state="relearning",
            stability=new_stability,
            difficulty=new_difficulty,
            retrievability=retrievability,
            due=due,
            elapsed_days=math.floor(elapsed),
            scheduled_days=0,
            reps=card.reps + 1,
            lapses=card.lapses + 1,
            last_review=when,
            relearn_until=due,
        )

    new_stability = _stability_after_success(card.stability, card.difficulty, retrievability, grade)
    new_difficulty = _next_difficulty(card.difficulty, grade)
    scheduled_days = interval_override_days or _next_interval_days(new_stability, desired_retention)
    due = when + scheduled_days * MILLIS_PER_DAY
    return FSRSUpdate(
        state="review",
        stability=new_stability,
        difficulty=new_difficulty,
        retrievability=retrievability,
        due=due,
        elapsed_days=math.floor(elapsed),
        scheduled_days=scheduled_days,
        reps=card.reps + 1,
        lapses=card.lapses,
        last_review=when,
        relearn_until=None,
    )


def _schedule_first_learning(
    card: "CardState",
    grade: int,
    when: int,
    *,
    desired_retention: float,
    interval_override_days: int | None,
) -> FSRSUpdate:
    """Initialize a new card from its first rating."""
    new_stability = _init_stability(grade)
    new_difficulty = _init_difficulty_with_short_term(grade)
    if grade == 1:
        due = when + DEFAULT_RELEARN_MINUTES * MILLIS_PER_MINUTE
        return FSRSUpdate(
            state="relearning",
            stability=new_stability,
            difficulty=new_difficulty,
            retrievability=0.0,
            due=due,
            elapsed_days=0,
            scheduled_days=0,
            reps=card.reps + 1,
            lapses=card.lapses + 1,
            last_review=when,
            relearn_until=due,
        )

    scheduled_days = interval_override_days or _next_interval_days(new_stability, desired_retention)
    due = when + scheduled_days * MILLIS_PER_DAY
    return FSRSUpdate(
        state="review",
        stability=new_stability,
        difficulty=new_difficulty,
        retrievability=0.0,
        due=due,
        elapsed_days=0,
        scheduled_days=scheduled_days,
        reps=card.reps + 1,
        lapses=card.lapses,
        last_review=when,
        relearn_until=None,
    )


def _elapsed_days(last_review: int | None, when: int) -> float:
    if not last_review:
        return 0.0
    return max(0.0, (when - last_review) / MILLIS_PER_DAY)


def _retrievability(elapsed_days: float, stability: float) -> float:
    if stability <= 0:
        return 0.0
    factor = 0.9 ** (1.0 / _decay()) - 1.0
    return (1.0 + factor * elapsed_days / stability) ** _decay()


def _next_interval_days(stability: float, desired_retention: float) -> int:
    factor = 0.9 ** (1.0 / _decay()) - 1.0
    interval = stability / factor * (desired_retention ** (1.0 / _decay()) - 1.0)
    return max(1, math.floor(interval))


def _stability_after_success(stability: float, difficulty: float, retrievability: float, grade: int) -> float:
    hard_penalty = DEFAULT_FSRS_WEIGHTS[15] if grade == 2 else 1.0
    easy_bonus = DEFAULT_FSRS_WEIGHTS[16] if grade == 4 else 1.0
    updated = stability * (
        1.0
        + math.exp(DEFAULT_FSRS_WEIGHTS[8])
        * (11.0 - difficulty)
        * math.pow(stability, -DEFAULT_FSRS_WEIGHTS[9])
        * (math.exp((1.0 - retrievability) * DEFAULT_FSRS_WEIGHTS[10]) - 1.0)
        * hard_penalty
        * easy_bonus
    )
    return _clamp_stability(updated)


def _stability_after_failure(stability: float, difficulty: float, retrievability: float) -> float:
    updated = min(
        DEFAULT_FSRS_WEIGHTS[11]
        * math.pow(difficulty, -DEFAULT_FSRS_WEIGHTS[12])
        * (math.pow(stability + 1.0, DEFAULT_FSRS_WEIGHTS[13]) - 1.0)
        * math.exp((1.0 - retrievability) * DEFAULT_FSRS_WEIGHTS[14]),
        stability / math.exp(DEFAULT_FSRS_WEIGHTS[17] * DEFAULT_FSRS_WEIGHTS[18]),
    )
    return _clamp_stability(updated)


def _init_stability(grade: int) -> float:
    return _clamp_stability(DEFAULT_FSRS_WEIGHTS[grade - 1])


def _init_difficulty(grade: int) -> float:
    value = DEFAULT_FSRS_WEIGHTS[4] - math.exp(DEFAULT_FSRS_WEIGHTS[5] * (grade - 1.0)) + 1.0
    return _clamp_difficulty(value)


def _init_difficulty_with_short_term(grade: int) -> float:
    return _init_difficulty(grade)


def _next_difficulty(difficulty: float, grade: int) -> float:
    delta = -DEFAULT_FSRS_WEIGHTS[6] * (grade - 3.0)
    damped = delta * (10.0 - difficulty) / 9.0
    updated = difficulty + damped
    reverted = DEFAULT_FSRS_WEIGHTS[7] * _init_difficulty(4) + (1.0 - DEFAULT_FSRS_WEIGHTS[7]) * updated
    return _clamp_difficulty(reverted)


def _clamp_stability(value: float) -> float:
    return min(S_MAX, max(S_MIN, float(value)))


def _clamp_difficulty(value: float) -> float:
    return min(EASE_MAX, max(EASE_MIN, float(value)))


def _decay() -> float:
    return -DEFAULT_FSRS_WEIGHTS[20]
