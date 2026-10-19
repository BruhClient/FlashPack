"""Dialog to choose chapters and size for a class test."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout,
)

from ..db import Database
from ..models import utcnow
from ..stats import class_stats
from .dialogs import FadeDialog, button

DEFAULT_SESSION_SIZE = 20


class TestSetupDialog(FadeDialog):
    def __init__(self, db: Database, class_id: int, parent=None):
        super().__init__(parent)
        cls = db.get_class(class_id)
        self.setWindowTitle("Start test")
        self.resize(480, 560)

        _, per_chapter = class_stats(db.list_chapters(class_id),
                                     db.list_cards_for_class(class_id), utcnow())
        self._stats = {s.key: s for s in per_chapter}

        title = QLabel(f"Test · {cls.name}")
        title.setObjectName("dialogTitle")
        intro = QLabel("Due and weak cards come first, then untested ones.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(title)
        header.addWidget(intro)

        self.chapters = QListWidget()
        self.chapters.setObjectName("checkList")
        self.chapters.setSpacing(1)
        for s in per_chapter:
            item = QListWidgetItem(f"{s.name}\n{s.total} cards  ·  {s.due_today} due  ·  "
                                   f"{s.untested} untested")
            item.setData(Qt.ItemDataRole.UserRole, s.key)
            if s.total:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setCheckState(Qt.CheckState.Unchecked)
            self.chapters.addItem(item)
        self.chapters.itemChanged.connect(lambda *_: self._update())

        chapters_label = QLabel("Chapters")
        chapters_label.setObjectName("sectionLabel")
        chapter_row = QHBoxLayout()
        chapter_row.addWidget(chapters_label)
        chapter_row.addStretch(1)
        chapter_row.addWidget(button("All", variant="ghost", slot=lambda: self._check_all(True)))
        chapter_row.addWidget(button("None", variant="ghost", slot=lambda: self._check_all(False)))

        self.count = QSpinBox()
        self.count.setRange(1, 999)
        self.count.setValue(DEFAULT_SESSION_SIZE)
        self.count.setSuffix(" cards")
        self.count.setFixedWidth(130)
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Session size"))
        count_row.addStretch(1)
        count_row.addWidget(self.count)

        self.include_new = QCheckBox("Include untested cards")
        self.include_new.setChecked(True)
        self.include_new.toggled.connect(lambda *_: self._update())

        self.summary = QLabel()
        self.summary.setObjectName("muted")
        self.start = button("Start", "play", "primary", self.accept)
        self.start.setDefault(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.summary)
        buttons.addStretch(1)
        buttons.addWidget(button("Cancel", slot=self.reject))
        buttons.addWidget(self.start)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addSpacing(4)
        layout.addLayout(chapter_row)
        layout.addWidget(self.chapters, 1)
        layout.addLayout(count_row)
        layout.addWidget(self.include_new)
        layout.addSpacing(4)
        layout.addLayout(buttons)
        self._update()

    def _check_all(self, on: bool) -> None:
        for i in range(self.chapters.count()):
            item = self.chapters.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def selected_chapter_ids(self) -> list[int]:
        return [self.chapters.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.chapters.count())
                if self.chapters.item(i).checkState() == Qt.CheckState.Checked]

    def session_size(self) -> int:
        return self.count.value()

    def include_untested(self) -> bool:
        return self.include_new.isChecked()

    def _update(self) -> None:
        chosen = [self._stats[i] for i in self.selected_chapter_ids()]
        available = sum(s.total if self.include_untested() else s.tested for s in chosen)
        due = sum(s.due_today for s in chosen)
        self.summary.setText(f"{available} available  ·  {due} due")
        self.start.setEnabled(available > 0)
