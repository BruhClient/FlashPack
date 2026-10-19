"""Spaced-repetition scheduling (an SM-2 variant on a 1-5 confidence scale)
and selection of the best cards for a test session.

Pure Python - no Qt - so it can be unit tested in isolation.
"""
from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .models import Card, ScheduleUpdate, to_iso, utcnow

RATING_LABELS = {
    1: "No idea",
    2: "Barely",
    3: "Unsure",
    4: "Good",
    5: "Perfect",
}

MIN_EASE = 1.3
DEFAULT_EASE = 2.5
FAIL_INTERVAL_DAYS = 10 / (24 * 60)  # relearn a failed card after 10 minutes
MAX_OVERDUE_RATIO = 5.0              # keeps very overdue cards from drowning out weakness


def _days(delta: timedelta) -> float:
    return delta.total_seconds() / 86400


def next_ease(ease: float, rating: int) -> float:
    """SM-2 ease update: 5 raises ease, 4 keeps it, 3 and below lower it."""
    miss = 5 - rating
    return max(MIN_EASE, ease + 0.1 - miss * (0.08 + miss * 0.02))


def apply_rating(card: Card, rating: int, now: Optional[datetime] = None,
                 first_in_session: bool = True) -> ScheduleUpdate:
    """Return the card's new schedule after it was rated `rating` (1-5).

    Only the first rating a card gets in a session changes its ease and lapse
    count; repeats of a failed card just reschedule it.
    """
    if rating not in RATING_LABELS:
        raise ValueError(f"rating must be 1-5, got {rating!r}")
    now = now or utcnow()

    ease = next_ease(card.ease, rating) if first_in_session else card.ease
    lapses = card.lapses
    failed = rating <= 2

    if failed:
        repetitions = 0
        interval = FAIL_INTERVAL_DAYS
        if first_in_session:
            lapses += 1
    else:
        repetitions = card.repetitions + 1
        if repetitions == 1:
            interval = 1.0
        elif repetitions == 2:
            interval = 3.0 if rating == 3 else 6.0
        else:
            interval = max(card.interval_days, 1.0) * ease
            if rating == 3:
                interval *= 0.8
            elif rating == 5:
                interval *= 1.3

    return ScheduleUpdate(
        ease=ease,
        interval_days=interval,
        repetitions=repetitions,
        due_at=to_iso(now + timedelta(days=interval)),
        last_rating=rating,
        last_reviewed_at=to_iso(now),
        lapses=lapses,
        failed=failed,
    )


def apply_update(card: Card, update: ScheduleUpdate) -> None:
    """Copy a schedule update onto an in-memory card."""
    card.ease = update.ease
    card.interval_days = update.interval_days
    card.repetitions = update.repetitions
    card.due_at = update.due_at
    card.last_rating = update.last_rating
    card.last_reviewed_at = update.last_reviewed_at
    card.lapses = update.lapses


def _elapsed_and_interval(card: Card, now: datetime) -> tuple[float, float]:
    interval = max(card.interval_days, FAIL_INTERVAL_DAYS)
    last = card.last_reviewed
    elapsed = _days(now - last) if last else interval
    return max(elapsed, 0.0), interval


def priority(card: Card, now: datetime) -> float:
    """How urgently a due card should be tested. Higher = sooner."""
    elapsed, interval = _elapsed_and_interval(card, now)
    overdue_ratio = min(elapsed / interval, MAX_OVERDUE_RATIO)
    rating = card.last_rating or 3
    weakness = (5 - rating) / 4 + (DEFAULT_EASE - card.ease)
    return overdue_ratio + weakness


def recall_probability(card: Card, now: datetime) -> float:
    """Rough estimate of the chance the card is still remembered (90% at its due date)."""
    elapsed, interval = _elapsed_and_interval(card, now)
    return 0.9 ** (elapsed / interval)


def build_session(cards: Iterable[Card], n: int, include_new: bool = True,
                  now: Optional[datetime] = None) -> list[Card]:
    """Pick up to `n` cards: due cards by priority, then new cards, then the
    not-yet-due cards you are most likely to have forgotten."""
    now = now or utcnow()
    cards = list(cards)
    reviewed = [c for c in cards if not c.is_new]

    due = sorted((c for c in reviewed if c.due <= now),
                 key=lambda c: priority(c, now), reverse=True)
    new = sorted((c for c in cards if c.is_new),
                 key=lambda c: (c.created_at, c.id)) if include_new else []
    later = sorted((c for c in reviewed if c.due > now),
                   key=lambda c: recall_probability(c, now))

    return (due + new + later)[:max(n, 0)]


class StudySession:
    """Queue for one test. Cards rated 1-2 come back a few cards later until passed."""

    REQUEUE_MIN = 3
    REQUEUE_MAX = 5

    def __init__(self, cards: Iterable[Card], rng: Optional[random.Random] = None):
        self.queue: list[Card] = list(cards)
        self.total = len(self.queue)
        self.first_ratings: dict[int, int] = {}
        self.passed: set[int] = set()
        self.attempts = 0
        self._rng = rng or random.Random()

    @property
    def current(self) -> Optional[Card]:
        return self.queue[0] if self.queue else None

    @property
    def finished(self) -> bool:
        return not self.queue

    @property
    def progress(self) -> float:
        return len(self.passed) / self.total if self.total else 1.0

    def is_first_attempt(self, card: Card) -> bool:
        return card.id not in self.first_ratings

    def rate(self, rating: int) -> Card:
        """Record a rating for the current card and advance the queue."""
        if not self.queue:
            raise RuntimeError("session is finished")
        card = self.queue.pop(0)
        self.attempts += 1
        self.first_ratings.setdefault(card.id, rating)
        if rating <= 2:
            pos = min(len(self.queue), self._rng.randint(self.REQUEUE_MIN, self.REQUEUE_MAX))
            self.queue.insert(pos, card)
        else:
            self.passed.add(card.id)
        return card

    def rating_distribution(self) -> dict[int, int]:
        counts = Counter(self.first_ratings.values())
        return {r: counts.get(r, 0) for r in RATING_LABELS}
