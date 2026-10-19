"""Dialog for creating or editing a card's front and back."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from .dialogs import FadeDialog, button
from .rich_text import RichTextEditor


class CardEditorDialog(FadeDialog):
    """Emits `card_saved(front_html, back_html)` for every save.

    In "add" mode there is also "Save & add another", which keeps the dialog open.
    """

    card_saved = pyqtSignal(str, str)

    def __init__(self, data_dir: Path, parent=None, front: str = "", back: str = "",
                 adding: bool = True, chapter_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("New card" if adding else "Edit card")
        self.resize(800, 740)
        self.saved_count = 0

        title = QLabel("New card" if adding else "Edit card")
        title.setObjectName("dialogTitle")
        subtitle = QLabel(chapter_name)
        subtitle.setObjectName("muted")
        subtitle.setVisible(bool(chapter_name))
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(title)
        header.addWidget(subtitle)

        self.front = RichTextEditor(data_dir, "Question, term or prompt…")
        self.back = RichTextEditor(data_dir, "Answer…")
        self.front.set_html(front)
        self.back.set_html(back)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.hide()

        buttons = QHBoxLayout()
        if adding:
            again = button("Save && add another", "plus", slot=self._save_and_continue)
            again.setAutoDefault(False)
            again.setToolTip("Ctrl+Shift+Enter")
            buttons.addWidget(again)
            QShortcut(QKeySequence("Ctrl+Shift+Return"), self, self._save_and_continue)
        buttons.addWidget(self.error)
        buttons.addStretch(1)
        cancel = button("Cancel", slot=self.reject)
        cancel.setAutoDefault(False)
        save = button("Save", "check", "primary", self._save_and_close)
        save.setAutoDefault(False)
        save.setToolTip("Ctrl+Enter")
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._save_and_close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addSpacing(10)
        layout.addWidget(self._section("Front"))
        layout.addWidget(self.front, 1)
        layout.addSpacing(10)
        layout.addWidget(self._section("Back"))
        layout.addWidget(self.back, 1)
        layout.addSpacing(8)
        layout.addLayout(buttons)

        self.front.edit.setFocus()

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _emit(self) -> bool:
        if self.front.is_empty():
            self.error.setText("The front of the card can't be empty.")
            self.error.show()
            self.front.edit.setFocus()
            return False
        self.error.hide()
        self.card_saved.emit(self.front.html(), self.back.html())
        self.saved_count += 1
        return True

    def _save_and_close(self) -> None:
        if self._emit():
            self.accept()

    def _save_and_continue(self) -> None:
        if self._emit():
            self.front.clear()
            self.back.clear()
            self.front.edit.setFocus()
