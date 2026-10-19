"""Toast notification that slides up from the bottom of the window and fades away."""
from __future__ import annotations

from PyQt6.QtCore import (
    QAbstractAnimation, QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, Qt, QTimer,
)
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from . import icons

VISIBLE_MS = 2800
SLIDE = 14


class Toast(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.icon = QLabel()
        self.text = QLabel()
        self.text.setObjectName("toastText")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 18, 10)
        layout.setSpacing(10)
        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._group = None
        self.hide()

    def _resting_pos(self) -> QPoint:
        parent = self.parentWidget()
        return QPoint((parent.width() - self.width()) // 2, parent.height() - self.height() - 28)

    def _animate(self, start_opacity, end_opacity, start_pos, end_pos, duration, on_done=None):
        if self._group is not None:
            try:
                self._group.stop()
            except RuntimeError:  # finished and already deleted
                pass
        group = QParallelAnimationGroup(self)
        fade = QPropertyAnimation(self.effect, b"opacity")
        fade.setDuration(duration)
        fade.setStartValue(start_opacity)
        fade.setEndValue(end_opacity)
        move = QPropertyAnimation(self, b"pos")
        move.setDuration(duration)
        move.setStartValue(start_pos)
        move.setEndValue(end_pos)
        move.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(fade)
        group.addAnimation(move)
        if on_done:
            group.finished.connect(on_done)
        self._group = group
        group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def show_message(self, text: str, icon_name: str = "circle-check") -> None:
        icons.apply(self.icon, icon_name, "toast_text", 16)
        self.text.setText(text)
        self.adjustSize()
        rest = self._resting_pos()
        self.move(rest + QPoint(0, SLIDE))
        self.show()
        self.raise_()
        self._animate(self.effect.opacity(), 1.0, rest + QPoint(0, SLIDE), rest, 260)
        self._hide_timer.start(VISIBLE_MS)

    def _fade_out(self) -> None:
        rest = self.pos()
        self._animate(1.0, 0.0, rest, rest + QPoint(0, SLIDE // 2), 320, self.hide)
