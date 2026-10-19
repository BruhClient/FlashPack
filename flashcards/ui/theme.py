"""Light/dark design tokens, the app palette and the templated stylesheet.

Widgets read colors through `color(key)` at paint time, and listen to
`manager().changed` when they cache anything color-dependent.
"""
from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Optional

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

# "Paper and ink": warm neutrals, black ink as the only UI accent, earthy data colours,
# and a red rule borrowed from ruled index cards.
LIGHT = {
    "bg": "#FAF8F4", "sidebar": "#F2EFE9", "surface": "#FFFFFF", "elevated": "#FFFFFF",
    "border": "#DCD6CA", "border_soft": "#E8E3D9", "hover": "#EFEBE3", "pressed": "#E5E0D5",
    "text": "#1E1C19", "muted": "#6E685E", "faint": "#A29C90", "icon": "#4F4A42",
    "accent": "#1E1C19", "accent_hover": "#3A362F", "accent_text": "#1E1C19",
    "accent_soft": "#ECE7DD", "on_accent": "#FAF8F4", "accent_disabled": "#C9C3B6",
    "selection": "#E9E4DA", "text_selection": "#F6E39A", "rule": "#E08273",
    "danger": "#A9412C", "danger_soft": "#F6E6E1", "danger_border": "#E6C2B8",
    "danger_solid": "#A9412C", "danger_solid_hover": "#8E3524",
    "success": "#3E7151", "success_soft": "#E4EEE6",
    "track": "#ECE7DD", "grid": "#DED8CC", "chart_accent": "#1E1C19",
    "untested": "#DDD7CB", "struggling": "#C4573F", "learning": "#D8A343", "mastered": "#4D7F5E",
    "tooltip_bg": "#1E1C19", "tooltip_text": "#FAF8F4",
    "toast_bg": "#1E1C19", "toast_text": "#FAF8F4",
    "scrollbar": "#D5CFC2", "scrollbar_hover": "#A29C90",
    "r1": "#C4573F", "r2": "#C9773F", "r3": "#BE9334", "r4": "#5E8E68", "r5": "#3E7151",
}

DARK = {
    "bg": "#1B1A18", "sidebar": "#161513", "surface": "#242321", "elevated": "#282725",
    "border": "#3A3834", "border_soft": "#2E2C29", "hover": "#2A2926", "pressed": "#35332F",
    "text": "#ECE7DD", "muted": "#A39D91", "faint": "#6F6A61", "icon": "#BEB8AC",
    "accent": "#ECE7DD", "accent_hover": "#FFFFFF", "accent_text": "#ECE7DD",
    "accent_soft": "#302E2A", "on_accent": "#1B1A18", "accent_disabled": "#4A4741",
    "selection": "#302E2A", "text_selection": "#5E4E1F", "rule": "#9C5246",
    "danger": "#E28069", "danger_soft": "#3A231D", "danger_border": "#6A3528",
    "danger_solid": "#B4472F", "danger_solid_hover": "#C85840",
    "success": "#86B394", "success_soft": "#1F2D23",
    "track": "#2E2C29", "grid": "#3A3834", "chart_accent": "#ECE7DD",
    "untested": "#46433E", "struggling": "#D2694F", "learning": "#DDAE55", "mastered": "#729F80",
    "tooltip_bg": "#ECE7DD", "tooltip_text": "#1B1A18",
    "toast_bg": "#ECE7DD", "toast_text": "#1B1A18",
    "scrollbar": "#403E39", "scrollbar_hover": "#5E5A53",
    "r1": "#D2694F", "r2": "#D88A55", "r3": "#DDAE55", "r4": "#86B394", "r5": "#6FA383",
}

THEMES = {"light": LIGHT, "dark": DARK}
FONT_CANDIDATES = ("Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Arial")
SERIF_CANDIDATES = ("Sitka Text", "Sitka", "Iowan Old Style", "Charter", "Georgia", "Cambria",
                    "Times New Roman")
STYLE_PATH = Path(__file__).with_name("style.qss")

