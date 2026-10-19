"""Left navigation: Classes -> Chapters with inline rename, row actions and card drop targets."""
from __future__ import annotations

import json
from typing import Callable, Optional

from PyQt6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QMenu, QStyledItemDelegate, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..db import Database
from . import icons, theme
from .chapter_view import CARD_IDS_MIME
from .dialogs import add_menu_action, ask_text, confirm, icon_button

KIND_ROLE = Qt.ItemDataRole.UserRole
ID_ROLE = Qt.ItemDataRole.UserRole + 1
COUNT_ROLE = Qt.ItemDataRole.UserRole + 2
NAME_ROLE = Qt.ItemDataRole.UserRole + 3
CLASS, CHAPTER = "class", "chapter"
MORE_W = 28


class _TreeDelegate(QStyledItemDelegate):
    """Default cell painting plus a right-aligned card count, or a '⋯' button on hover."""

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        tree: SidebarTree = self.parent()
        if tree.isEnabled() and index == tree.hover_index:
            pix = icons.pixmap("more", theme.color("muted"), 16)
            rect = tree.more_rect(index)
            painter.drawPixmap(rect.center().x() - 8, rect.center().y() - 8, pix)
            return
        count = index.data(COUNT_ROLE)
        if count is not None:
            painter.save()
            painter.setPen(theme.color("faint"))
            painter.drawText(option.rect.adjusted(0, 0, -10, 0),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(count))
            painter.restore()


