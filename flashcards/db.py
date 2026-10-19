"""SQLite storage for classes, chapters, cards and review history."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .models import Card, Chapter, ClassItem, ScheduleUpdate, to_iso, utcnow

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cards (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id       INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    front_html       TEXT NOT NULL DEFAULT '',
    back_html        TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    ease             REAL NOT NULL DEFAULT 2.5,
    interval_days    REAL NOT NULL DEFAULT 0,
    repetitions      INTEGER NOT NULL DEFAULT 0,
    due_at           TEXT,
    last_rating      INTEGER,
    last_reviewed_at TEXT,
    lapses           INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id     INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chapters_class ON chapters(class_id);
CREATE INDEX IF NOT EXISTS idx_cards_chapter  ON cards(chapter_id);
CREATE INDEX IF NOT EXISTS idx_reviews_card   ON reviews(card_id);
"""

CARD_COLUMNS = (
    "id", "chapter_id", "front_html", "back_html", "created_at", "ease",
    "interval_days", "repetitions", "due_at", "last_rating", "last_reviewed_at", "lapses",
)
_CARD_SELECT = f"SELECT {', '.join('cards.' + c for c in CARD_COLUMNS)} FROM cards"


def _placeholders(values: list) -> str:
    return ", ".join("?" for _ in values)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    @property
    def data_dir(self) -> Path:
        return self.path.parent

    def close(self) -> None:
        self.conn.close()

    # ---- classes -------------------------------------------------------
    def list_classes(self) -> list[ClassItem]:
        rows = self.conn.execute("SELECT id, name, created_at FROM classes ORDER BY id")
        return [ClassItem(**dict(r)) for r in rows]

    def get_class(self, class_id: int) -> Optional[ClassItem]:
        row = self.conn.execute(
            "SELECT id, name, created_at FROM classes WHERE id = ?", (class_id,)).fetchone()
        return ClassItem(**dict(row)) if row else None

    def add_class(self, name: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO classes (name, created_at) VALUES (?, ?)", (name, to_iso(utcnow())))
        return cur.lastrowid

    def rename_class(self, class_id: int, name: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE classes SET name = ? WHERE id = ?", (name, class_id))

    def delete_class(self, class_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))

    # ---- chapters ------------------------------------------------------
    def list_chapters(self, class_id: int) -> list[Chapter]:
        rows = self.conn.execute(
            "SELECT id, class_id, name, position FROM chapters WHERE class_id = ? "
            "ORDER BY position, id", (class_id,))
        return [Chapter(**dict(r)) for r in rows]

    def get_chapter(self, chapter_id: int) -> Optional[Chapter]:
        row = self.conn.execute(
            "SELECT id, class_id, name, position FROM chapters WHERE id = ?",
            (chapter_id,)).fetchone()
        return Chapter(**dict(row)) if row else None

    def add_chapter(self, class_id: int, name: str) -> int:
        with self.conn:
            (pos,) = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM chapters WHERE class_id = ?",
                (class_id,)).fetchone()
            cur = self.conn.execute(
                "INSERT INTO chapters (class_id, name, position) VALUES (?, ?, ?)",
                (class_id, name, pos))
        return cur.lastrowid

    def rename_chapter(self, chapter_id: int, name: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE chapters SET name = ? WHERE id = ?", (name, chapter_id))

    def delete_chapter(self, chapter_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))

    def move_chapter(self, chapter_id: int, delta: int) -> None:
        """Move a chapter up (delta=-1) or down (delta=+1) within its class."""
        chapter = self.get_chapter(chapter_id)
        if chapter is None:
            return
        ids = [c.id for c in self.list_chapters(chapter.class_id)]
        i = ids.index(chapter_id)
        j = i + delta
        if not 0 <= j < len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        with self.conn:
            self.conn.executemany("UPDATE chapters SET position = ? WHERE id = ?",
                                  [(pos, cid) for pos, cid in enumerate(ids)])

    def move_chapter_to_class(self, chapter_id: int, class_id: int) -> None:
        """Move a chapter (and its cards) to the end of another class."""
        with self.conn:
            (pos,) = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM chapters WHERE class_id = ?",
                (class_id,)).fetchone()
            self.conn.execute("UPDATE chapters SET class_id = ?, position = ? WHERE id = ?",
                              (class_id, pos, chapter_id))

    # ---- cards ---------------------------------------------------------
    @staticmethod
    def _card(row: sqlite3.Row) -> Card:
        return Card(**dict(row))

    def get_card(self, card_id: int) -> Optional[Card]:
        row = self.conn.execute(f"{_CARD_SELECT} WHERE id = ?", (card_id,)).fetchone()
        return self._card(row) if row else None

    def list_cards(self, chapter_id: int) -> list[Card]:
        rows = self.conn.execute(
            f"{_CARD_SELECT} WHERE chapter_id = ? ORDER BY created_at, id", (chapter_id,))
        return [self._card(r) for r in rows]

    def list_cards_for_chapters(self, chapter_ids: Iterable[int]) -> list[Card]:
        ids = list(chapter_ids)
        if not ids:
            return []
        rows = self.conn.execute(
            f"{_CARD_SELECT} WHERE chapter_id IN ({_placeholders(ids)}) ORDER BY created_at, id",
            ids)
        return [self._card(r) for r in rows]

    def list_cards_for_class(self, class_id: int) -> list[Card]:
        rows = self.conn.execute(
            f"{_CARD_SELECT} JOIN chapters ON chapters.id = cards.chapter_id "
            "WHERE chapters.class_id = ? ORDER BY cards.created_at, cards.id", (class_id,))
        return [self._card(r) for r in rows]

    def count_cards(self, chapter_id: int) -> int:
        (n,) = self.conn.execute(
            "SELECT COUNT(*) FROM cards WHERE chapter_id = ?", (chapter_id,)).fetchone()
        return n

    def add_card(self, chapter_id: int, front_html: str, back_html: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO cards (chapter_id, front_html, back_html, created_at) "
                "VALUES (?, ?, ?, ?)", (chapter_id, front_html, back_html, to_iso(utcnow())))
        return cur.lastrowid

    def update_card_content(self, card_id: int, front_html: str, back_html: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE cards SET front_html = ?, back_html = ? WHERE id = ?",
                              (front_html, back_html, card_id))

    def delete_cards(self, card_ids: Iterable[int]) -> None:
        ids = list(card_ids)
        if ids:
            with self.conn:
                self.conn.execute(f"DELETE FROM cards WHERE id IN ({_placeholders(ids)})", ids)

    def move_cards(self, card_ids: Iterable[int], chapter_id: int) -> None:
        """Move cards to another chapter, keeping their review history and schedule."""
        ids = list(card_ids)
        if ids:
            with self.conn:
                self.conn.execute(
                    f"UPDATE cards SET chapter_id = ? WHERE id IN ({_placeholders(ids)})",
                    [chapter_id, *ids])

    def all_card_html(self) -> list[str]:
        rows = self.conn.execute("SELECT front_html, back_html FROM cards")
        return [html for row in rows for html in row]

    # ---- reviews -------------------------------------------------------
    def record_review(self, card_id: int, rating: int, update: ScheduleUpdate) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE cards SET ease = ?, interval_days = ?, repetitions = ?, due_at = ?, "
                "last_rating = ?, last_reviewed_at = ?, lapses = ? WHERE id = ?",
                (update.ease, update.interval_days, update.repetitions, update.due_at,
                 update.last_rating, update.last_reviewed_at, update.lapses, card_id))
            self.conn.execute(
                "INSERT INTO reviews (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
                (card_id, rating, update.last_reviewed_at))

    def review_times_for_class(self, class_id: int, since: datetime) -> list[str]:
        rows = self.conn.execute(
            "SELECT reviews.reviewed_at FROM reviews "
            "JOIN cards ON cards.id = reviews.card_id "
            "JOIN chapters ON chapters.id = cards.chapter_id "
            "WHERE chapters.class_id = ? AND reviews.reviewed_at >= ?",
            (class_id, to_iso(since)))
        return [r[0] for r in rows]
