"""Floating toast pinned just above Murmur's voice bar.

Premium glass-style pill: two-line typography (small uppercase eyebrow +
larger primary text), translucent dark gradient with a top inner highlight
to read as 'glass', soft multi-layer drop shadow, and a slide-down + fade
entrance animation. Click-through enabled so the user can keep working.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QPoint,
    QRect,
    QRectF,
    QTimer,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget


# ---- geometry ---------------------------------------------------------
_SHADOW_PAD   = 18      # extra widget padding used for the drop shadow
_PILL_RADIUS  = 13
_PAD_H        = 16
_PAD_V        = 9
_MIN_WIDTH    = 200
_MAX_WIDTH    = 460
# Vertical gap between the toast pill's bottom edge and the voice bar
# pill's top edge. Tiny gap so they read as a paired stack.
_GAP_ABOVE_BAR_PILL = 10
_SLIDE_PX      = 10     # entrance slide distance

# Match the overlay's own constants so we can anchor exactly above the bar.
_BAR_BOTTOM_MARGIN = 16  # see ui/overlay.py
_BAR_IDLE_HEIGHT   = 10  # see ui/overlay.py _SIZES["idle"]

# ---- palette ----------------------------------------------------------
# Slight cool tint in the dark - reads more "Apple/Linear" than pure black.
_BG_TOP        = QColor(26, 28, 36, 242)
_BG_MID        = QColor(15, 17, 24, 242)
_BG_BOTTOM     = QColor(7, 9, 14, 242)
_RIM           = QColor(255, 255, 255, 70)
_TOP_HIGHLIGHT = QColor(255, 255, 255, 38)
_ACCENT_DOT    = QColor(135, 185, 245)      # Murmur blue
_CHECK         = QColor(120, 215, 165)      # soft mint - positive signal
_EYEBROW       = QColor(170, 185, 215, 195) # cool-tinted eyebrow
_TEXT          = QColor(245, 245, 250)


class OverlayToast(QWidget):
    """Single shared toast. Call `show(eyebrow, body)` to display it."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool                       # no taskbar entry
            | Qt.WindowTransparentForInput  # clicks pass through
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._eyebrow = ""
        self._body = ""
        self._pill_w = _MIN_WIDTH
        self._pill_h = 64

        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_done_cb = None

        self._slide = QPropertyAnimation(self, b"pos")
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)

        self._enter_group = QParallelAnimationGroup(self)
        self._enter_group.addAnimation(self._fade)
        self._enter_group.addAnimation(self._slide)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    # ---- public API ---------------------------------------------------

    def show_message(self, eyebrow: str, body: str, duration_ms: int = 3400) -> None:
        """Two-line display: a small uppercase eyebrow + a primary body line."""
        self._eyebrow = eyebrow.upper()
        self._body = body
        self._measure()
        target_x, target_y = self._anchor_position()
        # Start slightly above the final spot, slide down + fade in.
        start_pos = QPoint(target_x, target_y - _SLIDE_PX)
        end_pos = QPoint(target_x, target_y)
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        self._enter_group.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._slide.setStartValue(start_pos)
        self._slide.setEndValue(end_pos)
        self._enter_group.start()

        self._hide_timer.start(duration_ms)
        self.update()

    # ---- sizing & positioning -----------------------------------------

    def _measure(self) -> None:
        eyebrow_fm = QFontMetrics(self._eyebrow_font())
        body_fm = QFontMetrics(self._body_font())
        eyebrow_w = eyebrow_fm.horizontalAdvance(self._eyebrow)
        body_w = body_fm.horizontalAdvance(self._body)

        # Content column width
        content_w = max(eyebrow_w, body_w)
        # Icon block: 12px dot + 11px gap
        icon_block = 12 + 11
        total_content_w = icon_block + content_w
        pill_w = max(_MIN_WIDTH, min(_MAX_WIDTH, total_content_w + 2 * _PAD_H))

        # Two stacked lines + 2px gap between them
        eyebrow_h = eyebrow_fm.height()
        body_h = body_fm.height()
        pill_h = eyebrow_h + body_h + 2 + 2 * _PAD_V

        self._pill_w = pill_w
        self._pill_h = max(52, pill_h)
        self.resize(pill_w + 2 * _SHADOW_PAD, self._pill_h + 2 * _SHADOW_PAD)

    def _anchor_position(self) -> tuple[int, int]:
        screen = (
            QGuiApplication.screenAt(QCursor.pos())
            or QGuiApplication.primaryScreen()
        )
        geom = screen.availableGeometry()
        widget_w = self._pill_w + 2 * _SHADOW_PAD
        widget_h = self._pill_h + 2 * _SHADOW_PAD
        x = geom.center().x() - widget_w // 2
        # Voice bar's pill (idle) sits with its TOP edge at:
        #   bar_pill_top = geom.bottom() - _BAR_BOTTOM_MARGIN - _BAR_IDLE_HEIGHT
        # Our pill's BOTTOM edge should be `_GAP_ABOVE_BAR_PILL` above that.
        bar_pill_top = geom.bottom() - _BAR_BOTTOM_MARGIN - _BAR_IDLE_HEIGHT
        toast_pill_bottom = bar_pill_top - _GAP_ABOVE_BAR_PILL
        # Widget extends _SHADOW_PAD below the pill, so:
        widget_bottom = toast_pill_bottom + _SHADOW_PAD
        y = widget_bottom - widget_h
        return x, y

    # ---- typography ---------------------------------------------------

    @staticmethod
    def _eyebrow_font() -> QFont:
        f = QFont("Segoe UI", 7)
        f.setWeight(QFont.Bold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.8)
        return f

    @staticmethod
    def _body_font() -> QFont:
        f = QFont("Segoe UI", 10)
        f.setWeight(QFont.Medium)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.2)
        return f

    # ---- painting -----------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        pill_rect = QRectF(
            _SHADOW_PAD, _SHADOW_PAD, self._pill_w, self._pill_h
        )

        # 1. Multi-layer drop shadow - deeper + softer than a single rect.
        for i in range(10, 0, -1):
            alpha = max(0, 80 - i * 7)
            grow = i * 2.0
            shadow_rect = pill_rect.adjusted(-grow, -grow + 4, grow, grow + 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(
                shadow_rect, _PILL_RADIUS + grow, _PILL_RADIUS + grow
            )

        # 2. Body gradient - three stops for a richer surface than a single
        #    top->bottom linear.
        body_path = QPainterPath()
        body_path.addRoundedRect(pill_rect, _PILL_RADIUS, _PILL_RADIUS)
        grad = QLinearGradient(pill_rect.topLeft(), pill_rect.bottomLeft())
        grad.setColorAt(0.0, _BG_TOP)
        grad.setColorAt(0.55, _BG_MID)
        grad.setColorAt(1.0, _BG_BOTTOM)
        p.fillPath(body_path, grad)

        # 3. Inner top highlight - thin lighter stripe for a 'glass' edge.
        p.setClipPath(body_path)
        highlight_rect = QRectF(
            pill_rect.left() + 1, pill_rect.top() + 1,
            pill_rect.width() - 2, 2.0,
        )
        h_grad = QLinearGradient(
            highlight_rect.topLeft(), highlight_rect.topRight()
        )
        h_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        h_grad.setColorAt(0.5, _TOP_HIGHLIGHT)
        h_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(highlight_rect, h_grad)
        p.setClipping(False)

        # 4. Outer rim - subtle 1px stroke just inside the path.
        p.setPen(QPen(_RIM, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(
            pill_rect.adjusted(0.5, 0.5, -0.5, -0.5),
            _PILL_RADIUS, _PILL_RADIUS,
        )

        # 5. Icon - a single small accent dot. Quiet, premium, no check
        #    chrome. Two-layer (soft halo + solid centre) for depth.
        icon_cx = _SHADOW_PAD + _PAD_H + 6
        icon_cy = _SHADOW_PAD + self._pill_h / 2
        p.setPen(Qt.NoPen)
        # Faint halo
        halo = QColor(_ACCENT_DOT)
        halo.setAlpha(60)
        p.setBrush(halo)
        p.drawEllipse(QPoint(int(icon_cx), int(icon_cy)), 7, 7)
        # Solid centre
        p.setBrush(_ACCENT_DOT)
        p.drawEllipse(QPoint(int(icon_cx), int(icon_cy)), 4, 4)

        # 6. Two-line text block: eyebrow on top, body below.
        text_x = icon_cx + 7 + 11
        text_block_w = self._pill_w - (text_x - _SHADOW_PAD) - _PAD_H

        eyebrow_fm = QFontMetrics(self._eyebrow_font())
        body_fm = QFontMetrics(self._body_font())
        block_h = eyebrow_fm.height() + body_fm.height() + 2
        block_top = _SHADOW_PAD + (self._pill_h - block_h) / 2

        # Eyebrow
        p.setFont(self._eyebrow_font())
        p.setPen(_EYEBROW)
        eyebrow_rect = QRectF(
            text_x, block_top, text_block_w, eyebrow_fm.height(),
        )
        p.drawText(
            eyebrow_rect,
            Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine,
            self._eyebrow,
        )

        # Body
        p.setFont(self._body_font())
        p.setPen(_TEXT)
        body_rect = QRectF(
            text_x,
            block_top + eyebrow_fm.height() + 2,
            text_block_w,
            body_fm.height(),
        )
        p.drawText(
            body_rect,
            Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine,
            self._body,
        )
        p.end()

    # ---- fade out -----------------------------------------------------

    def _fade_out(self) -> None:
        self._enter_group.stop()
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade_done_cb = self._after_fade
        self._fade.finished.connect(self._on_fade_done)
        self._fade.start()

    def _on_fade_done(self) -> None:
        try:
            self._fade.finished.disconnect(self._on_fade_done)
        except (RuntimeError, TypeError):
            pass
        if self._fade_done_cb:
            cb, self._fade_done_cb = self._fade_done_cb, None
            cb()

    def _after_fade(self) -> None:
        if self.windowOpacity() <= 0.05:
            self.hide()
