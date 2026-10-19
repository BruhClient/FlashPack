"""Themed dialogs that fade in: text prompt, confirm, alert and the import-mode chooser."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QAbstractAnimation, QEvent, QPoint, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from . import icons, theme
from .animations import FAST

def hairline(soft: bool = False) -> QFrame:
    """1px horizontal rule; sections are separated by these instead of boxed cards."""
    line = QFrame()
    line.setObjectName("ruleSoft" if soft else "rule")
    line.setFixedHeight(1)
    return line


def icon_button(name: str, tooltip: str, slot=None, size: int = 16,
                variant: str = "icon") -> QPushButton:
    """Square, borderless button that shows only an icon."""
    btn = QPushButton()
    btn.setProperty("variant", variant)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    icons.apply(btn, name, "danger" if variant == "icon-danger" else "icon", size)
    if slot is not None:
        btn.clicked.connect(lambda _checked=False: slot())
    return btn


def button(text: str, icon_name: Optional[str] = None, variant: Optional[str] = None,
           slot=None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        btn.setProperty("variant", variant)
    if icon_name:
        color = "on_accent" if variant in ("primary", "danger-solid") else "icon"
        icons.apply(btn, icon_name, color, 16)
    if slot is not None:
        btn.clicked.connect(lambda _checked=False: slot())
    return btn


def add_menu_action(menu: QMenu, text: str, icon_name: str, slot, color_key: str = "icon"):
    action = menu.addAction(icons.icon(icon_name, color_key), text)
    action.triggered.connect(lambda _checked=False: slot())
    return action


def more_button(build_menu: Callable[[QMenu], None], tooltip: str = "More actions") -> QPushButton:
    """'⋯' icon button that opens a menu built on demand by `build_menu(menu)`."""
    btn = icon_button("more", tooltip)

    def show_menu() -> None:
        menu = QMenu(btn)
        build_menu(menu)
        menu.exec(btn.mapToGlobal(QPoint(0, btn.height() + 4)))

    btn.clicked.connect(lambda _checked=False: show_menu())
    return btn


class SearchField(QLineEdit):
    """Line edit with a search icon painted inside it, centred on the text line.

    (QLineEdit's built-in leading-action icon ignores stylesheet padding and sits low.)"""

    ICON = 16
    ICON_X = 11          # 1px border + 10px stylesheet padding

    def __init__(self, placeholder: str = "Search", parent=None):
        super().__init__(parent)
        self.setObjectName("search")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setTextMargins(self.ICON + 8, 0, 0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = "muted" if self.hasFocus() else "faint"
        painter.drawPixmap(self.ICON_X, (self.height() - self.ICON) // 2,
                           icons.pixmap("search", theme.color(color), self.ICON))


class EditableTitle(QWidget):
    """Page title that turns into a text field when clicked. Enter saves, Esc cancels."""

    renamed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._editing = False

        self.label = QLabel()
        self.label.setObjectName("pageTitle")
        self.label.setCursor(Qt.CursorShape.IBeamCursor)
        self.label.setToolTip("Click to rename")
        self.label.installEventFilter(self)

        self.field = QLineEdit()
        self.field.setObjectName("titleEdit")
        self.field.hide()
        self.field.installEventFilter(self)
        self.field.editingFinished.connect(lambda: self._finish(save=True))

        self.pencil = icon_button("pencil", "Rename", self.start_edit, size=15)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.label)
        layout.addWidget(self.field)
        layout.addWidget(self.pencil)
        layout.addStretch(1)

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = text
        if not self._editing:
            self.label.setText(text)

    def start_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self.field.setText(self._text)
        self.field.setMinimumWidth(max(280, self.label.sizeHint().width() + 48))
        self.label.hide()
        self.pencil.hide()
        self.field.show()
        self.field.setFocus()
        self.field.selectAll()

    def _finish(self, save: bool) -> None:
        if not self._editing:
            return
        self._editing = False
        name = self.field.text().strip()
        self.field.hide()
        self.label.show()
        self.pencil.show()
        if save and name and name != self._text:
            self._text = name
            self.label.setText(name)
            self.renamed.emit(name)

    def eventFilter(self, obj, event):
        if obj is self.label and event.type() == QEvent.Type.MouseButtonPress \
                and event.button() == Qt.MouseButton.LeftButton:
            self.start_edit()
            return True
        if obj is self.field and event.type() == QEvent.Type.KeyPress \
                and event.key() == Qt.Key.Key_Escape:
            self._finish(save=False)
            return True
        return super().eventFilter(obj, event)


class FadeDialog(QDialog):
    """Dialog that fades in the first time it is shown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._faded = False

    def showEvent(self, event):
        super().showEvent(event)
        if self._faded:
            return
        self._faded = True
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(FAST + 40)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


class _MessageDialog(FadeDialog):
    """Title / message / extra content, then right-aligned buttons."""

    def __init__(self, parent, title: str, message: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        heading = QLabel(title)
        heading.setObjectName("dialogTitle")
        text = QLabel(message)
        text.setObjectName("muted")
        text.setWordWrap(True)
        text.setVisible(bool(message))

        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self.body.addWidget(heading)
        self.body.addWidget(text)

        self.buttons = QHBoxLayout()
        self.buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(22)
        layout.addLayout(self.body)
        layout.addLayout(self.buttons)

    def add_button(self, btn: QPushButton) -> QPushButton:
        btn.setAutoDefault(False)
        self.buttons.addWidget(btn)
        return btn


def ask_text(parent, title: str, label: str = "", text: str = "",
             ok_text: str = "Save", placeholder: str = "") -> Optional[str]:
    dialog = _MessageDialog(parent, title, label)
    field = QLineEdit(text)
    field.setPlaceholderText(placeholder)
    field.selectAll()
    dialog.body.addSpacing(6)
    dialog.body.addWidget(field)
    dialog.add_button(button("Cancel", slot=dialog.reject))
    ok = dialog.add_button(button(ok_text, "check", "primary", dialog.accept))
    ok.setDefault(True)
    ok.setEnabled(bool(text.strip()))
    field.textChanged.connect(lambda t: ok.setEnabled(bool(t.strip())))
    field.returnPressed.connect(lambda: ok.isEnabled() and dialog.accept())
    field.setFocus()
    if dialog.exec() and field.text().strip():
        return field.text().strip()
    return None


def confirm(parent, title: str, message: str, ok_text: str = "Delete", danger: bool = True) -> bool:
    dialog = _MessageDialog(parent, title, message)
    dialog.add_button(button("Cancel", slot=dialog.reject)).setFocus()
    dialog.add_button(button(ok_text, None, "danger-solid" if danger else "primary", dialog.accept))
    return bool(dialog.exec())


def alert(parent, title: str, message: str) -> None:
    dialog = _MessageDialog(parent, title, message)
    dialog.add_button(button("OK", None, "primary", dialog.accept)).setDefault(True)
    dialog.exec()


class OptionCard(QFrame):
    """Large clickable choice: title and description."""

    clicked = pyqtSignal()

    def __init__(self, title: str, description: str):
        super().__init__()
        self.setObjectName("optionCard")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        heading = QLabel(title)
        heading.setObjectName("optionTitle")
        text = QLabel(description)
        text.setObjectName("muted")
        text.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        layout.addWidget(heading)
        layout.addWidget(text)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def choose_import_mode(parent) -> Optional[str]:
    """Returns 'merge', 'replace' or None."""
    from ..transfer import MODE_MERGE, MODE_REPLACE

    dialog = _MessageDialog(parent, "Import data", "How should this file be added?")
    choice: dict[str, str] = {}

    def pick(mode: str) -> None:
        choice["mode"] = mode
        dialog.accept()

    merge = OptionCard("Merge", "Add the file's classes next to the ones you already have.")
    merge.clicked.connect(lambda: pick(MODE_MERGE))
    replace = OptionCard("Replace everything",
                         "Delete what's here and use only the file's data. "
                         "A backup of your current data is saved first.")
    replace.clicked.connect(lambda: pick(MODE_REPLACE))
    dialog.body.addSpacing(8)
    dialog.body.addWidget(merge)
    dialog.body.addWidget(replace)
    dialog.add_button(button("Cancel", slot=dialog.reject))
    dialog.setMinimumWidth(480)
    return choice.get("mode") if dialog.exec() else None