_manager: Optional["ThemeManager"] = None


def manager() -> Optional["ThemeManager"]:
    return _manager


def tokens() -> dict:
    return _manager.tokens if _manager else LIGHT


def color(key: str) -> QColor:
    return QColor(tokens()[key])


def is_dark() -> bool:
    return bool(_manager and _manager.name == "dark")


def _first_installed(candidates: tuple[str, ...]) -> str:
    families = set(QFontDatabase.families())
    return next((f for f in candidates if f in families), QApplication.font().family())


def serif_font(point_size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """The display serif used for titles, big numbers and card text."""
    font = QFont(_manager.serif_family if _manager else _first_installed(SERIF_CANDIDATES))
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


class ThemeManager(QObject):
    changed = pyqtSignal(str)

    def __init__(self, app: QApplication, name: Optional[str] = None, persist: bool = True):
        super().__init__(app)
        self.app = app
        self.persist = persist
        self._settings = QSettings("Flagship", "Flagship")
        if name not in THEMES:
            saved = self._settings.value("theme", "", type=str) if persist else ""
            system_dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
            name = saved if saved in THEMES else ("dark" if system_dark else "light")
        self.name = name
        self.font_family = _first_installed(FONT_CANDIDATES)
        self.serif_family = _first_installed(SERIF_CANDIDATES)

        app.setStyle("Fusion")
        font = QFont(self.font_family)
        font.setPointSizeF(10)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)

    @property
    def tokens(self) -> dict:
        return THEMES[self.name]

    def set_theme(self, name: str) -> None:
        if name == self.name or name not in THEMES:
            return
        self.name = name
        if self.persist:
            self._settings.setValue("theme", name)
        self._apply()
        self.changed.emit(name)

    def toggle(self) -> None:
        self.set_theme("light" if self.name == "dark" else "dark")

    def _apply(self) -> None:
        from . import icons  # icons needs the theme, so import lazily

        t = self.tokens
        hints = self.app.styleHints()
        if hasattr(hints, "setColorScheme"):
            hints.setColorScheme(Qt.ColorScheme.Dark if self.name == "dark" else Qt.ColorScheme.Light)

        roles = {
            QPalette.ColorRole.Window: t["bg"],
            QPalette.ColorRole.WindowText: t["text"],
            QPalette.ColorRole.Base: t["elevated"],
            QPalette.ColorRole.AlternateBase: t["surface"],
            QPalette.ColorRole.Text: t["text"],
            QPalette.ColorRole.Button: t["surface"],
            QPalette.ColorRole.ButtonText: t["text"],
            QPalette.ColorRole.BrightText: t["on_accent"],
            QPalette.ColorRole.Highlight: t["text_selection"],
            QPalette.ColorRole.HighlightedText: t["text"],
            QPalette.ColorRole.ToolTipBase: t["tooltip_bg"],
            QPalette.ColorRole.ToolTipText: t["tooltip_text"],
            QPalette.ColorRole.PlaceholderText: t["faint"],
            QPalette.ColorRole.Link: t["accent_text"],
            QPalette.ColorRole.Light: t["border"],
            QPalette.ColorRole.Midlight: t["border_soft"],
            QPalette.ColorRole.Mid: t["border"],
            QPalette.ColorRole.Dark: t["faint"],
            QPalette.ColorRole.Shadow: "#000000",
        }
        palette = QPalette()
        for role, value in roles.items():
            palette.setColor(role, QColor(value))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                     QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["faint"]))
        self.app.setPalette(palette)

        values = dict(t)
        values.update(icons.stylesheet_images())
        values["font"] = self.font_family
        values["serif"] = self.serif_family
        qss = Template(STYLE_PATH.read_text(encoding="utf-8")).safe_substitute(values)
        self.app.setStyleSheet(qss)
        icons.refresh()


def install(app: QApplication, name: Optional[str] = None, persist: bool = True) -> ThemeManager:
    global _manager
    _manager = ThemeManager(app, name, persist)
    _manager._apply()
    return _manager
