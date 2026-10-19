"""Export all data to a single portable `.flashpack` file and import it elsewhere.

A pack is a zip containing `data.json` (every class, chapter, card and review)
and a `media/` folder with the images the cards reference.
"""
from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional

from . import media
from .db import CARD_COLUMNS, Database
from .models import to_iso, utcnow

PACK_FORMAT = "flashpack"
PACK_VERSION = 1
PACK_SUFFIX = ".flashpack"

MODE_MERGE = "merge"
MODE_REPLACE = "replace"


class PackError(Exception):
    """The file is not a valid flashcard pack."""


@dataclass
class ImportResult:
    classes: int
    chapters: int
    cards: int
    backup_path: Optional[Path] = None


def _rows(db: Database, table: str, columns: tuple[str, ...]) -> list[dict]:
    rows = db.conn.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY id")
    return [dict(r) for r in rows]


def export_pack(db: Database, dest: Path) -> Path:
    """Write every class, chapter, card, review and referenced image to `dest`."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "format": PACK_FORMAT,
        "schema_version": PACK_VERSION,
        "exported_at": to_iso(utcnow()),
        "classes": _rows(db, "classes", ("id", "name", "created_at")),
        "chapters": _rows(db, "chapters", ("id", "class_id", "name", "position")),
        "cards": _rows(db, "cards", CARD_COLUMNS),
        "reviews": _rows(db, "reviews", ("id", "card_id", "rating", "reviewed_at")),
    }
    folder = Path(db.data_dir) / media.MEDIA_DIRNAME
    names = media.referenced_files(c[k] for c in data["cards"] for k in ("front_html", "back_html"))

    tmp = dest.with_name(dest.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False))
        for name in sorted(names):
            path = folder / name
            if path.is_file():
                zf.write(path, f"{media.MEDIA_DIRNAME}/{name}")
    os.replace(tmp, dest)
    return dest


def _read_data(zf: zipfile.ZipFile) -> dict:
    try:
        data = json.loads(zf.read("data.json").decode("utf-8"))
    except KeyError as exc:
        raise PackError("The file has no data.json - it is not a flashcard export.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackError("The file's data.json is corrupted.") from exc
    if not isinstance(data, dict) or data.get("format") != PACK_FORMAT:
        raise PackError("The file is not a flashcard export.")
    version = data.get("schema_version")
    if not isinstance(version, int) or version > PACK_VERSION:
        raise PackError("The file was made by a newer version of the app.")
    for key in ("classes", "chapters", "cards", "reviews"):
        if not isinstance(data.get(key), list):
            raise PackError(f"The file's data.json is missing '{key}'.")
    return data


def _extract_media(zf: zipfile.ZipFile, data_dir: Path) -> None:
    folder = media.media_dir(data_dir)
    prefix = media.MEDIA_DIRNAME + "/"
    for info in zf.infolist():
        if info.is_dir() or not info.filename.startswith(prefix):
            continue
        name = PurePosixPath(info.filename).name
        target = folder / name
        # Names are UUIDs, so an existing file is the same image - skip it.
        if media.is_safe_name(name) and not target.exists():
            target.write_bytes(zf.read(info))


def _unique_name(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    candidate = f"{name} (imported)"
    n = 2
    while candidate in taken:
        candidate = f"{name} (imported {n})"
        n += 1
    return candidate


def import_pack(db: Database, path: Path, mode: str = MODE_MERGE,
                backup_dir: Optional[Path] = None) -> ImportResult:
    """Load a pack. `merge` adds its classes alongside existing ones;
    `replace` deletes everything first (after saving a backup pack)."""
    if mode not in (MODE_MERGE, MODE_REPLACE):
        raise ValueError(f"unknown import mode {mode!r}")
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackError(f"Could not open the file: {exc}") from exc

    with zf:
        data = _read_data(zf)
        backup_path = None
        if mode == MODE_REPLACE:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir = Path(backup_dir or Path(db.data_dir) / "backups")
            backup_path = export_pack(db, backup_dir / f"before-import-{stamp}{PACK_SUFFIX}")
        _extract_media(zf, db.data_dir)

    conn = db.conn
    now = to_iso(utcnow())
    class_map: dict[int, int] = {}
    chapter_map: dict[int, int] = {}
    card_map: dict[int, int] = {}
    try:
        with conn:
            if mode == MODE_REPLACE:
                conn.execute("DELETE FROM classes")
            taken = {r[0] for r in conn.execute("SELECT name FROM classes")}

            for c in data["classes"]:
                name = _unique_name(str(c.get("name") or "Untitled class"), taken)
                taken.add(name)
                cur = conn.execute("INSERT INTO classes (name, created_at) VALUES (?, ?)",
                                   (name, c.get("created_at") or now))
                class_map[c["id"]] = cur.lastrowid

            for ch in data["chapters"]:
                class_id = class_map.get(ch.get("class_id"))
                if class_id is None:
                    continue
                cur = conn.execute(
                    "INSERT INTO chapters (class_id, name, position) VALUES (?, ?, ?)",
                    (class_id, str(ch.get("name") or "Untitled chapter"),
                     int(ch.get("position") or 0)))
                chapter_map[ch["id"]] = cur.lastrowid

            columns = [c for c in CARD_COLUMNS if c != "id"]
            insert_card = (f"INSERT INTO cards ({', '.join(columns)}) "
                           f"VALUES ({', '.join('?' for _ in columns)})")
            defaults = {"front_html": "", "back_html": "", "created_at": now, "ease": 2.5,
                        "interval_days": 0.0, "repetitions": 0, "lapses": 0}
            for card in data["cards"]:
                chapter_id = chapter_map.get(card.get("chapter_id"))
                if chapter_id is None:
                    continue
                values = {k: v for k, v in card.items() if v is not None}
                values["chapter_id"] = chapter_id
                cur = conn.execute(insert_card,
                                   [values.get(col, defaults.get(col)) for col in columns])
                card_map[card["id"]] = cur.lastrowid

            conn.executemany(
                "INSERT INTO reviews (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
                [(card_map[r["card_id"]], int(r["rating"]), r["reviewed_at"])
                 for r in data["reviews"]
                 if r.get("card_id") in card_map and r.get("reviewed_at")])
    except (KeyError, TypeError, ValueError) as exc:
        raise PackError(f"The file's data is malformed: {exc}") from exc

    return ImportResult(len(class_map), len(chapter_map), len(card_map), backup_path)
