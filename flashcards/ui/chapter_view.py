"""Chapter page: filterable card list with add / edit / move / delete."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QByteArray, QMimeData, QModelIndex, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMenu, QPushButton, QStackedWidget, QStyle, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..db import Database
from ..models import Card, utcnow
from ..stats import STATUS_LABELS, STATUSES, UNTESTED, card_status
from . import icons, theme
from .animations import FAST, crossfade
from .card_editor import CardEditorDialog
from .charts import TILE_RATIO, draw_tile, status_color
from .dialogs import (
    EditableTitle, FadeDialog, SearchField, button, confirm, icon_button, more_button,
)
from .rich_text import plain_preview

CARD_IDS_MIME = "application/x-flagship-card-ids"

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_TITLE = Qt.ItemDataRole.UserRole + 1
ROLE_SUBTITLE = Qt.ItemDataRole.UserRole + 2
ROLE_STATUS = Qt.ItemDataRole.UserRole + 3

ALL = "all"


def due_label(card: Card, now: datetime) -> str:
    if card.is_new:
        return "Not tested yet"
    seconds = (card.due - now).total_seconds()
    if seconds <= 0:
        return "Due now"
    minutes = seconds / 60
    if minutes < 60:
        return f"Due in {max(int(minutes), 1)} min"
    hours = minutes / 60
    if hours < 24:
        return f"Due in {int(hours)} h"
    days = round(hours / 24)
    return f"Due in {days} day{'s' if days != 1 else ''}"


def _shortcut(keys: str, parent: QWidget, slot) -> QShortcut:
    sc = QShortcut(QKeySequence(keys), parent, slot)
    sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    return sc


class CardDelegate(QStyledItemDelegate):
    """Two-line row over a hairline: front preview, then a status tile + status / due / answer."""

    HEIGHT = 60
    TILE_H = 8

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("selection" if selected else "hover"))
            painter.drawRoundedRect(rect.adjusted(0, 1, 0, -1), 4, 4)
        else:
            painter.fillRect(QRectF(rect.left() + 10, rect.bottom(), rect.width() - 20, 1),
                             theme.color("border_soft"))

        font = option.font
        fm = QFontMetrics(font)
        x = rect.left() + 10
        width = int(rect.width() - 20)
        title = fm.elidedText(index.data(ROLE_TITLE) or "", Qt.TextElideMode.ElideRight, width)
        painter.setFont(font)
        painter.setPen(theme.color("text"))
        painter.drawText(QRectF(x, rect.top() + 10, width, fm.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

        sub_y = rect.top() + 13 + fm.height()
        tile_w = round(self.TILE_H * TILE_RATIO)
        draw_tile(painter, QRectF(x, sub_y + (fm.height() - self.TILE_H) / 2, tile_w, self.TILE_H),
                  status_color(index.data(ROLE_STATUS) or UNTESTED))
        small = fm.elidedText(index.data(ROLE_SUBTITLE) or "", Qt.TextElideMode.ElideRight,
                              width - tile_w - 8)
        painter.setPen(theme.color("muted"))
        painter.drawText(QRectF(x + tile_w + 8, sub_y, width - tile_w - 8, fm.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, small)
        painter.restore()


class CardList(QListWidget):
    """Card list whose rows can be dragged onto a chapter in the sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardList")
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setItemDelegate(CardDelegate(self))

    def mimeTypes(self):
        return [CARD_IDS_MIME]

    def mimeData(self, items):
        data = QMimeData()
        ids = [item.data(ROLE_ID) for item in items]
        data.setData(CARD_IDS_MIME, QByteArray(json.dumps(ids).encode()))
        return data

    def supportedDropActions(self):
        return Qt.DropAction.CopyAction


