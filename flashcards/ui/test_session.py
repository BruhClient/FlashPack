"""Test session page: show front, reveal back, rate 1-5, repeat; then a summary."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ..db import Database
from ..models import Card, utcnow
from ..scheduler import RATING_LABELS, StudySession, apply_rating, apply_update
from ..stats import count_due, end_of_local_day
from . import theme
from .animations import FAST, NORMAL, crossfade, fade_in, glide
from .charts import BarRow, HBarChart
from .class_dashboard import Section
from .dialogs import button, hairline, icon_button
from .rich_text import CardViewer

RATING_COLOR_KEYS = {1: "r1", 2: "r2", 3: "r3", 4: "r4", 5: "r5"}
PROGRESS_SCALE = 1000


class IndexCard(QFrame):
    """The study card, drawn as a ruled index card lying on a small stack of others."""

    HEADER_H = 48    # the chapter name sits above the red rule
    STACK = 5        # how far the card underneath peeks out
    RADIUS = 5

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5 - self.STACK, -0.5 - self.STACK)
        p.setPen(QPen(theme.color("border"), 1))
        p.setBrush(theme.color("surface"))
        p.drawRoundedRect(card.translated(self.STACK, self.STACK), self.RADIUS, self.RADIUS)
        p.drawRoundedRect(card, self.RADIUS, self.RADIUS)
        p.setPen(QPen(theme.color("rule"), 1.5))
        y = card.top() + self.HEADER_H
        p.drawLine(QPointF(card.left() + 1, y), QPointF(card.right() - 1, y))


class RatingKey(QPushButton):
    """A keycap: the stylesheet draws the key, this paints its number and label.
    The number is coloured along the rating scale; the key's lower edge takes the colour on hover."""

    def __init__(self, rating: int, label: str, parent=None):
        super().__init__(parent)
        self.rating = rating
        self.label = label
        self.setObjectName("ratingButton")
        self.setProperty("rating", str(rating))
        self.setToolTip(f"{label} (press {rating})")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        number_font = theme.serif_font(15)
        label_font = self.font()
        label_font.setPointSizeF(self.font().pointSizeF() * 0.9)
        nh, lh = QFontMetrics(number_font).height(), QFontMetrics(label_font).height()
        top = (self.height() - 2 - nh - lh) / 2     # the key's thicker bottom edge takes 2px
        p.setFont(number_font)
        p.setPen(theme.color(RATING_COLOR_KEYS[self.rating]))
        p.drawText(QRectF(0, top, self.width(), nh), Qt.AlignmentFlag.AlignCenter, str(self.rating))
        p.setFont(label_font)
        p.setPen(theme.color("muted"))
        p.drawText(QRectF(0, top + nh - 2, self.width(), lh), Qt.AlignmentFlag.AlignCenter, self.label)


