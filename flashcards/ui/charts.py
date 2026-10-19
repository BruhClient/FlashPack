"""Hand-painted, theme-aware chart widgets that animate in when their data changes."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..stats import LEARNING, MASTERED, STATUS_LABELS, STRUGGLING, UNTESTED
from . import theme

GROW_MS = 750
# Best first, so bars and grids fill up from the left as cards get learned.
ORDER = (MASTERED, LEARNING, STRUGGLING, UNTESTED)
TILE_RATIO = 1.45     # card tiles have index-card proportions


def status_color(status: str) -> QColor:
    return theme.color(status)


def percent(value: Optional[float]) -> str:
    return "—" if value is None else f"{round(value * 100)}%"


def draw_tile(p: QPainter, rect: QRectF, color: QColor) -> None:
    radius = max(1.5, rect.height() / 9)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(rect, radius, radius)


def _legend_items(fm: QFontMetrics, counts: Optional[dict[str, int]]) -> list[tuple[str, str, float]]:
    items = []
    for status in ORDER:
        label = STATUS_LABELS[status]
        text = f"{counts.get(status, 0)} {label.lower()}" if counts is not None else label
        items.append((status, text, 16 + fm.horizontalAdvance(text)))
    return items


def draw_legend(p: QPainter, x: float, y: float, height: float, font: QFont,
                counts: Optional[dict[str, int]] = None, gap: float = 18) -> None:
    """■ Mastered  ■ Learning  … (with counts in front when given)."""
    fm = QFontMetrics(font)
    p.setFont(font)
    tile_h = 8
    for status, text, width in _legend_items(fm, counts):
        draw_tile(p, QRectF(x, y + (height - tile_h) / 2, round(tile_h * TILE_RATIO), tile_h),
                  status_color(status))
        p.setPen(theme.color("muted"))
        p.drawText(QRectF(x + 16, y, width, height),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        x += width + gap


class _Chart(QWidget):
    """Base: grow-in animation, hover tooltips, hover highlight and click-to-select."""

    clicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._regions: list[tuple[QRectF, str, Any]] = []
        self._hover_key: Any = None
        self._t = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(GROW_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)

    def animate(self) -> None:
        self._anim.stop()
        self._t = 0.0
        self._anim.start()

    def _step(self, value) -> None:
        self._t = float(value)
        self.update()

    def _hit(self, pos: QPointF) -> Optional[tuple[str, Any]]:
        for rect, tip, key in self._regions:
            if rect.contains(pos):
                return tip, key
        return None

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        key = hit[1] if hit else None
        if hit:
            QToolTip.showText(event.globalPosition().toPoint(), hit[0], self)
        else:
            QToolTip.hideText()
        if key is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        if key != self._hover_key:
            self._hover_key = key
            self.update()

    def mousePressEvent(self, event):
        hit = self._hit(event.position())
        if hit and hit[1] is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(hit[1])

    def leaveEvent(self, event):
        QToolTip.hideText()
        if self._hover_key is not None:
            self._hover_key = None
            self.update()
        super().leaveEvent(event)

    def _painter(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(self.font())
        return p

    @staticmethod
    def _rounded(p: QPainter, rect: QRectF, color: QColor, radius: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(rect, radius, radius)

    def _hover_row(self, p: QPainter, rect: QRectF, key: Any) -> None:
        if key is not None and key == self._hover_key:
            self._rounded(p, rect.adjusted(-8, 0, 8, 0), theme.color("hover"), 4)


@dataclass
class BarRow:
    key: Any
    label: str
    value: Optional[float]   # 0..1, None = nothing to show
    right_text: str
    color: Optional[QColor] = None
    tooltip: str = ""


class HBarChart(_Chart):
    """One thin horizontal bar per row, e.g. the rating spread after a test."""

    ROW_H = 32
    BAR_H = 8

    def __init__(self, parent=None, label_width=150, right_width=150):
        super().__init__(parent)
        self._rows: list[BarRow] = []
        self._label_w = label_width
        self._right_w = right_width

    def set_rows(self, rows: list[BarRow]) -> None:
        self._rows = rows
        self.setFixedHeight(max(len(rows), 1) * self.ROW_H)
        self.animate()

    def paintEvent(self, event):
        p = self._painter()
        self._regions = []
        fm = QFontMetrics(self.font())
        track_x = self._label_w + 12
        track_w = max(self.width() - track_x - self._right_w - 12, 20)
        for i, row in enumerate(self._rows):
            y = i * self.ROW_H
            row_rect = QRectF(0, y, self.width(), self.ROW_H)
            self._hover_row(p, row_rect, row.key)
            p.setPen(theme.color("text"))
            label = fm.elidedText(row.label, Qt.TextElideMode.ElideRight, self._label_w)
            p.drawText(QRectF(0, y, self._label_w, self.ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

            bar_y = y + (self.ROW_H - self.BAR_H) / 2
            self._rounded(p, QRectF(track_x, bar_y, track_w, self.BAR_H), theme.color("track"), 1.5)
            if row.value is not None and row.value > 0:
                color = row.color or theme.color("chart_accent")
                fill_w = max(track_w * min(row.value, 1.0) * self._t, 2)
                self._rounded(p, QRectF(track_x, bar_y, fill_w, self.BAR_H), color, 1.5)

            p.setPen(theme.color("muted"))
            p.drawText(QRectF(track_x + track_w + 12, y, self._right_w, self.ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, row.right_text)
            self._regions.append((row_rect, row.tooltip or f"{row.label}: {row.right_text}", row.key))
        if not self._rows:
            p.setPen(theme.color("muted"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nothing to show yet")


class StatusLegend(QWidget):
    """Colour key for the status tiles: ■ Mastered ■ Learning ■ Struggling ■ Untested."""

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        items = _legend_items(fm, None)
        width = sum(w for _, _, w in items) + 18 * (len(items) - 1)
        return QSize(int(width) + 2, fm.height() + 4)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_legend(p, 0, 0, self.height(), self.font())


@dataclass
class ChapterRow:
    key: Any
    label: str
    counts: dict[str, int]
    proficiency: Optional[float]
    due: int = 0


class ChapterChart(_Chart):
    """One row per chapter: its status mix as a segmented bar, mastery % on the right.
    Details live in the hover tooltip; click a row to open the chapter."""

    ROW_H = 38
    BAR_H = 8
    GAP = 2
    LABEL_W = 160
    VALUE_W = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[ChapterRow] = []

    def set_rows(self, rows: list[ChapterRow]) -> None:
        self._rows = rows
        self.setFixedHeight(max(len(rows), 1) * self.ROW_H)
        self.animate()

    @staticmethod
    def _tooltip(row: ChapterRow) -> str:
        total = sum(row.counts.values())
        mix = "  ·  ".join(f"{STATUS_LABELS[s]} {row.counts.get(s, 0)}" for s in ORDER)
        return (f"{row.label}\nMastery {percent(row.proficiency)}  ·  {total} cards"
                f"  ·  {row.due} due\n{mix}")

    def paintEvent(self, event):
        p = self._painter()
        self._regions = []
        fm = QFontMetrics(self.font())
        value_font = theme.serif_font(self.font().pointSizeF() * 1.35)
        track_x = self.LABEL_W + 12
        track_w = max(self.width() - track_x - self.VALUE_W - 16, 20)
        for i, row in enumerate(self._rows):
            y = i * self.ROW_H
            row_rect = QRectF(0, y, self.width(), self.ROW_H)
            self._hover_row(p, row_rect, row.key)
            p.setFont(self.font())
            p.setPen(theme.color("text"))
            label = fm.elidedText(row.label, Qt.TextElideMode.ElideRight, self.LABEL_W)
            p.drawText(QRectF(0, y, self.LABEL_W, self.ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

            total = sum(row.counts.values())
            bar_y = y + (self.ROW_H - self.BAR_H) / 2
            if not total:
                self._rounded(p, QRectF(track_x, bar_y, track_w, self.BAR_H), theme.color("track"), 1.5)
            parts = [(s, row.counts.get(s, 0)) for s in ORDER if row.counts.get(s, 0)]
            usable = track_w - self.GAP * (len(parts) - 1)
            visible_right = track_x + track_w * self._t
            x = track_x
            for status, n in parts:
                w = usable * n / total
                right = min(x + w, visible_right)
                if right > x:
                    self._rounded(p, QRectF(x, bar_y, right - x, self.BAR_H), status_color(status), 1.5)
                x += w + self.GAP

            p.setFont(value_font)
            p.setPen(theme.color("faint" if row.proficiency is None else "text"))
            p.drawText(QRectF(self.width() - self.VALUE_W, y, self.VALUE_W, self.ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       percent(row.proficiency))
            self._regions.append((row_rect, self._tooltip(row), row.key))


class CardGrid(_Chart):
    """Every card in the class as one small tile, coloured by status, best first.
    Tiles shrink to fit big classes; past that the proportions are kept."""

    HEIGHT = 196
    LEGEND_H = 28
    SIZES = (30, 26, 22, 18, 16, 14, 12, 10, 9, 8, 7, 6, 5, 4, 3)   # tile heights, largest first

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict[str, int] = {s: 0 for s in ORDER}
        self._grid: Optional[tuple[float, float, float, int, list[str]]] = None
        self.setFixedHeight(self.HEIGHT)

    def set_counts(self, counts: dict[str, int]) -> None:
        self._counts = dict(counts)
        self.animate()

    def _fit(self, n: int, width: float, height: float) -> tuple[float, float, float, int, int]:
        """Tile width, height, gap, columns and rows for the largest tiles that fit."""
        for th in self.SIZES:
            tw = round(th * TILE_RATIO)
            gap = 4 if th >= 14 else 3 if th >= 8 else 2 if th >= 5 else 1
            cols = max(int((width + gap) // (tw + gap)), 1)
            max_rows = max(int((height + gap) // (th + gap)), 1)
            if math.ceil(n / cols) <= max_rows:
                break
        return tw, th, gap, cols, max_rows

    def _hit(self, pos: QPointF):
        if not self._grid:
            return None
        tw, th, gap, cols, cells = self._grid
        col, row = int(pos.x() // (tw + gap)), int(pos.y() // (th + gap))
        index = row * cols + col
        if pos.x() < 0 or pos.y() < 0 or col >= cols or index >= len(cells):
            return None
        status = cells[index]
        n, total = self._counts.get(status, 0), sum(self._counts.values())
        return f"{STATUS_LABELS[status]}: {n} of {total} cards ({round(100 * n / total)}%)", None

    def paintEvent(self, event):
        p = self._painter()
        cells = [s for s in ORDER for _ in range(self._counts.get(s, 0))]
        tw, th, gap, cols, max_rows = self._fit(len(cells), self.width(),
                                                self.HEIGHT - self.LEGEND_H - 8)
        capacity = cols * max_rows
        if len(cells) > capacity:
            cells = [cells[i * len(cells) // capacity] for i in range(capacity)]
        self._grid = (tw, th, gap, cols, cells)
        for i, status in enumerate(cells[:math.ceil(len(cells) * self._t)]):
            row, col = divmod(i, cols)
            draw_tile(p, QRectF(col * (tw + gap), row * (th + gap), tw, th), status_color(status))
        rows = math.ceil(len(cells) / cols)
        legend_y = min(rows * (th + gap) - gap + 10, self.HEIGHT - self.LEGEND_H)
        draw_legend(p, 0, legend_y, self.LEGEND_H, self.font(), self._counts)


class ActivityChart(_Chart):
    """Reviews per day as thin ink bars over a baseline."""

    HEIGHT = CardGrid.HEIGHT   # sits beside the card grid
    AXIS_H = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[date, int]] = []
        self.setFixedHeight(self.HEIGHT)

    def set_data(self, data: list[tuple[date, int]]) -> None:
        self._data = data
        self.animate()

    def paintEvent(self, event):
        p = self._painter()
        self._regions = []
        if not self._data:
            return
        plot = QRectF(0, 4, self.width(), self.HEIGHT - 4 - self.AXIS_H)
        peak = max(n for _, n in self._data)
        p.setPen(QPen(theme.color("grid"), 1))
        p.drawLine(QPointF(plot.left(), plot.bottom() + 0.5), QPointF(plot.right(), plot.bottom() + 0.5))

        slot = plot.width() / len(self._data)
        bar_w = max(min(slot * 0.5, 12), 2)
        for i, (day, n) in enumerate(self._data):
            x = plot.left() + i * slot + (slot - bar_w) / 2
            if n:
                h = max(plot.height() * n / peak * self._t, 2)
                self._rounded(p, QRectF(x, plot.bottom() - h, bar_w, h), theme.color("chart_accent"), 1)
            tip = f"{day.strftime('%a %b')} {day.day}: {n} review{'s' if n != 1 else ''}"
            self._regions.append((QRectF(plot.left() + i * slot, plot.top(), slot, plot.height()),
                                  tip, None))

        if not peak:
            p.setPen(theme.color("faint"))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, "No reviews yet")

        p.setPen(theme.color("faint"))
        first = self._data[0][0]
        p.drawText(QRectF(0, plot.bottom() + 6, 120, self.AXIS_H - 6),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                   f"{first.strftime('%b')} {first.day}")
        p.drawText(QRectF(self.width() - 120, plot.bottom() + 6, 120, self.AXIS_H - 6),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, "Today")
