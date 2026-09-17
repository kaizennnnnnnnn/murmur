"""Murmur system tray icon.

A stylised "M" monogram drawn as a single continuous stroke with rounded
joins. The two peaks and shallow valley make it read as both the brand
initial and a sound-wave envelope. Color reflects the current state.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


_STATE_COLOR = {
    State.IDLE: QColor("#ECEAE6"),
    State.RECORDING: QColor("#E26A6A"),
    State.TRANSCRIBING: QColor("#ECEAE6"),
}


def _make_logo_icon(color: QColor, size: int = 64) -> QIcon:
    """Bold soundwave + accent dot.

    A single thick sine curve (one full cycle: up → through midline → down)
    with a small filled dot floating just to the left at midline. The dot
    reads as the speaking source; the curve as the sound radiating from it.
    Clean at tray size, distinct from anything we've tried before.
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Source dot on the left
    dot_r = size * 0.085
    dot_cx = size * 0.17
    dot_cy = size / 2
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(int(dot_cx - dot_r), int(dot_cy - dot_r),
                  int(dot_r * 2), int(dot_r * 2))

    # Sine curve to the right of the dot
    stroke = max(5, size // 9)
    pen = QPen(color, stroke)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    left_x = dot_cx + dot_r + stroke
    right_x = size - stroke
    mid_y = size / 2
    amplitude = size * 0.22

    path = QPainterPath()
    samples = 48
    for i in range(samples + 1):
        t = i / samples
        x = left_x + t * (right_x - left_x)
        y = mid_y - amplitude * math.sin(t * 2 * math.pi)  # one full cycle
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)

    p.drawPath(path)
    p.end()
    return QIcon(pix)


class Tray:
    def __init__(
        self,
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
        on_open: Callable[[], None] | None = None,
    ):
        self._icons = {s: _make_logo_icon(_STATE_COLOR[s]) for s in State}
        self._tray = QSystemTrayIcon(self._icons[State.IDLE])
        self._tray.setToolTip("Murmur — idle")
        self._on_open = on_open

        self._menu = QMenu()  # hold a Python reference so it can't be GC'd
        menu = self._menu
        if on_open is not None:
            act_open = QAction("Open Murmur", menu)
            act_open.triggered.connect(lambda *_: on_open())
            menu.addAction(act_open)
            menu.addSeparator()

        act_settings = QAction("Settings…", menu)
        act_settings.triggered.connect(lambda *_: on_settings())
        menu.addAction(act_settings)

        menu.addSeparator()

        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(lambda *_: on_quit())
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick and self._on_open is not None:
            self._on_open()

    def set_state(self, state: State, detail: Optional[str] = None) -> None:
        self._tray.setIcon(self._icons[state])
        tip = f"Murmur — {state.value}"
        if detail:
            tip += f" ({detail})"
        self._tray.setToolTip(tip)

    def show_message(self, title: str, body: str) -> None:
        # Pass our QIcon so Windows uses the Murmur monogram in the toast
        # instead of the default blue "i" info icon.
        self._tray.showMessage(title, body, self._icons[State.IDLE], 3000)