class SidebarTree(QTreeWidget):
    """Tree with full-row highlights, a hover '⋯' button, inline rename and card drops."""

    cards_dropped = pyqtSignal(list, int)
    more_requested = pyqtSignal(QTreeWidgetItem, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navTree")
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setAnimated(True)
        self.setIconSize(QSize(16, 16))
        self.setExpandsOnDoubleClick(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setMouseTracking(True)
        self.setItemDelegate(_TreeDelegate(self))
        self.drop_index = None
        self.hover_index = QModelIndex()

    def more_rect(self, index) -> QRect:
        r = self.visualRect(index)
        return QRect(r.right() - MORE_W - 2, r.top(), MORE_W, r.height())

    def reset_hover(self) -> None:
        self.hover_index = QModelIndex()

    def drawRow(self, painter: QPainter, option, index):
        # One rounded highlight across the whole row (indent + arrow + text), painted
        # before Qt draws the branch arrow, icon and text on top of it.
        selected = self.selectionModel().isSelected(index)
        hovered = self.isEnabled() and index == self.hover_index
        is_drop = self.drop_index is not None and index == self.drop_index
        if selected or hovered or is_drop:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if is_drop:
                painter.setPen(QPen(theme.color("accent"), 1.2))
                painter.setBrush(theme.color("accent_soft"))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(theme.color("selection" if selected else "hover"))
            painter.drawRoundedRect(QRectF(option.rect).adjusted(1, 1, -1, -1), 8, 8)
            painter.restore()
        super().drawRow(painter, option, index)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        index = self.indexAt(event.position().toPoint())
        if index != self.hover_index:
            self.hover_index = index
            self.viewport().update()

    def leaveEvent(self, event):
        self.reset_hover()
        self.viewport().update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if event.button() == Qt.MouseButton.LeftButton and index.isValid() \
                and self.more_rect(index).contains(pos):
            anchor = self.viewport().mapToGlobal(self.more_rect(index).bottomLeft())
            self.more_requested.emit(self.itemFromIndex(index), anchor)
            return
        super().mousePressEvent(event)

    # ---- drag & drop of cards onto chapters ------------------------------
    def _chapter_at(self, pos: QPoint) -> Optional[QTreeWidgetItem]:
        item = self.itemAt(pos)
        return item if item is not None and item.data(0, KIND_ROLE) == CHAPTER else None

    def _set_drop_item(self, item: Optional[QTreeWidgetItem]) -> None:
        index = self.indexFromItem(item) if item is not None else None
        if index != self.drop_index:
            self.drop_index = index
            self.viewport().update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CARD_IDS_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        item = self._chapter_at(event.position().toPoint())
        if event.mimeData().hasFormat(CARD_IDS_MIME) and item is not None:
            self._set_drop_item(item)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            self._set_drop_item(None)
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_item(None)
        event.accept()

    def dropEvent(self, event):
        item = self._chapter_at(event.position().toPoint())
        self._set_drop_item(None)
        if item is None or not event.mimeData().hasFormat(CARD_IDS_MIME):
            event.ignore()
            return
        ids = json.loads(bytes(event.mimeData().data(CARD_IDS_MIME)).decode())
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.cards_dropped.emit([int(i) for i in ids], item.data(0, ID_ROLE))


class Sidebar(QWidget):
    class_selected = pyqtSignal(int)
    chapter_selected = pyqtSignal(int)
    nothing_selected = pyqtSignal()
    cards_dropped = pyqtSignal(list, int)
    structure_changed = pyqtSignal()
    theme_toggle_requested = pyqtSignal()
    import_requested = pyqtSignal()
    export_requested = pyqtSignal()
    open_folder_requested = pyqtSignal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        brand = QLabel("Flashcards")
        brand.setObjectName("brand")
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 0, 0)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)

        section = QLabel("Classes")
        section.setObjectName("sectionLabel")
        section_row = QHBoxLayout()
        section_row.setContentsMargins(6, 0, 0, 0)
        section_row.addWidget(section)
        section_row.addStretch(1)
        section_row.addWidget(icon_button("plus", "New class (Ctrl+Shift+N)", self.new_class))

        self.tree = SidebarTree()
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.itemChanged.connect(self._on_item_edited)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.more_requested.connect(self._show_item_menu)
        self.tree.cards_dropped.connect(self.cards_dropped)

        self.theme_btn = icon_button("moon", "Dark mode (Ctrl+Shift+L)", self.theme_toggle_requested.emit)
        footer = QHBoxLayout()
        footer.setSpacing(2)
        footer.addWidget(self.theme_btn)
        footer.addStretch(1)
        footer.addWidget(icon_button("download", "Import data… (Ctrl+I)", self.import_requested.emit))
        footer.addWidget(icon_button("share", "Export data… (Ctrl+E)", self.export_requested.emit))
        footer.addWidget(icon_button("folder-open", "Open data folder", self.open_folder_requested.emit))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 22, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(brand_row)
        layout.addSpacing(14)
        layout.addLayout(section_row)
        layout.addWidget(self.tree, 1)
        layout.addLayout(footer)

        manager = theme.manager()
        if manager is not None:
            manager.changed.connect(self._on_theme_changed)
        self._update_theme_button()

    # ---- theme ---------------------------------------------------------
    def _update_theme_button(self) -> None:
        dark = theme.is_dark()
        icons.apply(self.theme_btn, "sun" if dark else "moon")
        self.theme_btn.setToolTip(("Light mode" if dark else "Dark mode") + " (Ctrl+Shift+L)")

    def _on_theme_changed(self, _name: str) -> None:
        self._update_theme_button()
        self.refresh()

    # ---- tree contents -------------------------------------------------
    def current(self) -> tuple[Optional[str], Optional[int]]:
        items = self.tree.selectedItems()
        if not items:
            return None, None
        return items[0].data(0, KIND_ROLE), items[0].data(0, ID_ROLE)

    def _make_item(self, kind: str, ident: int, name: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        if kind == CLASS:
            font = self.tree.font()
            font.setWeight(QFont.Weight.DemiBold)
            item.setFont(0, font)
        item.setData(0, KIND_ROLE, kind)
        item.setData(0, ID_ROLE, ident)
        item.setData(0, NAME_ROLE, name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        return item

    def refresh(self) -> None:
        """Rebuild the tree, keeping selection and expanded classes."""
        kind, ident = self.current()
        expanded = {self.tree.topLevelItem(i).data(0, ID_ROLE)
                    for i in range(self.tree.topLevelItemCount())
                    if self.tree.topLevelItem(i).isExpanded()}
        first_build = self.tree.topLevelItemCount() == 0

        self.tree.blockSignals(True)
        self.tree.setAnimated(False)
        self.tree.reset_hover()
        self.tree.clear()
        for cls in self.db.list_classes():
            cls_item = self._make_item(CLASS, cls.id, cls.name)
            self.tree.addTopLevelItem(cls_item)
            for ch in self.db.list_chapters(cls.id):
                n = self.db.count_cards(ch.id)
                ch_item = self._make_item(CHAPTER, ch.id, ch.name)
                ch_item.setData(0, COUNT_ROLE, n)
                ch_item.setToolTip(0, f"{n} card{'s' if n != 1 else ''}")
                cls_item.addChild(ch_item)
            cls_item.setExpanded(first_build or cls.id in expanded)
        self.tree.setAnimated(True)
        self.tree.blockSignals(False)

        if kind and not self._select(kind, ident, emit=False):
            self.nothing_selected.emit()

    def _find(self, kind: str, ident: int) -> Optional[QTreeWidgetItem]:
        for i in range(self.tree.topLevelItemCount()):
            cls_item = self.tree.topLevelItem(i)
            if kind == CLASS and cls_item.data(0, ID_ROLE) == ident:
                return cls_item
            for j in range(cls_item.childCount()):
                child = cls_item.child(j)
                if kind == CHAPTER and child.data(0, ID_ROLE) == ident:
                    return child
        return None

    def _select(self, kind: str, ident: int, emit: bool = True) -> bool:
        item = self._find(kind, ident)
        if item is None:
            return False
        if item.parent() is not None:
            item.parent().setExpanded(True)
        self.tree.blockSignals(not emit)
        self.tree.setCurrentItem(item)
        item.setSelected(True)
        self.tree.blockSignals(False)
        return True

    def select_class(self, class_id: int) -> None:
        self._select(CLASS, class_id)

    def select_chapter(self, chapter_id: int) -> None:
        self._select(CHAPTER, chapter_id)

    def select_first(self) -> None:
        if self.tree.topLevelItemCount():
            self.select_class(self.tree.topLevelItem(0).data(0, ID_ROLE))
        else:
            self.nothing_selected.emit()

    def _on_selection(self) -> None:
        kind, ident = self.current()
        if kind == CLASS:
            self.class_selected.emit(ident)
        elif kind == CHAPTER:
            self.chapter_selected.emit(ident)
        else:
            self.nothing_selected.emit()

    # ---- create ----------------------------------------------------------
    def new_class(self) -> None:
        name = ask_text(self, "New class", "Give the class a name, e.g. “Biology 101”.",
                        ok_text="Create", placeholder="Class name")
        if name:
            class_id = self.db.add_class(name)
            self.refresh()
            self.select_class(class_id)
            self.structure_changed.emit()

    def new_chapter(self, class_id: int) -> None:
        name = ask_text(self, "New chapter", "Chapters group the cards inside a class.",
                        ok_text="Create", placeholder="Chapter name")
        if name:
            chapter_id = self.db.add_chapter(class_id, name)
            self.refresh()
            self.select_chapter(chapter_id)
            self.structure_changed.emit()

    # ---- rename (inline in the tree) ---------------------------------------
    def start_rename(self, kind: str, ident: int) -> None:
        item = self._find(kind, ident)
        if item is not None:
            self.tree.scrollToItem(item)
            self.tree.editItem(item, 0)

    def _on_item_edited(self, item: QTreeWidgetItem, _column: int) -> None:
        kind, ident = item.data(0, KIND_ROLE), item.data(0, ID_ROLE)
        if kind is None:
            return
        old = item.data(0, NAME_ROLE)
        name = item.text(0).strip()
        self.tree.blockSignals(True)
        item.setText(0, name or old)
        if name and name != old:
            item.setData(0, NAME_ROLE, name)
        self.tree.blockSignals(False)
        if not name or name == old:
            return
        if kind == CLASS:
            self.db.rename_class(ident, name)
        else:
            self.db.rename_chapter(ident, name)
        self.structure_changed.emit()

    # ---- delete / reorder / move -----------------------------------------
    def delete_class(self, class_id: int) -> None:
        self._delete(CLASS, class_id)

    def delete_chapter(self, chapter_id: int) -> None:
        self._delete(CHAPTER, chapter_id)

    def _delete(self, kind: str, ident: int) -> None:
        item = self._find(kind, ident)
        if item is None:
            return
        if kind == CLASS:
            n_ch = item.childCount()
            detail = (f"This deletes {n_ch} chapter{'s' if n_ch != 1 else ''} "
                      "and all of their cards.")
        else:
            n = self.db.count_cards(ident)
            detail = f"This deletes {n} card{'s' if n != 1 else ''}."
        if not confirm(self, f"Delete “{item.text(0)}”?", detail):
            return
        parent_class = item.parent().data(0, ID_ROLE) if item.parent() else None
        if kind == CLASS:
            self.db.delete_class(ident)
        else:
            self.db.delete_chapter(ident)
        self.tree.clearSelection()
        self.refresh()
        self.structure_changed.emit()
        if parent_class is not None:
            self.select_class(parent_class)
        else:
            self.select_first()

    def _move_chapter(self, chapter_id: int, delta: int) -> None:
        self.db.move_chapter(chapter_id, delta)
        self.refresh()
        self.structure_changed.emit()

    def _move_chapter_to_class(self, chapter_id: int, class_id: int) -> None:
        self.db.move_chapter_to_class(chapter_id, class_id)
        self.refresh()
        self.select_chapter(chapter_id)
        self.structure_changed.emit()

    # ---- menus (shared with the class / chapter pages) -------------------
    def build_class_menu(self, menu: QMenu, class_id: int, on_rename: Callable[[], None]) -> None:
        add_menu_action(menu, "Rename class", "pencil", on_rename)
        add_menu_action(menu, "New chapter", "plus", lambda: self.new_chapter(class_id))
        menu.addSeparator()
        add_menu_action(menu, "Delete class", "trash", lambda: self.delete_class(class_id), "danger")

    def build_chapter_menu(self, menu: QMenu, chapter_id: int,
                           on_rename: Callable[[], None]) -> None:
        chapter = self.db.get_chapter(chapter_id)
        if chapter is None:
            return
        siblings = [c.id for c in self.db.list_chapters(chapter.class_id)]
        position = siblings.index(chapter_id)
        add_menu_action(menu, "Rename chapter", "pencil", on_rename)
        up = add_menu_action(menu, "Move up", "arrow-up", lambda: self._move_chapter(chapter_id, -1))
        down = add_menu_action(menu, "Move down", "arrow-down",
                               lambda: self._move_chapter(chapter_id, 1))
        up.setEnabled(position > 0)
        down.setEnabled(position < len(siblings) - 1)
        others = [c for c in self.db.list_classes() if c.id != chapter.class_id]
        move_menu = menu.addMenu(icons.icon("arrow-right-left"), "Move to class")
        move_menu.setEnabled(bool(others))
        for cls in others:
            add_menu_action(move_menu, cls.name, "book",
                            lambda cid=cls.id: self._move_chapter_to_class(chapter_id, cid))
        menu.addSeparator()
        add_menu_action(menu, "Delete chapter", "trash",
                        lambda: self.delete_chapter(chapter_id), "danger")

    def _show_item_menu(self, item: QTreeWidgetItem, global_pos: QPoint) -> None:
        kind, ident = item.data(0, KIND_ROLE), item.data(0, ID_ROLE)
        menu = QMenu(self)

        def rename() -> None:
            self.start_rename(kind, ident)

        if kind == CLASS:
            self.build_class_menu(menu, ident, rename)
        else:
            self.build_chapter_menu(menu, ident, rename)
        menu.exec(global_pos)

    def _context_menu(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        global_pos = self.tree.viewport().mapToGlobal(pos)
        if item is not None:
            self._show_item_menu(item, global_pos)
            return
        menu = QMenu(self)
        add_menu_action(menu, "New class", "plus", self.new_class)
        menu.exec(global_pos)
