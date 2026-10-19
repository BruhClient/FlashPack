"""Line icons drawn from inline SVG (shapes from the Lucide set, lucide.dev, ISC license).

Icons are tinted with theme tokens. Widgets registered through `apply()` are
re-tinted automatically when the theme changes.
"""
from __future__ import annotations

import tempfile
import weakref
from pathlib import Path

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QLabel

from . import theme

PATHS = {
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-up": '<path d="m18 15-6-6-6 6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "arrow-up": '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "pencil": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
    "trash": ('<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
              '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'
              '<line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>'),
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "eye": ('<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 '
            '10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>'),
    "book": '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
    "file-text": ('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
                  '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/>'
                  '<path d="M16 17H8"/>'),
    "layers": ('<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 '
               '1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 '
               '0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>'),
    "circle-dashed": ('<path d="M10.1 2.18a9.93 9.93 0 0 1 3.8 0"/><path d="M17.6 3.71a9.95 9.95 0 0 1 '
                      '2.69 2.7"/><path d="M21.82 10.1a9.93 9.93 0 0 1 0 3.8"/><path d="M20.29 17.6a9.95 '
                      '9.95 0 0 1-2.7 2.69"/><path d="M13.9 21.82a9.94 9.94 0 0 1-3.8 0"/><path d="M6.4 '
                      '20.29a9.95 9.95 0 0 1-2.69-2.7"/><path d="M2.18 13.9a9.93 9.93 0 0 1 0-3.8"/>'
                      '<path d="M3.71 6.4a9.95 9.95 0 0 1 2.7-2.69"/>'),
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "pie-chart": '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
    "activity": ('<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 '
                 '2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>'),
    "bar-chart": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 16h8"/><path d="M7 11h12"/><path d="M7 6h3"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "sun": ('<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/>'
            '<path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/>'
            '<path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>'),
    "download": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/>'
                 '<line x1="12" x2="12" y1="15" y2="3"/>'),
    "share": ('<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/>'
              '<line x1="12" x2="12" y1="2" y2="15"/>'),
    "folder-open": ('<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 '
                    '1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 '
                    '2 0 0 1 2 2v2"/>'),
    "folder-input": ('<path d="M2 9V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 '
                     '1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1"/><path d="M2 13h10"/><path d="m9 16 3-3-3-3"/>'),
    "graduation-cap": ('<path d="M21.42 10.92a1 1 0 0 0-.02-1.84L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 '
                       '0 1.83l8.57 3.91a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 '
                       '12 0v-3.5"/>'),
    "inbox": ('<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 '
              '2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'),
    "alert": ('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
              '<path d="M12 9v4"/><path d="M12 17h.01"/>'),
    "circle-check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "rotate-ccw": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "merge": '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/>',
    "refresh": ('<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
                '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>'),
    "bold": '<path d="M6 12h9a4 4 0 0 1 0 8H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h7a4 4 0 0 1 0 8"/>',
    "italic": ('<line x1="19" x2="10" y1="4" y2="4"/><line x1="14" x2="5" y1="20" y2="20"/>'
               '<line x1="15" x2="9" y1="4" y2="20"/>'),
    "underline": '<path d="M6 4v6a6 6 0 0 0 12 0V4"/><line x1="4" x2="20" y1="20" y2="20"/>',
    "strikethrough": ('<path d="M16 4H9a3 3 0 0 0-2.83 4"/><path d="M14 12a4 4 0 0 1 0 8H6"/>'
                      '<line x1="4" x2="20" y1="12" y2="12"/>'),
    "list": ('<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/>'
             '<path d="M3 12h.01"/><path d="M3 18h.01"/>'),
    "list-ordered": ('<path d="M10 6h11"/><path d="M10 12h11"/><path d="M10 18h11"/><path d="M4 6h1v4"/>'
                     '<path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>'),
    "image": ('<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/>'
              '<path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>'),
    "eraser": ('<path d="M4 7V4h16v3"/><path d="M5 20h6"/><path d="M13 4 8 20"/><path d="m15 15 5 5"/>'
               '<path d="m20 15-5 5"/>'),
    "baseline": '<path d="M4 20h16"/><path d="m6 16 6-12 6 12"/><path d="M8 12h8"/>',
    "highlighter": '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
    "heading": '<path d="M6 12h12"/><path d="M6 20V4"/><path d="M18 20V4"/>',
    "more": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    "arrow-right-left": ('<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/>'
                         '<path d="M4 17h16"/>'),
}

_cache: dict[tuple, QPixmap] = {}
_bound: list[tuple[weakref.ref, str, str, int]] = []


def _ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    return max(2.0, screen.devicePixelRatio()) if screen else 2.0


def svg(name: str, color: str, stroke: float = 2.0, size: int = 24) -> bytes:
    fill = color if name == "play" else "none"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="{fill}" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-linejoin="round">{PATHS[name]}</svg>').encode()


def pixmap(name: str, color: QColor | str, size: int = 16) -> QPixmap:
    hex_color = QColor(color).name()
    ratio = _ratio()
    key = (name, hex_color, size, ratio)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, hex_color))).render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    _cache[key] = pm
    return pm


def icon(name: str, color_key: str = "icon", size: int = 16) -> QIcon:
    result = QIcon()
    result.addPixmap(pixmap(name, theme.color(color_key), size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(pixmap(name, theme.color("faint"), size), QIcon.Mode.Disabled, QIcon.State.Off)
    on = pixmap(name, theme.color("accent_text"), size)
    result.addPixmap(on, QIcon.Mode.Normal, QIcon.State.On)
    result.addPixmap(on, QIcon.Mode.Active, QIcon.State.On)
    return result


def _set(target, name: str, color_key: str, size: int) -> None:
    if isinstance(target, QLabel):
        target.setPixmap(pixmap(name, theme.color(color_key), size))
        return
    target.setIcon(icon(name, color_key, size))
    if hasattr(target, "setIconSize"):
        target.setIconSize(QSize(size, size))


def apply(target, name: str, color_key: str = "icon", size: int = 16):
    """Give a button / action / label an icon that follows the theme. Returns `target`."""
    _set(target, name, color_key, size)
    for i, (ref, *_rest) in enumerate(_bound):
        if ref() is target:
            _bound[i] = (ref, name, color_key, size)
            return target
    _bound.append((weakref.ref(target), name, color_key, size))
    return target


def refresh() -> None:
    """Re-tint every registered icon (called on theme change)."""
    alive = []
    for ref, name, color_key, size in _bound:
        target = ref()
        if target is None:
            continue
        try:
            _set(target, name, color_key, size)
        except RuntimeError:  # underlying Qt object was deleted
            continue
        alive.append((ref, name, color_key, size))
    _bound[:] = alive


def stylesheet_images() -> dict[str, str]:
    """SVG files for stylesheet `image:` properties (arrows, check marks), as QSS-ready paths."""
    folder = Path(tempfile.gettempdir()) / "flagship-icons"
    folder.mkdir(exist_ok=True)
    wanted = {
        "img_chevron_down": ("chevron-down", theme.color("muted")),
        "img_chevron_up": ("chevron-up", theme.color("muted")),
        "img_chevron_right": ("chevron-right", theme.color("muted")),
        "img_check": ("check", theme.color("on_accent")),
    }
    paths = {}
    for key, (name, color) in wanted.items():
        hex_color = color.name()
        path = folder / f"{name}-{hex_color[1:]}-14.svg"
        if not path.exists():
            path.write_bytes(svg(name, hex_color, stroke=3 if name == "check" else 2, size=14))
        paths[key] = path.as_posix()
    return paths