class TestSessionView(QWidget):
    finished = pyqtSignal(int)   # class id

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.session: Optional[StudySession] = None
        self.class_id: Optional[int] = None
        self.chapter_ids: list[int] = []
        self.chapter_names: dict[int, str] = {}
        self.revealed = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.pages = QStackedWidget()
        self.question_page = self._build_question_page()
        self.summary_page = self._build_summary_page()
        self.pages.addWidget(self.question_page)
        self.pages.addWidget(self.summary_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pages)

        def shortcut(keys: str, slot) -> None:
            sc = QShortcut(QKeySequence(keys), self, slot)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        shortcut("Space", self._reveal)
        shortcut("Return", self._reveal)
        for rating in RATING_LABELS:
            shortcut(str(rating), lambda r=rating: self._rate(r))
        shortcut("Escape", self._end_early)

    # ---- layout ----------------------------------------------------------
    def _build_question_page(self) -> QWidget:
        page = QWidget()
        end = icon_button("x", "End test (Esc)", self._end_early)
        end.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.heading = QLabel()
        self.heading.setObjectName("pageSubtitle")
        self.counter = QLabel()
        self.counter.setObjectName("counter")
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(end)
        top.addWidget(self.heading)
        top.addStretch(1)
        top.addWidget(self.counter)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(2)

        self.card = IndexCard()
        self.chapter_tag = QLabel()
        self.chapter_tag.setObjectName("chapterTag")
        self.chapter_tag.setFixedHeight(IndexCard.HEADER_H - 12)
        self.front = CardViewer(self.db.data_dir)
        self.divider = hairline(soft=True)
        self.back = CardViewer(self.db.data_dir)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(30, 12, 30 + IndexCard.STACK, 22 + IndexCard.STACK)
        card_layout.setSpacing(8)
        card_layout.addWidget(self.chapter_tag)
        card_layout.addSpacing(10)
        card_layout.addWidget(self.front, 1)
        card_layout.addWidget(self.divider)
        card_layout.addWidget(self.back, 1)

        self.reveal_btn = button("Show answer", "eye", "primary", self._reveal)
        self.reveal_btn.setObjectName("revealButton")
        self.reveal_btn.setToolTip("Space")
        self.reveal_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.rating_bar = QWidget()
        ratings = QHBoxLayout(self.rating_bar)
        ratings.setContentsMargins(0, 0, 0, 0)
        ratings.setSpacing(8)
        prompt = QLabel("How well did you know it?")
        prompt.setObjectName("muted")
        ratings.addWidget(prompt)
        ratings.addStretch(1)
        for rating, label in RATING_LABELS.items():
            key = RatingKey(rating, label)
            key.clicked.connect(lambda _=False, r=rating: self._rate(r))
            ratings.addWidget(key)

        self.bottom = QStackedWidget()
        self.bottom.addWidget(self.reveal_btn)
        self.bottom.addWidget(self.rating_bar)
        self.bottom.setFixedHeight(64)

        hint = QLabel("Space to reveal  ·  1–5 to rate  ·  Esc to end")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 24, 56, 18)
        layout.setSpacing(14)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        layout.addSpacing(6)
        layout.addWidget(self.card, 1)
        layout.addSpacing(4)
        layout.addWidget(self.bottom)
        layout.addWidget(hint)
        return page

    def _build_summary_page(self) -> QWidget:
        page = QWidget()
        self.summary_title = QLabel("Session complete")
        self.summary_title.setObjectName("pageTitle")
        self.summary_text = QLabel()
        self.summary_text.setObjectName("pageSubtitle")
        self.summary_text.setWordWrap(True)
        self.distribution = HBarChart(label_width=120, right_width=60)

        back = button("Back to class", "arrow-left", "primary", self._finish)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(back)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 48, 56, 28)
        layout.setSpacing(6)
        layout.addWidget(self.summary_title)
        layout.addWidget(self.summary_text)
        layout.addSpacing(32)
        layout.addWidget(Section("First-try ratings", self.distribution))
        layout.addStretch(1)
        layout.addLayout(row)
        return page

    # ---- flow ------------------------------------------------------------
    def start(self, class_id: int, class_name: str, chapter_ids: list[int],
              chapter_names: dict[int, str], cards: list[Card]) -> None:
        self.class_id = class_id
        self.chapter_ids = chapter_ids
        self.chapter_names = chapter_names
        self.session = StudySession(cards)
        self.heading.setText(f"{class_name}  ·  Test")
        self.progress.setRange(0, max(self.session.total, 1) * PROGRESS_SCALE)
        self.progress.setValue(0)
        self.pages.setCurrentWidget(self.question_page)
        self._show_current()
        self.setFocus()

    def _show_current(self) -> None:
        card = self.session.current if self.session else None
        if card is None:
            self._show_summary()
            return
        self.revealed = False
        self.chapter_tag.setText(self.chapter_names.get(card.chapter_id, ""))
        self.front.show_html(card.front_html)
        self.back.show_html(card.back_html or
                            f"<p style='color:{theme.tokens()['faint']}'>(no answer)</p>")
        self.back.hide()
        self.divider.hide()
        self.bottom.setCurrentWidget(self.reveal_btn)
        done = len(self.session.passed)
        self.counter.setText(f"{done} / {self.session.total}")
        glide(self.progress, done * PROGRESS_SCALE)

    def _reveal(self) -> None:
        if self.pages.currentWidget() is not self.question_page or self.session is None \
                or self.session.finished or self.revealed:
            return
        self.revealed = True
        self.divider.show()
        self.back.show()
        fade_in(self.back, NORMAL + 60)
        crossfade(self.bottom, lambda: self.bottom.setCurrentWidget(self.rating_bar), FAST)

    def _rate(self, rating: int) -> None:
        if not self.revealed or self.session is None or self.session.finished:
            return
        card = self.session.current
        update = apply_rating(card, rating, utcnow(), self.session.is_first_attempt(card))
        self.db.record_review(card.id, rating, update)
        apply_update(card, update)
        self.session.rate(rating)
        if self.session.finished:
            self._show_current()
        else:
            crossfade(self.question_page, self._show_current, NORMAL)

    def _end_early(self) -> None:
        if self.pages.currentWidget() is not self.question_page or self.session is None:
            return
        if self.session.attempts == 0:
            self._finish()
        else:
            self._show_summary(ended_early=True)

    def _show_summary(self, ended_early: bool = False) -> None:
        s = self.session
        reviewed = len(s.first_ratings)
        cards = self.db.list_cards_for_chapters(self.chapter_ids)
        due_tomorrow = count_due(cards, end_of_local_day(utcnow(), days_ahead=1))
        relearned = sum(1 for r in s.first_ratings.values() if r <= 2)
        parts = [f"You reviewed {reviewed} card{'s' if reviewed != 1 else ''}"]
        if relearned:
            parts.append(f"relearned {relearned}")

        def show():
            self.summary_title.setText("Test ended" if ended_early else "Session complete")
            self.summary_text.setText(
                ", ".join(parts) + f".  {due_tomorrow} card{'s' if due_tomorrow != 1 else ''} "
                "in these chapters will be due by tomorrow.")
            self.pages.setCurrentWidget(self.summary_page)
            dist = s.rating_distribution()
            peak = max(dist.values()) or 1
            self.distribution.set_rows([
                BarRow(None, f"{r}  {RATING_LABELS[r]}", dist[r] / peak, str(dist[r]),
                       color=theme.color(RATING_COLOR_KEYS[r]))
                for r in sorted(RATING_LABELS, reverse=True)])

        glide(self.progress, len(s.passed) * PROGRESS_SCALE)
        crossfade(self.pages, show, NORMAL + 60)

    def _finish(self) -> None:
        class_id = self.class_id
        self.session = None
        self.finished.emit(class_id)
