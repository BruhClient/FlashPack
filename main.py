"""Flashcards - run with `python main.py`.

Data lives in the per-user app data folder (on Windows %APPDATA%\\Flagship).
Set FLAGSHIP_DATA_DIR to use a different folder.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication

from flashcards import media
from flashcards.db import Database
from flashcards.ui import theme
from flashcards.ui.main_window import MainWindow


def data_dir() -> Path:
    override = os.environ.get("FLAGSHIP_DATA_DIR")
    if override:
        return Path(override)
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Flagship")
    app.setApplicationDisplayName("Flashcards")
    theme.install(app)  # light/dark from the saved choice, else the OS setting

    db = Database(data_dir() / "flashcards.db")
    media.cleanup_orphans(db.data_dir, db.all_card_html())

    window = MainWindow(db)
    window.show()
    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
