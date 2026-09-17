"""Floating toast notification - slides down from the top of the window,
auto-dismisses after a few seconds. Used for 'Learned X for next time' and
similar quiet confirmations."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from . import theme


class Toast(QFrame):
    """Single shared toast - call `show_message()` to display; repeated
    calls replace the current contents and reset the timer."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.hide()

        h = QHBoxLayout(self)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(10)

        self._icon = QLabel("✓")
        self._icon.setObjectName("ToastIcon")
        h.addWidget(self._icon)

        self._label = QLabel("")
        self._label.setObjectName("ToastText")
        self._label.setWordWrap(True)
        h.addWidget(self._label, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide_with_fade)

        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(180)

    # ---- public API --------------------------------------------------

    def show_message(self, text: str, duration_ms: int = 3200) -> None:
        self._label.setText(text)
        self.adjustSize()
        self._position()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(duration_ms)

    # ---- internals ---------------------------------------------------

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        w = self.sizeHint().width()
        # Cap width so very long messages still look tidy.
        w = min(w, int(parent.width() * 0.55))
        h = self.sizeHint().height()
        self.resize(w, h)
        x = (parent.width() - w) // 2
        y = 24
        self.move(x, y)

    def _hide_with_fade(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._on_fade_done)
        self._fade.start()

    def _on_fade_done(self) -> None:
        try:
            self._fade.finished.disconnect(self._on_fade_done)
        except (RuntimeError, TypeError):
            pass
        if self.windowOpacity() <= 0.01:
            self.hide()
