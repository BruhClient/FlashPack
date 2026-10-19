"""Class page: a row of figures and a few charts that speak for themselves (details on hover)."""
from __future__ import annotations

from datetime import timedelta
from typing import Callable, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from ..db import Database
from ..models import utcnow
from ..stats import class_stats, review_activity
from .animations import count_up
from .chapter_view import EmptyState
from .charts import ActivityChart, CardGrid, ChapterChart, ChapterRow, StatusLegend
from .dialogs import EditableTitle, button, hairline, more_button

ACTIVITY_DAYS = 30


class Figure(QWidget):
    """Big serif number over a small caption; the number counts up when it changes."""

    def __init__(self, caption: str, left_pad: int = 0, parent=None):
        super().__init__(parent)
        self._last = 0.0
        self.value = QLabel("—")
        self.value.setObjectName("figureValue")
        caption_label = QLabel(caption)
        caption_label.setObjectName("figureCaption")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(left_pad, 14, 12, 14)
        layout.setSpacing(0)
        layout.addWidget(self.value)
        layout.addWidget(caption_label)

    def set(self, value: Optional[float], fmt: Callable[[float], str] = lambda v: str(round(v)),
            tone: str = "") -> None:
        if self.value.property("tone") != tone:
            self.value.setProperty("tone", tone)
            self.value.style().unpolish(self.value)
            self.value.style().polish(self.value)
        if value is None:
            self.value.setText("—")
            self._last = 0.0
            return
        count_up(self.value, self._last, value, fmt)
        self._last = value


class Section(QWidget):
    """Serif heading (optional widget on the right), a hairline, then the content. No box."""

    def __init__(self, title: str, content: QWidget, extra: Optional[QWidget] = None, parent=None):
        super().__init__(parent)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        title_row = QHBoxLayout()
        title_row.addWidget(heading)
        title_row.addStretch(1)
        if extra is not None:
            title_row.addWidget(extra)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(title_row)
        layout.addSpacing(8)
        layout.addWidget(hairline())
        layout.addSpacing(14)
        layout.addWidget(content)


def _vertical_rule() -> QFrame:
    line = QFrame()
    line.setObjectName("ruleSoft")
    line.setFixedWidth(1)
    return line


class ClassDashboard(QWidget):
    start_test_requested = pyqtSignal(int)
    open_chapter_requested = pyqtSignal(int)
    add_chapter_requested = pyqtSignal(int)
    renamed = pyqtSignal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.class_id: Optional[int] = None
        # Set by the main window: fills the '⋯' menu (rename / new chapter / delete).
        self.menu_builder: Optional[Callable[[QMenu], None]] = None

        self.title = EditableTitle()
        self.title.renamed.connect(self._rename)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        add_chapter = button("Chapter", "plus", slot=self._request_add_chapter)
        add_chapter.setToolTip("Add a chapter")
        self.start = button("Start test", "play", "primary", self._request_test)
        self.start.setObjectName("startButton")

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(more_button(self._build_menu, "Class actions"))
        header.addWidget(add_chapter)
        header.addSpacing(4)
        header.addWidget(self.start)

        self.fig_mastery = Figure("Mastery")
        self.fig_due = Figure("Due today", 24)
        self.fig_untested = Figure("Untested", 24)
        self.fig_cards = Figure("Cards", 24)
        figures = QHBoxLayout()
        figures.setSpacing(0)
        for i, fig in enumerate((self.fig_mastery, self.fig_due, self.fig_untested, self.fig_cards)):
            if i:
                figures.addWidget(_vertical_rule())
            figures.addWidget(fig, 1)
        band = QVBoxLayout()
        band.setSpacing(0)
        band.addWidget(hairline())
        band.addLayout(figures)
        band.addWidget(hairline())

        self.chapters = ChapterChart()
        self.chapters.clicked.connect(self._open_chapter)
        self.grid = CardGrid()
        self.activity = ActivityChart()
        self.activity_total = QLabel()
        self.activity_total.setObjectName("sectionNote")

        bottom = QHBoxLayout()
        bottom.setSpacing(48)
        bottom.addWidget(Section("Cards", self.grid), 1)
        bottom.addWidget(Section(f"Last {ACTIVITY_DAYS} days", self.activity, self.activity_total), 1)

        charts = QWidget()
        charts_layout = QVBoxLayout(charts)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(36)
        charts_layout.addLayout(band)
        charts_layout.addWidget(Section("Chapters", self.chapters, StatusLegend()))
        charts_layout.addLayout(bottom)
        charts_layout.addStretch(1)

        self.empty = EmptyState("layers", "", "")
        self.body = QStackedWidget()
        self.body.addWidget(charts)
        self.body.addWidget(self.empty)
        self.charts = charts

        content = QWidget()
        content.setObjectName("scrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 32, 40, 32)
        content_layout.setSpacing(24)
        content_layout.addLayout(header)
        content_layout.addWidget(self.body, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _request_test(self) -> None:
        if self.class_id is not None:
            self.start_test_requested.emit(self.class_id)

    def _request_add_chapter(self) -> None:
        if self.class_id is not None:
            self.add_chapter_requested.emit(self.class_id)

    def _build_menu(self, menu: QMenu) -> None:
        if self.menu_builder is not None and self.class_id is not None:
            self.menu_builder(menu)

    def _rename(self, name: str) -> None:
        if self.class_id is not None:
            self.db.rename_class(self.class_id, name)
            self.renamed.emit()

    def _open_chapter(self, chapter_id) -> None:
        if chapter_id is not None:
            self.open_chapter_requested.emit(int(chapter_id))

    def show_class(self, class_id: int) -> None:
        self.class_id = class_id
        self.refresh()

    def refresh(self) -> None:
        cls = self.db.get_class(self.class_id) if self.class_id else None
        if cls is None:
            return
        now = utcnow()
        chapters = self.db.list_chapters(cls.id)
        overall, per_chapter = class_stats(chapters, self.db.list_cards_for_class(cls.id), now)

        self.title.setText(cls.name)
        self.subtitle.setText(f"{len(chapters)} chapter{'s' if len(chapters) != 1 else ''}")
        self.start.setEnabled(overall.total > 0)

        if not chapters or overall.total == 0:
            if not chapters:
                self.empty.set_text("No chapters yet", "Add one with the Chapter button.")
            else:
                self.empty.set_text("No cards yet", "Open a chapter to add cards.")
            self.body.setCurrentWidget(self.empty)
            return
        self.body.setCurrentWidget(self.charts)

        self.fig_mastery.set(None if overall.proficiency is None else overall.proficiency * 100,
                             lambda v: f"{round(v)}%")
        self.fig_due.set(overall.due_today, tone="danger" if overall.due_today else "")
        self.fig_untested.set(overall.untested)
        self.fig_cards.set(overall.total)

        self.chapters.set_rows([ChapterRow(s.key, s.name, s.counts, s.proficiency, s.due_today)
                                for s in per_chapter])
        self.grid.set_counts(overall.counts)
        times = self.db.review_times_for_class(cls.id, now - timedelta(days=ACTIVITY_DAYS + 1))
        activity = review_activity(times, now, ACTIVITY_DAYS)
        self.activity.set_data(activity)
        total = sum(n for _, n in activity)
        self.activity_total.setText(f"{total} review{'s' if total != 1 else ''}" if total else "")
