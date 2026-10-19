"""Proficiency and coverage numbers for the class dashboard. Pure Python."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

from .models import Card, Chapter, from_iso

MASTERY_INTERVAL_DAYS = 21

UNTESTED = "untested"
STRUGGLING = "struggling"
LEARNING = "learning"
MASTERED = "mastered"
STATUSES = (UNTESTED, STRUGGLING, LEARNING, MASTERED)
STATUS_LABELS = {
    UNTESTED: "Untested",
    STRUGGLING: "Struggling",
    LEARNING: "Learning",
    MASTERED: "Mastered",
}


def card_status(card: Card) -> str:
    if card.is_new or card.last_rating is None:
        return UNTESTED
    if card.last_rating <= 2:
        return STRUGGLING
    if card.last_rating >= 4 and card.interval_days >= MASTERY_INTERVAL_DAYS:
        return MASTERED
    return LEARNING


def card_mastery(card: Card) -> Optional[float]:
    """0..1 blend of last confidence and how long the card has held up. None if untested."""
    if card_status(card) == UNTESTED:
        return None
    confidence = (card.last_rating - 1) / 4
    retention = min(card.interval_days / MASTERY_INTERVAL_DAYS, 1.0)
    return 0.5 * confidence + 0.5 * retention


def end_of_local_day(now: datetime, days_ahead: int = 0) -> datetime:
    local = now.astimezone()
    day = local.date() + timedelta(days=days_ahead)
    return datetime.combine(day, time.max, tzinfo=local.tzinfo)


def count_due(cards: Iterable[Card], cutoff: datetime) -> int:
    return sum(1 for c in cards if not c.is_new and c.due <= cutoff)


@dataclass
class GroupStats:
    """Stats for one chapter (key = chapter id) or a whole class (key = None)."""
    key: Optional[int]
    name: str
    total: int = 0
    due_today: int = 0
    proficiency: Optional[float] = None
    counts: dict[str, int] = field(default_factory=lambda: {s: 0 for s in STATUSES})

    @property
    def untested(self) -> int:
        return self.counts[UNTESTED]

    @property
    def tested(self) -> int:
        return self.total - self.untested


def summarize(cards: Iterable[Card], now: datetime, key: Optional[int] = None,
              name: str = "") -> GroupStats:
    cards = list(cards)
    stats = GroupStats(key=key, name=name, total=len(cards))
    masteries = []
    for card in cards:
        stats.counts[card_status(card)] += 1
        m = card_mastery(card)
        if m is not None:
            masteries.append(m)
    stats.proficiency = sum(masteries) / len(masteries) if masteries else None
    stats.due_today = count_due(cards, end_of_local_day(now))
    return stats


def class_stats(chapters: Iterable[Chapter], cards: Iterable[Card],
                now: datetime) -> tuple[GroupStats, list[GroupStats]]:
    """(whole-class stats, per-chapter stats in chapter order)."""
    chapters = list(chapters)
    cards = list(cards)
    by_chapter: dict[int, list[Card]] = {ch.id: [] for ch in chapters}
    for card in cards:
        by_chapter.setdefault(card.chapter_id, []).append(card)
    per_chapter = [summarize(by_chapter[ch.id], now, ch.id, ch.name) for ch in chapters]
    return summarize(cards, now), per_chapter


def review_activity(timestamps: Iterable[str], now: datetime,
                    days: int = 30) -> list[tuple[date, int]]:
    """Reviews per local calendar day for the last `days` days (oldest first)."""
    today = now.astimezone().date()
    start = today - timedelta(days=days - 1)
    counts = {start + timedelta(days=i): 0 for i in range(days)}
    for ts in timestamps:
        dt = from_iso(ts)
        if dt is None:
            continue
        day = dt.astimezone().date()
        if day in counts:
            counts[day] += 1
    return list(counts.items())
