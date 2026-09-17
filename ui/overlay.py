"""Murmur floating overlay.

States, all in a frameless always-on-top pill at bottom-center:
  - idle              : thin line; click to start
  - listening_hotkey  : compact pill with centered bars (no buttons)
  - listening_click   : pill with X (cancel) | bars | ✓ (finish)
  - transcribing      : compact pill with wave-animated bars

Visual style: translucent dark glass with a bright white rim. State
transitions animate both the window geometry (smooth size morph) and the
opacity (fade-in). The listening bars have a traveling blue brightness wave
running through them so the row feels alive even between syllables.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

# Palette — neutral black glass with monochrome voice bars to match the
# black-and-white app icon. RECORDING (red) stays as-is because it's a
# functional state indicator, not an aesthetic accent.
_BG_TOP = QColor(26, 26, 30, 215)
_BG_BOTTOM = QColor(6, 6, 9, 215)
_BG_TOP_HOVER = QColor(38, 38, 44, 230)
_BG_BOTTOM_HOVER = QColor(12, 12, 16, 230)
_RIM = QColor(255, 255, 255, 115)
_RIM_INNER = QColor(255, 255, 255, 18)
_TEXT = QColor(228, 232, 240)
_BAR_DIM = QColor(120, 120, 130)
_BAR = QColor(200, 200, 205)
_BAR_BRIGHT = QColor(245, 245, 248)
_DOT_TR = QColor("#ECEAE6")
_DOT_TR_GLOW = QColor(236, 234, 230, 90)
_LOADER_TRACK = QColor(255, 255, 255, 38)
_LOADER_ARC = QColor(232, 235, 240, 230)  # warm near-white, no blue
_BTN_X_BG = QColor(60, 30, 36, 200)
_BTN_X_STROKE = QColor(240, 140, 140)
_BTN_OK_BG = QColor(28, 56, 44, 200)
_BTN_OK_STROKE = QColor(120, 224, 168)

# --- "Hot" palette: applied while the user is actively listening (push-to-talk
# via hotkey OR pill-click toggle). The pill flips to bright white and the
# bars invert to black so it reads as "live mic" at a glance.
_HOT_BG_TOP        = QColor(255, 255, 255, 240)
_HOT_BG_BOTTOM     = QColor(232, 232, 236, 240)
_HOT_RIM           = QColor(0, 0, 0, 60)
_HOT_RIM_INNER     = QColor(255, 255, 255, 90)
_HOT_BAR_DIM       = QColor(120, 120, 128)
_HOT_BAR           = QColor(40, 40, 48)
_HOT_BAR_BRIGHT    = QColor(0, 0, 0)
# Slightly bolder button fills so the red/green still pop against white.
_HOT_BTN_X_BG      = QColor(232, 96, 100, 235)
_HOT_BTN_X_STROKE  = QColor(255, 255, 255)
_HOT_BTN_OK_BG     = QColor(54, 168, 110, 235)
_HOT_BTN_OK_STROKE = QColor(255, 255, 255)

_SIZES = {
    "idle":             (44, 10),
    "listening_hotkey": (146, 22),
    "listening_click":  (188, 26),
    "transcribing":     (156, 22),
}

_BAR_COUNT = 9
_BAR_W = 3
_BAR_GAP = 4
# Ambient = idle bar height as a fraction of max. Lower = more dynamic range
# left for speech to fill, so even quiet syllables visibly jump the bars.
_BAR_AMBIENT = 0.22
_LOADER_R = 5
_BOTTOM_MARGIN = 16
# Noise gate + gain: subtract a small ambient floor so background mic hiss
# doesn't drive the bars, then amplify what's left so speech is clearly
# visible. Tuned so a quiet talker still moves the bars but a silent room
# leaves them at ambient.
_NOISE_FLOOR = 0.008
_LEVEL_GAIN = 36.0
_FADE_MS = 200
_MORPH_MS = 320

# Drop-shadow padding: the widget is larger than the visible pill by this much
# on all sides so the shadow can be painted *inside* the widget bounds (Windows
# refuses to draw outside the bounds of a layered window).
_SHADOW_PAD = 14
_SHADOW_OFFSET_Y = 3
_SHADOW_PASSES = 7
_SHADOW_BASE_ALPHA = 70
_SHADOW_MAX_GROW = 11
# Wave speed/phase: higher AMBIENT_STEP and WAVE_SPEED = more aggressive flow
_AMBIENT_STEP = 0.38
_WAVE_SPEED = 1.1
_BAR_PHASE_OFFSET = 0.65


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class Overlay(QWidget):
    start_clicked = Signal()
    finish_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        self._state = "idle"
        self._level = 0.0
        self._bars = [0.0] * _BAR_COUNT
        self._hover = False
        self._ambient = 0.0  # phase that drives the traveling energy wave

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # 30 fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(_FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

        self._morph = QPropertyAnimation(self, b"geometry")
        self._morph.setDuration(_MORPH_MS)
        self._morph.setEasingCurve(QEasingCurve.OutCubic)

        self.setGeometry(self._target_geometry())

    # ---- transition helpers -------------------------------------------------

    def _fade_in(self) -> None:
        self._fade.stop()
        self.setWindowOpacity(0.0)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _morph_to_state(self) -> None:
        target = self._target_geometry()
        if not self.isVisible():
            self.setGeometry(target)
            return
        self._morph.stop()
        self._morph.setStartValue(self.geometry())
        self._morph.setEndValue(target)
        self._morph.start()

    def _target_geometry(self) -> QRect:
        pill_w, pill_h = _SIZES[self._state]
        widget_w = pill_w + 2 * _SHADOW_PAD
        widget_h = pill_h + 2 * _SHADOW_PAD
        if self._state == "idle":
            screen = QGuiApplication.primaryScreen()
        else:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geom = screen.availableGeometry()
        # Position so the visible pill is centered horizontally and sits
        # _BOTTOM_MARGIN above the screen bottom; the padding extends outward.
        pill_x = geom.center().x() - pill_w // 2
        pill_y = geom.bottom() - pill_h - _BOTTOM_MARGIN
        return QRect(pill_x - _SHADOW_PAD, pill_y - _SHADOW_PAD, widget_w, widget_h)

    # ---- public API ---------------------------------------------------------

    def show_idle(self) -> None:
        previous = self._state
        self._state = "idle"
        self._level = 0.0
        self._bars = [0.0] * _BAR_COUNT
        if previous != "idle":
            self._morph_to_state()
        else:
            self.setGeometry(self._target_geometry())
        self.show()
        self.raise_()
        self.update()

    def show_listening(self, with_buttons: bool) -> None:
        new_state = "listening_click" if with_buttons else "listening_hotkey"
        previous = self._state
        self._state = new_state
        self._level = 0.0
        # Start at ambient height so bars are already at their resting size
        # as soon as the pill finishes morphing in.
        self._bars = [_BAR_AMBIENT] * _BAR_COUNT
        if previous != new_state:
            self._morph_to_state()
            if previous == "transcribing":
                self._fade_in()
        else:
            self.setGeometry(self._target_geometry())
        self.show()
        self.raise_()
        self.update()

    def show_transcribing(self) -> None:
        previous = self._state
        self._state = "transcribing"
        if previous != "transcribing":
            self._morph_to_state()
        self.show()
        self.raise_()
        self.update()

    def update_level(self, rms: float) -> None:
        # Gate out background hiss so the bars don't dance in silence; the
        # remainder is amplified so even soft speech clearly drives them.
        gated = max(0.0, rms - _NOISE_FLOOR)
        self._level = max(0.0, min(1.0, gated * _LEVEL_GAIN))

    def hide_overlay(self) -> None:
        self._timer.stop()
        self._morph.stop()
        self._fade.stop()
        self.hide()

    # ---- mouse --------------------------------------------------------------

    def mouseMoveEvent(self, ev) -> None:
        # Only flag hover when the cursor is inside the visible pill, not the
        # transparent shadow padding around it.
        pos = ev.position().toPoint()
        pill_w, pill_h = _SIZES[self._state]
        in_pill = (
            _SHADOW_PAD <= pos.x() < _SHADOW_PAD + pill_w
            and _SHADOW_PAD <= pos.y() < _SHADOW_PAD + pill_h
        )
        if in_pill != self._hover:
            self._hover = in_pill
            self.update()

    def leaveEvent(self, _ev) -> None:
        if self._hover:
            self._hover = False
            self.update()

    def mousePressEvent(self, ev) -> None:
        if ev.button() != Qt.LeftButton:
            return
        pos = ev.position().toPoint()
        # Reject clicks that land on the transparent shadow area.
        pill_w, pill_h = _SIZES[self._state]
        if not (
            _SHADOW_PAD <= pos.x() < _SHADOW_PAD + pill_w
            and _SHADOW_PAD <= pos.y() < _SHADOW_PAD + pill_h
        ):
            return
        if self._state == "idle":
            self.start_clicked.emit()
        elif self._state == "listening_click":
            if self._cancel_rect().contains(pos):
                self.cancel_clicked.emit()
            elif self._finish_rect().contains(pos):
                self.finish_clicked.emit()

    def _cancel_rect(self) -> QRect:
        _, h = _SIZES["listening_click"]
        sz = 22
        # Widget-local coords: pill starts at (_SHADOW_PAD, _SHADOW_PAD)
        return QRect(_SHADOW_PAD + 6, _SHADOW_PAD + (h - sz) // 2, sz, sz)

    def _finish_rect(self) -> QRect:
        w, h = _SIZES["listening_click"]
        sz = 22
        return QRect(_SHADOW_PAD + w - sz - 6, _SHADOW_PAD + (h - sz) // 2, sz, sz)

    # ---- animation ----------------------------------------------------------

    def _tick(self) -> None:
        self._ambient += _AMBIENT_STEP
        if self._state.startswith("listening"):
            # Envelope follower per bar: fast attack so the bars snap up on
            # any syllable, slower release so they decay back to ambient
            # gracefully instead of stuttering. Asymmetric smoothing is what
            # makes the bars feel "alive" rather than mushy.
            for i in range(_BAR_COUNT):
                jitter = random.uniform(0.6, 1.0)
                audio_lvl = self._level * jitter
                target = max(_BAR_AMBIENT, audio_lvl)
                current = self._bars[i]
                if target > current:
                    # Attack — leap toward the new peak.
                    self._bars[i] = current * 0.25 + target * 0.75
                else:
                    # Release — drift back to baseline.
                    self._bars[i] = current * 0.82 + target * 0.18
        elif self._state == "transcribing":
            # Heights settle to baseline; only colors flow.
            for i in range(_BAR_COUNT):
                self._bars[i] = self._bars[i] * 0.7 + _BAR_AMBIENT * 0.3
        self.update()

    # ---- painting -----------------------------------------------------------

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        # Visible pill lives inside the padded widget
        pill_w, pill_h = _SIZES[self._state]
        pill_x, pill_y = _SHADOW_PAD, _SHADOW_PAD
        radius = pill_h / 2

        # --- Soft drop shadow (several concentric rounded-rect passes) -------
        p.setPen(Qt.NoPen)
        for i in range(_SHADOW_PASSES):
            t = i / max(1, _SHADOW_PASSES - 1)  # 0=innermost, 1=outermost
            grow = _SHADOW_MAX_GROW * t
            alpha = int(_SHADOW_BASE_ALPHA * (1 - t) ** 1.6)
            if alpha < 1:
                continue
            p.setBrush(QColor(0, 0, 0, alpha))
            sx = pill_x - grow
            sy = pill_y - grow + _SHADOW_OFFSET_Y
            sw = pill_w + 2 * grow
            sh = pill_h + 2 * grow
            p.drawRoundedRect(QRectF(sx, sy, sw, sh), radius + grow, radius + grow)

        # --- Pill body --------------------------------------------------------
        hot = self._state in ("listening_hotkey", "listening_click")
        if hot:
            grad_top, grad_bot = _HOT_BG_TOP, _HOT_BG_BOTTOM
            rim_outer, rim_inner = _HOT_RIM, _HOT_RIM_INNER
        elif self._hover and self._state == "idle":
            grad_top, grad_bot = _BG_TOP_HOVER, _BG_BOTTOM_HOVER
            rim_outer, rim_inner = _RIM, _RIM_INNER
        else:
            grad_top, grad_bot = _BG_TOP, _BG_BOTTOM
            rim_outer, rim_inner = _RIM, _RIM_INNER
        grad = QLinearGradient(pill_x, pill_y, pill_x, pill_y + pill_h)
        grad.setColorAt(0.0, grad_top)
        grad.setColorAt(1.0, grad_bot)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), radius, radius)

        # Rim — dark hairline on the white pill, bright on the dark pill.
        p.setPen(QPen(rim_outer, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(
            QRectF(pill_x + 0.5, pill_y + 0.5, pill_w - 1, pill_h - 1),
            radius - 0.5,
            radius - 0.5,
        )
        # Inner highlight
        p.setPen(QPen(rim_inner, 1))
        p.drawRoundedRect(
            QRectF(pill_x + 1.5, pill_y + 1.5, pill_w - 3, pill_h - 3),
            max(0.0, radius - 1.5),
            max(0.0, radius - 1.5),
        )

        # During a geometry morph the pill is between sizes — skip inner
        # content so we don't draw bars at half-size.
        if self._morph.state() == QPropertyAnimation.Running and self._state != "idle":
            interp = self._morph.currentTime() / max(1, self._morph.duration())
            if interp < 0.55:
                return

        if self._state == "idle":
            return

        # All inner content is drawn in pill-local coords; translate once.
        p.translate(pill_x, pill_y)

        if self._state == "listening_hotkey":
            self._paint_bars(p, x_start=(pill_w - self._bars_width()) // 2, h=pill_h, hot=True)
        elif self._state == "listening_click":
            # The hit-test rects are in widget coords; subtract translation.
            cancel = self._cancel_rect().translated(-pill_x, -pill_y)
            finish = self._finish_rect().translated(-pill_x, -pill_y)
            self._paint_button_x(p, cancel, hot=True)
            self._paint_bars(p, x_start=(pill_w - self._bars_width()) // 2, h=pill_h, hot=True)
            self._paint_button_check(p, finish, hot=True)
        elif self._state == "transcribing":
            self._paint_transcribing(p, pill_w, pill_h)

    @staticmethod
    def _bars_width() -> int:
        return _BAR_COUNT * _BAR_W + (_BAR_COUNT - 1) * _BAR_GAP

    def _paint_bars(self, p: QPainter, x_start: int, h: int, hot: bool = False) -> None:
        """Bars with a traveling brightness wave.

        `hot=True` swaps the bar palette to dark-on-white so the bars read
        as black ink on the listening-state pill."""
        if hot:
            bar_dim, bar_mid, bar_bright = _HOT_BAR_DIM, _HOT_BAR, _HOT_BAR_BRIGHT
        else:
            bar_dim, bar_mid, bar_bright = _BAR_DIM, _BAR, _BAR_BRIGHT
        max_h = h - 10
        x = x_start
        p.setPen(Qt.NoPen)
        for i, lvl in enumerate(self._bars):
            bar_h = max(2, int(max_h * lvl))
            y = (h - bar_h) // 2

            # The wave: each bar samples a sine offset by its index. Peaks
            # of the wave become the bright tip color; troughs become the
            # dimmer base. The wave moves left → right over time.
            wave_phase = self._ambient * _WAVE_SPEED - i * _BAR_PHASE_OFFSET
            wave = 0.5 + 0.5 * math.sin(wave_phase)  # 0..1
            top_color = _lerp_color(bar_mid, bar_bright, wave)
            bottom_color = _lerp_color(bar_dim, bar_mid, wave)

            grad = QLinearGradient(0, y, 0, y + bar_h)
            grad.setColorAt(0.0, top_color)
            grad.setColorAt(1.0, bottom_color)
            p.setBrush(grad)
            p.drawRoundedRect(x, y, _BAR_W, bar_h, _BAR_W / 2, _BAR_W / 2)
            x += _BAR_W + _BAR_GAP

    def _paint_transcribing(self, p: QPainter, w: int, h: int) -> None:
        """Green dot (left) + bars (middle) + neutral loader (right)."""
        # Green dot on the left — solid, no rotation
        dot_size = 6
        dot_x = 10
        dot_y = (h - dot_size) // 2
        p.setPen(Qt.NoPen)
        # Soft outer halo for premium feel
        p.setBrush(_DOT_TR_GLOW)
        p.drawEllipse(dot_x - 2, dot_y - 2, dot_size + 4, dot_size + 4)
        # Solid core
        p.setBrush(_DOT_TR)
        p.drawEllipse(dot_x, dot_y, dot_size, dot_size)

        # Neutral-white loader on the right
        loader_cx = w - 12
        loader_cy = h // 2

        # Bars between dot and loader, centered in the gap
        bars_left = dot_x + dot_size + 6
        bars_right = loader_cx - _LOADER_R - 5
        available = bars_right - bars_left
        total = _BAR_COUNT * _BAR_W + (_BAR_COUNT - 1) * _BAR_GAP
        x = bars_left + max(0, (available - total) // 2)
        self._paint_bars(p, x, h)

        self._paint_loader(p, loader_cx, loader_cy)

    def _paint_loader(self, p: QPainter, cx: int, cy: int) -> None:
        r = _LOADER_R
        # Subtle track
        track_pen = QPen(_LOADER_TRACK, 1.2)
        p.setPen(track_pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Rotating arc — neutral near-white (no blue, no green)
        arc_pen = QPen(_LOADER_ARC, 1.6)
        arc_pen.setCapStyle(Qt.RoundCap)
        p.setPen(arc_pen)
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        start_deg = (self._ambient * 38.0) % 360.0
        p.drawArc(rect, int(start_deg * 16), -130 * 16)

    def _paint_button_x(self, p: QPainter, rect: QRect, hot: bool = False) -> None:
        bg = _HOT_BTN_X_BG if hot else _BTN_X_BG
        stroke = _HOT_BTN_X_STROKE if hot else _BTN_X_STROKE
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawEllipse(rect)
        pen = QPen(stroke, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        m = 7
        p.drawLine(
            QPointF(rect.left() + m, rect.top() + m),
            QPointF(rect.right() - m, rect.bottom() - m),
        )
        p.drawLine(
            QPointF(rect.right() - m, rect.top() + m),
            QPointF(rect.left() + m, rect.bottom() - m),
        )

    def _paint_button_check(self, p: QPainter, rect: QRect, hot: bool = False) -> None:
        bg = _HOT_BTN_OK_BG if hot else _BTN_OK_BG
        stroke = _HOT_BTN_OK_STROKE if hot else _BTN_OK_STROKE
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawEllipse(rect)
        pen = QPen(stroke, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        cx, cy = rect.center().x(), rect.center().y()
        p.drawLine(QPointF(cx - 4.5, cy + 0.5), QPointF(cx - 1, cy + 4))
        p.drawLine(QPointF(cx - 1, cy + 4), QPointF(cx + 5, cy - 3))
