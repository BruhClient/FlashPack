"""Google-Docs-style rich text editing (icon toolbar, pasted images)
and a read-only viewer for showing cards."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QMimeData, QPointF, QSize, Qt, QUrl
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap,
    QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextDocumentFragment,
    QTextFormat, QTextImageFormat, QTextListFormat,
)
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QMenu, QTextBrowser, QTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from .. import media
from . import icons, theme

MAX_IMAGE_WIDTH = 520

# Mid-tone colors stay readable on both light and dark backgrounds.
TEXT_COLORS = [
    ("Default", None), ("Gray", "#8A8A94"), ("Red", "#EF4444"), ("Orange", "#F97316"),
    ("Green", "#22C55E"), ("Blue", "#3B82F6"), ("Purple", "#8B5CF6"),
]
# Translucent highlights keep the text color readable in both themes.
HIGHLIGHTS = [
    ("None", None), ("Yellow", "#FACC15"), ("Green", "#4ADE80"), ("Blue", "#60A5FA"),
    ("Pink", "#F472B6"), ("Orange", "#FB923C"),
]
HIGHLIGHT_ALPHA = 105
HEADINGS = [("Normal text", 0), ("Heading 1", 1), ("Heading 2", 2), ("Heading 3", 3)]
_HEADING_SIZE_ADJUST = {0: 0, 1: 3, 2: 2, 3: 1}
_IMAGE_RESOURCE = QTextDocument.ResourceType.ImageResource.value


def plain_preview(html: str, limit: int = 140) -> str:
    """Single-line plain text for list rows."""
    text = QTextDocumentFragment.fromHtml(html or "").toPlainText()
    text = re.sub(r"\s+", " ", text.replace("￼", " ")).strip()
    if not text and "<img" in (html or ""):
        return "[image]"
    return text[:limit] + ("…" if len(text) > limit else "")


def _load_media_image(data_dir: Path, rtype: int, url: QUrl) -> Optional[QImage]:
    if rtype != _IMAGE_RESOURCE:
        return None
    path = media.resolve(data_dir, url.toString())
    if path and path.is_file():
        image = QImage(str(path))
        return image if not image.isNull() else None
    return None


def _swatch(color: Optional[str], alpha: int = 255) -> QIcon:
    size, ratio = 16, 2
    pix = QPixmap(size * ratio, size * ratio)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(ratio, ratio)
    center = QPointF(size / 2, size / 2)
    if color is None:
        p.setPen(QPen(QColor("#8A8A94"), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(center, 6, 6)
        p.drawLine(QPointF(4, 12), QPointF(12, 4))
    else:
        fill = QColor(color)
        fill.setAlpha(alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawEllipse(center, 6.5, 6.5)
    p.end()
    pix.setDevicePixelRatio(ratio)
    return QIcon(pix)


class RichTextEdit(QTextEdit):
    """QTextEdit that stores pasted/dropped images in the media folder."""

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.setObjectName("cardEdit")
        self.setAcceptRichText(True)
        self.document().setBaseUrl(QUrl.fromLocalFile(str(self.data_dir) + "/"))
        self.document().setDocumentMargin(12)
        self.setFont(theme.serif_font(12))   # same face the card is studied in

    def loadResource(self, rtype, name):
        image = _load_media_image(self.data_dir, rtype, name)
        return image if image is not None else super().loadResource(rtype, name)

    @staticmethod
    def _image_files(source: QMimeData) -> list[Path]:
        if not source.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in source.urls()
                if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in media.IMAGE_EXTS]

    @staticmethod
    def _is_bare_image(source: QMimeData) -> bool:
        # Office apps put a picture of the selection next to the text; prefer the text.
        return source.hasImage() and not source.text().strip()

    def canInsertFromMimeData(self, source):
        return (self._is_bare_image(source) or bool(self._image_files(source))
                or super().canInsertFromMimeData(source))

    def insertFromMimeData(self, source):
        if self._is_bare_image(source):
            image = QImage(source.imageData())
            if not image.isNull():
                self.insert_image(image)
                return
        files = self._image_files(source)
        if files:
            for path in files:
                self.insert_image_file(path)
            return
        super().insertFromMimeData(source)

    def insert_image(self, image: QImage) -> None:
        name = media.new_media_name(".png")
        image.save(str(media.media_dir(self.data_dir) / name), "PNG")
        self._insert_reference(media.reference(name), image.width())

    def insert_image_file(self, path: Path) -> None:
        image = QImage(str(path))
        if image.isNull():
            return
        self._insert_reference(media.import_image_file(self.data_dir, path), image.width())

    def _insert_reference(self, ref: str, width: int) -> None:
        fmt = QTextImageFormat()
        fmt.setName(ref)
        if width > MAX_IMAGE_WIDTH:
            fmt.setWidth(MAX_IMAGE_WIDTH)
        cursor = self.textCursor()
        cursor.insertImage(fmt)
        self.setTextCursor(cursor)


class RichTextEditor(QWidget):
    """Icon formatting toolbar + editor."""

    def __init__(self, data_dir: Path, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.edit = RichTextEdit(data_dir)
        self.edit.setPlaceholderText(placeholder)

        bar = QFrame()
        bar.setObjectName("formatBar")
        self._row = QHBoxLayout(bar)
        self._row.setContentsMargins(6, 4, 6, 4)
        self._row.setSpacing(2)

        self.heading = QComboBox()
        for label, _level in HEADINGS:
            self.heading.addItem(label)
        self.heading.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.heading.setToolTip("Text style")
        self.heading.activated.connect(lambda i: self._set_heading(HEADINGS[i][1]))
        self._row.addWidget(self.heading)
        self._separator()

        self.act_bold = self._action("bold", "Bold (Ctrl+B)", QKeySequence.StandardKey.Bold,
                                     lambda on: self._merge(weight=on), checkable=True)
        self.act_italic = self._action("italic", "Italic (Ctrl+I)", QKeySequence.StandardKey.Italic,
                                       lambda on: self._merge(italic=on), checkable=True)
        self.act_underline = self._action("underline", "Underline (Ctrl+U)",
                                          QKeySequence.StandardKey.Underline,
                                          lambda on: self._merge(underline=on), checkable=True)
        self.act_strike = self._action("strikethrough", "Strikethrough (Ctrl+Shift+X)",
                                       QKeySequence("Ctrl+Shift+X"),
                                       lambda on: self._merge(strike=on), checkable=True)
        for act in (self.act_bold, self.act_italic, self.act_underline, self.act_strike):
            self._row.addWidget(self._button(act))
        self._separator()

        self._row.addWidget(self._menu_button("baseline", "Text color", [
            (name, _swatch(c), lambda _=False, c=c: self._set_color(c)) for name, c in TEXT_COLORS]))
        self._row.addWidget(self._menu_button("highlighter", "Highlight", [
            (name, _swatch(c, HIGHLIGHT_ALPHA), lambda _=False, c=c: self._set_highlight(c))
            for name, c in HIGHLIGHTS]))
        self._separator()

        self.act_bullets = self._action(
            "list", "Bulleted list (Ctrl+Shift+8)", QKeySequence("Ctrl+Shift+8"),
            lambda _: self._toggle_list(QTextListFormat.Style.ListDisc), checkable=True)
        self.act_numbers = self._action(
            "list-ordered", "Numbered list (Ctrl+Shift+7)", QKeySequence("Ctrl+Shift+7"),
            lambda _: self._toggle_list(QTextListFormat.Style.ListDecimal), checkable=True)
        self._row.addWidget(self._button(self.act_bullets))
        self._row.addWidget(self._button(self.act_numbers))
        self._separator()

        act_image = self._action("image", "Insert image (you can also paste one)", None,
                                 lambda _: self._pick_image())
        act_clear = self._action("eraser", "Clear formatting (Ctrl+\\)", QKeySequence("Ctrl+\\"),
                                 lambda _: self._clear_formatting())
        self._row.addWidget(self._button(act_image))
        self._row.addWidget(self._button(act_clear))
        self._row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(bar)
        layout.addWidget(self.edit, 1)

        self.edit.currentCharFormatChanged.connect(self._sync)
        self.edit.cursorPositionChanged.connect(self._sync)
        self._sync()

    # ---- public API ----------------------------------------------------
    def html(self) -> str:
        return "" if self.is_empty() else self.edit.toHtml()

    def set_html(self, html: str) -> None:
        self.edit.setHtml(without_body_font(html))

    def is_empty(self) -> bool:
        return not self.edit.toPlainText().strip() and "<img" not in self.edit.toHtml()

    def clear(self) -> None:
        self.edit.clear()

    # ---- toolbar plumbing ----------------------------------------------
    def _separator(self) -> None:
        line = QFrame()
        line.setObjectName("toolSeparator")
        line.setFixedSize(1, 18)
        self._row.addSpacing(4)
        self._row.addWidget(line)
        self._row.addSpacing(4)

    def _action(self, icon_name, tip, shortcut, slot, checkable=False) -> QAction:
        act = QAction(tip.split(" (")[0], self)
        act.setToolTip(tip)
        act.setCheckable(checkable)
        icons.apply(act, icon_name)
        if shortcut is not None:
            act.setShortcut(shortcut)
            act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.edit.addAction(act)
        act.triggered.connect(slot)
        return act

    def _button(self, action: QAction) -> QToolButton:
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _menu_button(self, icon_name, tip, entries) -> QToolButton:
        btn = QToolButton()
        btn.setToolTip(tip)
        icons.apply(btn, icon_name)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(btn)
        for name, icon, slot in entries:
            menu.addAction(icon, name).triggered.connect(slot)
        btn.setMenu(menu)
        return btn

    def _sync(self, *_):
        fmt = self.edit.currentCharFormat()
        for act, on in ((self.act_bold, fmt.fontWeight() >= QFont.Weight.DemiBold.value),
                        (self.act_italic, fmt.fontItalic()),
                        (self.act_underline, fmt.fontUnderline()),
                        (self.act_strike, fmt.fontStrikeOut())):
            act.blockSignals(True)
            act.setChecked(on)
            act.blockSignals(False)

        cursor = self.edit.textCursor()
        lst = cursor.currentList()
        style = lst.format().style() if lst else None
        for act, s in ((self.act_bullets, QTextListFormat.Style.ListDisc),
                       (self.act_numbers, QTextListFormat.Style.ListDecimal)):
            act.blockSignals(True)
            act.setChecked(style == s)
            act.blockSignals(False)

        level = cursor.blockFormat().headingLevel()
        index = next((i for i, (_, lv) in enumerate(HEADINGS) if lv == level), 0)
        self.heading.blockSignals(True)
        self.heading.setCurrentIndex(index)
        self.heading.blockSignals(False)

    # ---- formatting operations -----------------------------------------
    def _merge(self, weight=None, italic=None, underline=None, strike=None):
        fmt = QTextCharFormat()
        if weight is not None:
            fmt.setFontWeight(QFont.Weight.Bold.value if weight else QFont.Weight.Normal.value)
        if italic is not None:
            fmt.setFontItalic(italic)
        if underline is not None:
            fmt.setFontUnderline(underline)
        if strike is not None:
            fmt.setFontStrikeOut(strike)
        self.edit.mergeCurrentCharFormat(fmt)
        self.edit.setFocus()

    def _set_color(self, color: Optional[str]) -> None:
        if color is None:
            self._clear_char_property(QTextCharFormat.clearForeground)
        else:
            fmt = QTextCharFormat()
            fmt.setForeground(QBrush(QColor(color)))
            self.edit.mergeCurrentCharFormat(fmt)
        self.edit.setFocus()

    def _set_highlight(self, color: Optional[str]) -> None:
        if color is None:
            self._clear_char_property(QTextCharFormat.clearBackground)
        else:
            fill = QColor(color)
            fill.setAlpha(HIGHLIGHT_ALPHA)
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(fill))
            self.edit.mergeCurrentCharFormat(fmt)
        self.edit.setFocus()

    def _clear_char_property(self, clear: Callable[[QTextCharFormat], None]) -> None:
        """Remove one property (e.g. text color) from the selection, keeping the rest."""
        cursor = self.edit.textCursor()
        if not cursor.hasSelection():
            fmt = self.edit.currentCharFormat()
            clear(fmt)
            self.edit.setCurrentCharFormat(fmt)
            return
        doc = self.edit.document()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        runs = []
        for block in self._selected_blocks(cursor):
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                lo = max(frag.position(), start)
                hi = min(frag.position() + frag.length(), end)
                if lo < hi:
                    runs.append((lo, hi, frag.charFormat()))
                it += 1
        cursor.beginEditBlock()
        for lo, hi, fmt in runs:
            clear(fmt)
            run = QTextCursor(doc)
            run.setPosition(lo)
            run.setPosition(hi, QTextCursor.MoveMode.KeepAnchor)
            run.setCharFormat(fmt)
        cursor.endEditBlock()

    def _selected_blocks(self, cursor: QTextCursor) -> list:
        doc = self.edit.document()
        block = doc.findBlock(cursor.selectionStart())
        end = cursor.selectionEnd()
        blocks = []
        while block.isValid() and block.position() <= end:
            blocks.append(block)
            block = block.next()
        return blocks

    def _set_heading(self, level: int) -> None:
        cursor = self.edit.textCursor()
        char_fmt = QTextCharFormat()
        char_fmt.setFontWeight(QFont.Weight.Bold.value if level else QFont.Weight.Normal.value)
        char_fmt.setProperty(QTextFormat.Property.FontSizeAdjustment.value,
                             _HEADING_SIZE_ADJUST[level])
        cursor.beginEditBlock()
        for block in self._selected_blocks(cursor):
            c = QTextCursor(block)
            block_fmt = block.blockFormat()
            block_fmt.setHeadingLevel(level)
            c.setBlockFormat(block_fmt)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            c.mergeCharFormat(char_fmt)
        cursor.endEditBlock()
        self.edit.mergeCurrentCharFormat(char_fmt)
        self.edit.setFocus()

    def _toggle_list(self, style: QTextListFormat.Style) -> None:
        cursor = self.edit.textCursor()
        current = cursor.currentList()
        cursor.beginEditBlock()
        if current is not None and current.format().style() == style:
            for block in self._selected_blocks(cursor):
                lst = block.textList()
                if lst is not None:
                    lst.remove(block)
                    fmt = block.blockFormat()
                    fmt.setIndent(0)
                    QTextCursor(block).setBlockFormat(fmt)
        elif current is not None:
            fmt = current.format()
            fmt.setStyle(style)
            current.setFormat(fmt)
        else:
            fmt = QTextListFormat()
            fmt.setStyle(style)
            cursor.createList(fmt)
        cursor.endEditBlock()
        self._sync()
        self.edit.setFocus()

    def _clear_formatting(self) -> None:
        cursor = self.edit.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            cursor.setCharFormat(QTextCharFormat())
        for block in self._selected_blocks(cursor):
            QTextCursor(block).setBlockFormat(QTextBlockFormat())
        cursor.endEditBlock()
        self.edit.setCurrentCharFormat(QTextCharFormat())
        self._sync()
        self.edit.setFocus()

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image", "",
            "Images (" + " ".join(f"*{e}" for e in media.IMAGE_EXTS) + ")")
        if path:
            self.edit.insert_image_file(Path(path))
            self.edit.setFocus()


_BODY_STYLE = re.compile(r'(<body[^>]*?style=")([^"]*)(")', re.IGNORECASE)
_FONT_DECL = re.compile(r'\s*font-(?:family|size)\s*:[^;"]*;?', re.IGNORECASE)


def without_body_font(html: str) -> str:
    """Drop the font family/size Qt bakes into <body>, so the widget's own font applies
    (headings keep their relative sizes, inline formatting is untouched)."""
    return _BODY_STYLE.sub(lambda m: m.group(1) + _FONT_DECL.sub("", m.group(2)) + m.group(3),
                           html or "")


class CardViewer(QTextBrowser):
    """Read-only rendering of a card side, with media images, in a larger reading serif."""

    READING_POINT_SIZE = 16

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.setObjectName("cardView")
        self.setOpenExternalLinks(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.document().setBaseUrl(QUrl.fromLocalFile(str(self.data_dir) + "/"))
        self.document().setDocumentMargin(16)
        self.setFont(theme.serif_font(self.READING_POINT_SIZE))

    def loadResource(self, rtype, name):
        image = _load_media_image(self.data_dir, rtype, name)
        return image if image is not None else super().loadResource(rtype, name)

    def show_html(self, html: str) -> None:
        self.setHtml(without_body_font(html))

    def sizeHint(self) -> QSize:
        return QSize(600, 160)
