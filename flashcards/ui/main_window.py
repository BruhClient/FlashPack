"""Main window: sidebar navigation + animated page stack, export/import, theme switching."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import QFileDialog, QMainWindow, QSplitter

from ..db import Database
from ..scheduler import build_session
from ..transfer import PACK_SUFFIX, PackError, export_pack, import_pack
from . import theme
from .animations import FadeStack, crossfade
from .chapter_view import ChapterView, EmptyState
from .class_dashboard import ClassDashboard
from .dialogs import alert, button, choose_import_mode
from .sidebar import Sidebar
from .test_session import TestSessionView
from .test_setup import TestSetupDialog
from .toast import Toast

THEME_FADE_MS = 320


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("Flashcards")
        self.resize(1220, 800)
        self.setMinimumSize(940, 620)

        self.sidebar = Sidebar(db)
        self.welcome = EmptyState(
            "graduation-cap", "Welcome to Flashcards",
            "Create a class, add chapters to it, then fill them with cards.\n"
            "Coming from another device? Use the import button at the bottom of the sidebar.",
            button("New class", "plus", "primary", self.sidebar.new_class))
        self.dashboard = ClassDashboard(db)
        self.chapter_view = ChapterView(db)
        self.session_view = TestSessionView(db)

        self.stack = FadeStack()
        for page in (self.welcome, self.dashboard, self.chapter_view, self.session_view):
            self.stack.addWidget(page)

        splitter = QSplitter()
        splitter.setHandleWidth(1)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 960])
        splitter.setChildrenCollapsible(False)
        self.sidebar.setMinimumWidth(220)
        self.setCentralWidget(splitter)
        self.toast = Toast(self)

        self.sidebar.class_selected.connect(self._show_class)
        self.sidebar.chapter_selected.connect(self._show_chapter)
        self.sidebar.nothing_selected.connect(lambda: self.stack.fade_to(self.welcome))
        self.sidebar.cards_dropped.connect(self._move_cards)
        self.sidebar.structure_changed.connect(self._refresh_current)
        self.sidebar.theme_toggle_requested.connect(self.toggle_theme)
        self.sidebar.import_requested.connect(self.import_data)
        self.sidebar.export_requested.connect(self.export_data)
        self.sidebar.open_folder_requested.connect(self._open_data_folder)
        self.dashboard.start_test_requested.connect(self._start_test)
        self.dashboard.open_chapter_requested.connect(self.sidebar.select_chapter)
        self.dashboard.add_chapter_requested.connect(self.sidebar.new_chapter)
        self.dashboard.renamed.connect(self.sidebar.refresh)
        self.chapter_view.changed.connect(self.sidebar.refresh)
        self.session_view.finished.connect(self._end_test)
        # The pages' '⋯' menus offer the same actions as the sidebar's, but rename in place.
        self.dashboard.menu_builder = lambda menu: self.sidebar.build_class_menu(
            menu, self.dashboard.class_id, self.dashboard.title.start_edit)
        self.chapter_view.menu_builder = lambda menu: self.sidebar.build_chapter_menu(
            menu, self.chapter_view.chapter_id, self.chapter_view.title.start_edit)

        self.nav_actions = [
            self._shortcut("Ctrl+Shift+N", self.sidebar.new_class),
            self._shortcut("Ctrl+E", self.export_data),
            self._shortcut("Ctrl+I", self.import_data),
        ]
        self._shortcut("Ctrl+Shift+L", self.toggle_theme)
        self._shortcut("Ctrl+Q", self.close)

        self.sidebar.refresh()
        self.sidebar.select_first()

    def _shortcut(self, keys: str, slot) -> QAction:
        act = QAction(self)
        act.setShortcut(QKeySequence(keys))
        act.triggered.connect(lambda _checked=False: slot())
        self.addAction(act)
        return act

    # ---- theme -----------------------------------------------------------
    def toggle_theme(self) -> None:
        manager = theme.manager()
        if manager is not None:
            crossfade(self, manager.toggle, THEME_FADE_MS)

    # ---- navigation ------------------------------------------------------
    def _show_class(self, class_id: int) -> None:
        self.dashboard.show_class(class_id)
        self.stack.fade_to(self.dashboard)

    def _show_chapter(self, chapter_id: int) -> None:
        self.chapter_view.show_chapter(chapter_id)
        self.stack.fade_to(self.chapter_view)

    def _refresh_current(self) -> None:
        page = self.stack.currentWidget()
        if page is self.dashboard:
            self.dashboard.refresh()
        elif page is self.chapter_view:
            self.chapter_view.refresh()

    def _move_cards(self, card_ids: list[int], chapter_id: int) -> None:
        chapter = self.db.get_chapter(chapter_id)
        if chapter is None or not card_ids:
            return
        self.db.move_cards(card_ids, chapter_id)
        self.sidebar.refresh()
        self._refresh_current()
        n = len(card_ids)
        self.toast.show_message(f"Moved {n} card{'s' if n != 1 else ''} to {chapter.name}",
                                "folder-input")

    # ---- tests -----------------------------------------------------------
    def _start_test(self, class_id: int) -> None:
        dialog = TestSetupDialog(self.db, class_id, self)
        if not dialog.exec():
            return
        chapter_ids = dialog.selected_chapter_ids()
        cards = build_session(self.db.list_cards_for_chapters(chapter_ids),
                              dialog.session_size(), dialog.include_untested())
        if not cards:
            alert(self, "Nothing to test", "There are no cards to test in the chosen chapters.")
            return
        cls = self.db.get_class(class_id)
        names = {ch.id: ch.name for ch in self.db.list_chapters(class_id)}
        self._set_navigation_enabled(False)
        self.session_view.start(class_id, cls.name, chapter_ids, names, cards)
        self.stack.fade_to(self.session_view)
        self.session_view.setFocus()

    def _end_test(self, class_id: int) -> None:
        self._set_navigation_enabled(True)
        self.sidebar.refresh()
        self.sidebar.select_class(class_id)
        self._show_class(class_id)

    def _set_navigation_enabled(self, enabled: bool) -> None:
        self.sidebar.setEnabled(enabled)
        for act in self.nav_actions:
            act.setEnabled(enabled)

    # ---- export / import -------------------------------------------------
    def export_data(self) -> None:
        default = Path.home() / f"flashcards-{date.today().isoformat()}{PACK_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export data", str(default), f"Flashcard export (*{PACK_SUFFIX})")
        if not path:
            return
        if not path.endswith(PACK_SUFFIX):
            path += PACK_SUFFIX
        try:
            export_pack(self.db, Path(path))
        except OSError as exc:
            alert(self, "Export failed", f"Could not write the file:\n{exc}")
            return
        self.toast.show_message(f"Exported everything to {Path(path).name}", "share")

    def import_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import data", str(Path.home()), f"Flashcard export (*{PACK_SUFFIX})")
        if not path:
            return
        mode = choose_import_mode(self)
        if mode is None:
            return
        try:
            result = import_pack(self.db, Path(path), mode)
        except (PackError, OSError) as exc:
            alert(self, "Import failed", str(exc))
            return

        self.sidebar.tree.clearSelection()
        self.sidebar.refresh()
        self.sidebar.select_first()
        message = (f"Imported {result.classes} class{'es' if result.classes != 1 else ''} and "
                   f"{result.cards} card{'s' if result.cards != 1 else ''}")
        if result.backup_path:
            message += " · previous data backed up"
        self.toast.show_message(message, "download")

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.db.data_dir)))
