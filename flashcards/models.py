"""Plain data objects shared by the storage, scheduling and UI layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def from_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class ClassItem:
    id: int
    name: str
    created_at: str


@dataclass
class Chapter:
    id: int
    class_id: int
    name: str
    position: int


@dataclass
class Card:
    id: int
    chapter_id: int
    front_html: str
    back_html: str
    created_at: str
    ease: float = 2.5
    interval_days: float = 0.0
    repetitions: int = 0
    due_at: Optional[str] = None
    last_rating: Optional[int] = None
    last_reviewed_at: Optional[str] = None
    lapses: int = 0

    @property
    def is_new(self) -> bool:
        return self.due_at is None

    @property
    def due(self) -> Optional[datetime]:
        return from_iso(self.due_at)

    @property
    def last_reviewed(self) -> Optional[datetime]:
        return from_iso(self.last_reviewed_at)


@dataclass
class Review:
    id: int
    card_id: int
    rating: int
    reviewed_at: str


@dataclass
class ScheduleUpdate:
    """New scheduling state for a card after a rating."""
    ease: float
    interval_days: float
    repetitions: int
    due_at: str
    last_rating: int
    last_reviewed_at: str
    lapses: int
    failed: bool = field(default=False)