class MoveCardsDialog(FadeDialog):
    """Pick a destination chapter from any class."""

    def __init__(self, db: Database, current_chapter_id: int, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Move cards")
        self.resize(400, 480)
        self.chapter_id: Optional[int] = None

        title = QLabel(f"Move {count} card{'s' if count != 1 else ''}")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Choose the destination chapter.")
        subtitle.setObjectName("muted")
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(title)
        header.addWidget(subtitle)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        for cls in db.list_classes():
            parent_item = QTreeWidgetItem([cls.name])
            parent_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(parent_item)
            for ch in db.list_chapters(cls.id):
                item = QTreeWidgetItem([ch.name])
                item.setData(0, ROLE_ID, ch.id)
                if ch.id == current_chapter_id:
                    item.setText(0, f"{ch.name}  (current)")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                parent_item.addChild(item)
            parent_item.setExpanded(True)
        self.tree.itemSelectionChanged.connect(self._on_select)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        self.ok = button("Move", "folder-input", "primary", self.accept)
        self.ok.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button("Cancel", slot=self.reject))
        buttons.addWidget(self.ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(self.tree, 1)
        layout.addLayout(buttons)

    def _on_select(self) -> None:
        items = self.tree.selectedItems()
        self.chapter_id = items[0].data(0, ROLE_ID) if items else None
        self.ok.setEnabled(self.chapter_id is not None)

    def _on_double_click(self, *_):
        if self.chapter_id is not None:
            self.accept()


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str, action: Optional[QPushButton] = None):
        super().__init__()
        self.icon = QLabel()
        icons.apply(self.icon, icon_name, "faint", 28)
        self.title = QLabel(title)
        self.title.setObjectName("emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = QLabel(text)
        self.text.setObjectName("muted")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.text)
        if action is not None:
            layout.addSpacing(8)
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)

    def set_text(self, title: str, text: str) -> None:
        self.title.setText(title)
        self.text.setText(text)


