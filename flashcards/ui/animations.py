"""Small, reusable motion helpers: crossfades, fade-ins, count-ups, page transitions."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import (
    QAbstractAnimation, QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, Qt,
    QVariantAnimation,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QProgressBar, QStackedWidget, QWidget

FAST = 140
NORMAL = 220
SLOW = 650
EASE = QEasingCurve.Type.OutCubic

_DELETE = QAbstractAnimation.DeletionPolicy.DeleteWhenStopped


def _snapshot(widget: QWidget, parent: QWidget) -> QLabel:
    overlay = QLabel(parent)
    overlay.setPixmap(widget.grab())
    overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    top_left = widget.mapTo(parent, QPoint(0, 0)) if widget is not parent else QPoint(0, 0)
    overlay.setGeometry(top_left.x(), top_left.y(), widget.width(), widget.height())
    overlay.show()
    overlay.raise_()
    return overlay


def _fade_out_and_delete(overlay: QWidget, duration: int) -> QPropertyAnimation:
    effect = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", overlay)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
    anim.finished.connect(overlay.deleteLater)
    anim.start(_DELETE)
    return anim


def crossfade(widget: QWidget, change: Callable[[], None], duration: int = NORMAL,
              parent: QWidget | None = None) -> None:
    """Snapshot `widget`, run `change()`, then fade the snapshot away."""
    if not widget.isVisible() or widget.width() <= 0:
        change()
        return
    overlay = _snapshot(widget, parent or widget)
    change()
    overlay.raise_()
    _fade_out_and_delete(overlay, duration)


def fade_in(widget: QWidget, duration: int = NORMAL) -> None:
    """Fade a widget in; the opacity effect is removed afterwards to keep painting cheap."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(EASE)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(_DELETE)


def count_up(label: QLabel, start: float, end: float, fmt: Callable[[float], str],
             duration: int = SLOW) -> None:
    """Animate a number in a label from `start` to `end`."""
    previous = getattr(label, "_count_anim", None)
    if previous is not None:
        previous.stop()
    anim = QVariantAnimation(label)
    anim.setDuration(duration)
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setEasingCurve(EASE)
    anim.valueChanged.connect(lambda v: label.setText(fmt(v)))
    label._count_anim = anim
    label.setText(fmt(start))
    anim.start()


def glide(bar: QProgressBar, value: int, duration: int = 360) -> None:
    """Move a progress bar smoothly to `value`."""
    previous = getattr(bar, "_glide_anim", None)
    if previous is not None:
        previous.stop()
    anim = QPropertyAnimation(bar, b"value", bar)
    anim.setDuration(duration)
    anim.setStartValue(bar.value())
    anim.setEndValue(value)
    anim.setEasingCurve(EASE)
    bar._glide_anim = anim
    anim.start()


class FadeStack(QStackedWidget):
    """Stacked widget whose page changes crossfade with a slight upward drift."""

    DRIFT = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay: QLabel | None = None

    def fade_to(self, page: QWidget, duration: int = NORMAL) -> None:
        current = self.currentWidget()
        if page is current:
            return
        if current is None or not self.isVisible():
            self.setCurrentWidget(page)
            return
        if self._overlay is not None:
            try:
                self._overlay.deleteLater()
            except RuntimeError:
                pass
        overlay = _snapshot(current, self)
        self._overlay = overlay
        self.setCurrentWidget(page)
        overlay.raise_()

        group = QParallelAnimationGroup(self)
        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity")
        fade.setDuration(duration)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.InOutQuad)
        group.addAnimation(fade)

        rest = page.pos()
        drift = QPropertyAnimation(page, b"pos")
        drift.setDuration(duration + 80)
        drift.setStartValue(rest + QPoint(0, self.DRIFT))
        drift.setEndValue(rest)
        drift.setEasingCurve(EASE)
        group.addAnimation(drift)

        def done():
            try:
                overlay.deleteLater()
            except RuntimeError:  # already removed by a newer transition
                pass
            if self._overlay is overlay:
                self._overlay = None
        group.finished.connect(done)
        group.start(_DELETE)
