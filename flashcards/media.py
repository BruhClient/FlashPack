"""Image files referenced from card HTML as relative `media/<name>` paths."""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Iterable, Optional

MEDIA_DIRNAME = "media"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

_EXT_PATTERN = r"(?:png|jpe?g|gif|bmp|webp)"
_SAFE_NAME = re.compile(rf"^[A-Za-z0-9_-]+\.{_EXT_PATTERN}$", re.IGNORECASE)
_REFERENCE = re.compile(rf"{MEDIA_DIRNAME}/([A-Za-z0-9_-]+\.{_EXT_PATTERN})", re.IGNORECASE)
_REFERENCE_SUFFIX = re.compile(rf"(?:^|/){MEDIA_DIRNAME}/([A-Za-z0-9_-]+\.{_EXT_PATTERN})$",
                               re.IGNORECASE)


def media_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / MEDIA_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_safe_name(name: str) -> bool:
    return bool(_SAFE_NAME.match(name))


def new_media_name(ext: str = ".png") -> str:
    ext = ext.lower()
    if ext not in IMAGE_EXTS:
        ext = ".png"
    return uuid.uuid4().hex + ext


def reference(name: str) -> str:
    """The relative path stored in card HTML."""
    return f"{MEDIA_DIRNAME}/{name}"


def resolve(data_dir: Path, ref: str) -> Optional[Path]:
    """Absolute path for a `media/<name>` reference (relative, or already resolved
    to a file URL by Qt), or None if it isn't one of ours."""
    match = _REFERENCE_SUFFIX.search(ref.strip())
    return Path(data_dir) / MEDIA_DIRNAME / match.group(1) if match else None


def import_image_file(data_dir: Path, src: Path) -> str:
    """Copy an image file into the media folder and return its reference."""
    name = new_media_name(Path(src).suffix)
    shutil.copyfile(src, media_dir(data_dir) / name)
    return reference(name)


def referenced_files(htmls: Iterable[str]) -> set[str]:
    names: set[str] = set()
    for html in htmls:
        names.update(_REFERENCE.findall(html or ""))
    return names


def cleanup_orphans(data_dir: Path, htmls: Iterable[str]) -> int:
    """Delete media files no card refers to (e.g. images from a cancelled edit)."""
    folder = Path(data_dir) / MEDIA_DIRNAME
    if not folder.is_dir():
        return 0
    keep = referenced_files(htmls)
    removed = 0
    for path in folder.iterdir():
        if path.is_file() and is_safe_name(path.name) and path.name not in keep:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