class ChapterView(QWidget):
    changed = pyqtSignal()          # cards added / edited / moved / deleted

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.chapter_id: Optional[int] = None
        self._filter = ALL
        # Set by the main window: fills the '⋯' menu (rename / reorder / move / delete).
        self.menu_builder: Optional[Callable[[QMenu], None]] = None

        self.title = EditableTitle()
        self.title.renamed.connect(self._rename)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.search = SearchField("Search cards")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self._apply_filter)
        add = button("Add card", "plus", "primary", self.add_card)
        add.setToolTip("Ctrl+N")

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(self.search)
        header.addSpacing(4)
        header.addWidget(more_button(self._build_menu, "Chapter actions"))
        header.addWidget(add)

        # Status filter chips
        self.chips: dict[str, QPushButton] = {}
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        chips = QHBoxLayout()
        chips.setSpacing(0)
        for key in (ALL, *STATUSES):
            chip = QPushButton()
            chip.setProperty("variant", "tab")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self.chip_group.addButton(chip)
            self.chips[key] = chip
            chips.addWidget(chip)
        self.chips[ALL].setChecked(True)

        self.selection_label = QLabel()
        self.selection_label.setObjectName("muted")
        self.edit_btn = icon_button("pencil", "Edit card (Enter)", self.edit_selected)
        self.move_btn = icon_button("folder-input",
                                    "Move to another chapter… (or drag cards onto the sidebar)",
                                    self.move_selected)
        self.delete_btn = icon_button("trash", "Delete (Del)", self.delete_selected, variant="icon-danger")
        actions = QHBoxLayout()
        actions.addLayout(chips)
        actions.addStretch(1)
        actions.addWidget(self.selection_label)
        actions.addSpacing(6)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.move_btn)
        actions.addWidget(self.delete_btn)

        self.list = CardList()
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.list.itemDoubleClicked.connect(lambda *_: self.edit_selected())

        self.empty = EmptyState("inbox", "No cards yet",
                                "Add your first card — text, formatting and images all work.",
                                button("Add card", "plus", "primary", self.add_card))
        self.no_match = EmptyState("search", "Nothing matches", "Try another search or filter.")
        self.body = QStackedWidget()
        for page in (self.list, self.empty, self.no_match):
            self.body.addWidget(page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addLayout(actions)
        layout.addWidget(self.body, 1)

        _shortcut("Delete", self.list, self.delete_selected)
        _shortcut("Return", self.list, self.edit_selected)
        _shortcut("Ctrl+N", self, self.add_card)
        _shortcut("Ctrl+F", self, self.search.setFocus)
        self._update_buttons()

    # ---- loading -------------------------------------------------------
    def show_chapter(self, chapter_id: int) -> None:
        def load():
            self.chapter_id = chapter_id
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self._filter = ALL
            self.chips[ALL].setChecked(True)
            self.list.clearSelection()
            self.refresh()
        if self.chapter_id is not None and self.chapter_id != chapter_id:
            crossfade(self, load, FAST + 40)
        else:
            load()

    def refresh(self) -> None:
        chapter = self.db.get_chapter(self.chapter_id) if self.chapter_id else None
        if chapter is None:
            return
        cls = self.db.get_class(chapter.class_id)
        cards = self.db.list_cards(chapter.id)
        self.title.setText(chapter.name)
        self.subtitle.setText(f"{cls.name}  ·  {len(cards)} card{'s' if len(cards) != 1 else ''}")

        selected = set(self.selected_ids())
        now = utcnow()
        counts = {key: 0 for key in (ALL, *STATUSES)}
        self.list.clear()
        for card in cards:
            status = card_status(card)
            counts[ALL] += 1
            counts[status] += 1
            item = QListWidgetItem()
            item.setData(ROLE_ID, card.id)
            item.setData(ROLE_TITLE, plain_preview(card.front_html) or "(empty)")
            parts = [STATUS_LABELS[status]]
            if status != UNTESTED:
                parts.append(due_label(card, now))
            back = plain_preview(card.back_html, 80)
            if back:
                parts.append(back)
            item.setData(ROLE_SUBTITLE, "   ·   ".join(parts))
            item.setData(ROLE_STATUS, status)
            self.list.addItem(item)
            item.setSelected(card.id in selected)

        for key, chip in self.chips.items():
            label = "All" if key == ALL else STATUS_LABELS[key]
            chip.setText(f"{label}  {counts[key]}")
        self._apply_filter()

    def _set_filter(self, key: str) -> None:
        if key != self._filter:
            self._filter = key
            crossfade(self.body, self._apply_filter, FAST)

    def _apply_filter(self, *_):
        needle = self.search.text().strip().lower()
        visible = 0
        for i in range(self.list.count()):
            item = self.list.item(i)
            hay = f"{item.data(ROLE_TITLE)} {item.data(ROLE_SUBTITLE)}".lower()
            show = (self._filter == ALL or item.data(ROLE_STATUS) == self._filter) and \
                   (not needle or needle in hay)
            item.setHidden(not show)
            visible += show
        if self.list.count() == 0:
            self.body.setCurrentWidget(self.empty)
        elif visible == 0:
            self.body.setCurrentWidget(self.no_match)
        else:
            self.body.setCurrentWidget(self.list)
        self._update_buttons()

    def selected_ids(self) -> list[int]:
        return [item.data(ROLE_ID) for item in self.list.selectedItems() if not item.isHidden()]

    def _update_buttons(self) -> None:
        n = len(self.selected_ids())
        self.edit_btn.setEnabled(n == 1)
        self.move_btn.setEnabled(n > 0)
        self.delete_btn.setEnabled(n > 0)
        self.selection_label.setText(f"{n} selected" if n else "")

    # ---- actions -------------------------------------------------------
    def _build_menu(self, menu: QMenu) -> None:
        if self.menu_builder is not None and self.chapter_id is not None:
            self.menu_builder(menu)

    def _rename(self, name: str) -> None:
        if self.chapter_id is not None:
            self.db.rename_chapter(self.chapter_id, name)
            self.changed.emit()

    def add_card(self) -> None:
        chapter = self.db.get_chapter(self.chapter_id) if self.chapter_id else None
        if chapter is None:
            return
        dialog = CardEditorDialog(self.db.data_dir, self, adding=True, chapter_name=chapter.name)
        dialog.card_saved.connect(lambda f, b: self.db.add_card(chapter.id, f, b))
        dialog.card_saved.connect(lambda *_: self._after_change())
        dialog.exec()

    def edit_selected(self) -> None:
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        card = self.db.get_card(ids[0])
        if card is None:
            return
        dialog = CardEditorDialog(self.db.data_dir, self, card.front_html, card.back_html,
                                  adding=False)
        dialog.card_saved.connect(lambda f, b: self.db.update_card_content(card.id, f, b))
        if dialog.exec():
            self._after_change()

    def move_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        dialog = MoveCardsDialog(self.db, self.chapter_id, len(ids), self)
        if dialog.exec() and dialog.chapter_id is not None:
            self.db.move_cards(ids, dialog.chapter_id)
            self._after_change()

    def delete_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        noun = "this card" if len(ids) == 1 else f"these {len(ids)} cards"
        if confirm(self, "Delete cards", f"Delete {noun}? Their review history is removed too."):
            self.db.delete_cards(ids)
            self._after_change()

    def _after_change(self) -> None:
        crossfade(self.body, self.refresh, FAST)
        self.changed.emit()
