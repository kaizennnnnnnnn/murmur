"""Home page - greeting + hero tip card + transcript feed grouped by day."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import os

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QClipboard,
    QColor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import theme


_HERO_PORTRAIT: QPixmap | None = None


def _hero_portrait() -> QPixmap:
    """Cached load of the hero backdrop - a tighter, more head-forward
    portrait kept separate from the app-icon source so each can be tuned
    independently."""
    global _HERO_PORTRAIT
    if _HERO_PORTRAIT is None:
        here = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        _HERO_PORTRAIT = QPixmap(os.path.join(here, "assets", "HeroBackdrop.png"))
    return _HERO_PORTRAIT


class _HeroFrame(QFrame):
    """Hero card with the monochrome portrait fading in from the right.

    The card's base background comes from the stylesheet (HERO_BG). On top
    we draw the portrait scaled to card height, anchored to the right edge,
    then overlay a horizontal gradient that fades from solid HERO_BG on the
    left to fully transparent on the right - so the image dissolves into
    the text area instead of stopping with a hard edge."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, 16, 16)
        p.setClipPath(clip)
        p.setPen(Qt.NoPen)

        # Pure-black base under everything so the portrait's solid black
        # source background merges seamlessly into the card. Without this,
        # the gradient fade reveals a HERO_BG (#1F1F28) -> BLACK (#000000)
        # tonal step at the image's left edge - that's the visible seam.
        black = QColor(0, 0, 0)
        p.fillRect(rect, black)

        W, H = rect.width(), rect.height()
        pix = _hero_portrait()
        if pix.isNull():
            p.end()
            return

        # Scale the portrait taller than the card so the head sits inside
        # the visible band and the body bleeds off below.
        target_h = int(H * 1.45)
        scaled = pix.scaledToHeight(target_h, Qt.SmoothTransformation)
        x = int(W - scaled.width() * 0.90)
        y = int(H * 0.5 - scaled.height() * 0.40)
        p.drawPixmap(x, y, scaled)

        # Left-to-right gradient: HERO_BG opaque over the text column,
        # fading to fully transparent past the midpoint. Because the base
        # underneath is now pure black (matching the portrait's bg), the
        # fade reads as HERO_BG -> BLACK with no visible step at the image's
        # left edge - exactly the seamless dissolve the design wants.
        bg = QColor(theme.HERO_BG)
        bg_clear = QColor(bg.red(), bg.green(), bg.blue(), 0)
        grad = QLinearGradient(0, 0, W, 0)
        grad.setColorAt(0.00, bg)
        grad.setColorAt(0.30, bg)
        grad.setColorAt(0.85, bg_clear)
        grad.setColorAt(1.00, bg_clear)
        p.setBrush(grad)
        p.drawRect(rect)

        # Soft top/bottom edge fades so the portrait dissolves into the
        # card's rounded corners instead of meeting them as a flat line.
        edge_h = H * 0.22
        top_grad = QLinearGradient(0, 0, 0, edge_h)
        top_grad.setColorAt(0.0, black)
        top_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(top_grad)
        p.drawRect(QRectF(0, 0, W, edge_h))

        bot_grad = QLinearGradient(0, H - edge_h, 0, H)
        bot_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        bot_grad.setColorAt(1.0, black)
        p.setBrush(bot_grad)
        p.drawRect(QRectF(0, H - edge_h, W, edge_h))

        p.end()


def _fade_in(widget: QWidget, delay_ms: int = 0, duration_ms: int = 380) -> None:
    """Premium-feel entrance: opacity 0->1 with an out-cubic curve, staggered
    by `delay_ms`. The QGraphicsOpacityEffect is retained on the widget so
    later show events don't re-trigger (it stays at opacity 1)."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    # Stash on the widget so the QPropertyAnimation isn't garbage-collected
    # before it gets to run.
    widget._fade_anim = anim  # type: ignore[attr-defined]

    if delay_ms > 0:
        QTimer.singleShot(delay_ms, anim.start)
    else:
        anim.start()


def _format_clock(dt: datetime) -> str:
    h = dt.hour
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12:02d}:{dt.minute:02d} {suffix}"


def _day_header(d: date) -> str:
    today = date.today()
    delta = (today - d).days
    if delta == 0:
        return "TODAY"
    if delta == 1:
        return "YESTERDAY"
    if delta < 7:
        return d.strftime("%A").upper()
    return d.strftime("%b %d, %Y").upper()


class _TranscriptRow(QFrame):
    """One row in the feed: timestamp + text + edit pencil.

    Two modes:
      - view  -> label shows the text; row is clickable to copy.
      - edit  -> QTextEdit with Save / Cancel buttons. Save invokes the
                `saved` signal with (row_id, original_text, new_text) so the
                controller can run the correction-learning pipeline."""

    copied = Signal()
    saved = Signal(int, str, str)  # row_id, original, corrected

    def __init__(self, row_id: int, ts: datetime, text: str, polished: bool):
        super().__init__()
        self.setObjectName("TranscriptRow")
        self.setCursor(Qt.PointingHandCursor)
        self._row_id = row_id
        self._text = text
        self._polished = polished

        h = QHBoxLayout(self)
        h.setContentsMargins(20, 16, 14, 16)
        h.setSpacing(20)

        time_lbl = QLabel(_format_clock(ts).upper())
        time_lbl.setObjectName("TranscriptTime")
        time_lbl.setFixedWidth(64)
        time_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        h.addWidget(time_lbl, 0, Qt.AlignTop)

        # Stack swaps between view-label and edit-textarea
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        h.addWidget(self._stack, 1)

        # View widget (label + optional polish tag)
        self._view_widget = QWidget()
        view_layout = QVBoxLayout(self._view_widget)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(4)
        self._text_lbl = QLabel(text)
        self._text_lbl.setObjectName("TranscriptText")
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        view_layout.addWidget(self._text_lbl)
        if polished:
            tag = QLabel("POLISHED")
            tag.setObjectName("TranscriptPolish")
            view_layout.addWidget(tag, 0, Qt.AlignLeft)
        self._stack.addWidget(self._view_widget)

        # Edit widget (textarea + buttons)
        self._edit_widget = QWidget()
        edit_layout = QVBoxLayout(self._edit_widget)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(8)
        self._edit_field = QTextEdit()
        self._edit_field.setObjectName("RowEdit")
        self._edit_field.setAcceptRichText(False)
        self._edit_field.setFixedHeight(72)
        edit_layout.addWidget(self._edit_field)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self._exit_edit_mode)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        edit_layout.addLayout(btn_row)
        self._stack.addWidget(self._edit_widget)

        # Pencil edit button on the right (only visible in view mode)
        self._edit_btn = QPushButton("✎")
        self._edit_btn.setObjectName("RowEditBtn")
        self._edit_btn.setFlat(True)
        self._edit_btn.setFixedSize(28, 28)
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.setToolTip("Correct this transcript")
        self._edit_btn.clicked.connect(self._enter_edit_mode)
        h.addWidget(self._edit_btn, 0, Qt.AlignTop)

    # ---- mode switching ---------------------------------------------

    def _enter_edit_mode(self) -> None:
        self._edit_field.setPlainText(self._text)
        self._stack.setCurrentWidget(self._edit_widget)
        self._edit_btn.setVisible(False)
        self.setCursor(Qt.ArrowCursor)
        self._edit_field.setFocus()

    def _exit_edit_mode(self) -> None:
        self._stack.setCurrentWidget(self._view_widget)
        self._edit_btn.setVisible(True)
        self.setCursor(Qt.PointingHandCursor)

    def _on_save(self) -> None:
        new_text = self._edit_field.toPlainText().strip()
        if not new_text or new_text == self._text:
            self._exit_edit_mode()
            return
        original = self._text
        self._text = new_text
        self._text_lbl.setText(new_text)
        self._exit_edit_mode()
        self.saved.emit(self._row_id, original, new_text)

    # ---- click-to-copy (view mode only) ------------------------------

    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.LeftButton
            and self._stack.currentWidget() is self._view_widget
        ):
            QGuiApplication.clipboard().setText(self._text)
            self.copied.emit()
        super().mousePressEvent(event)


def _hero(hotkey_label: str) -> QFrame:
    frame = _HeroFrame()
    frame.setObjectName("Hero")
    frame.setMinimumHeight(200)
    l = QHBoxLayout(frame)
    l.setContentsMargins(36, 32, 36, 32)
    l.setSpacing(20)

    left = QVBoxLayout()
    left.setSpacing(10)

    eyebrow = QLabel("GETTING STARTED")
    eyebrow.setObjectName("HeroEyebrow")

    # Rich-text title - emphasises "anywhere" in italic serif, mirrors the
    # Wispr "sound like *you*" cadence.
    title = QLabel(
        "Speak <i>anywhere</i><br/>Murmur types for you."
    )
    title.setObjectName("HeroTitle")
    title.setTextFormat(Qt.RichText)
    title.setWordWrap(True)

    body = QLabel(
        f"Hold <b style='color:#ffffff'>{hotkey_label}</b> in any app — "
        f"or tap the bar at the bottom of your screen for hands-free mode."
    )
    body.setObjectName("HeroBody")
    body.setTextFormat(Qt.RichText)
    body.setWordWrap(True)

    cta = QPushButton("Try it now")
    cta.setObjectName("HeroCta")
    cta.setCursor(Qt.PointingHandCursor)
    cta.setFixedWidth(120)
    cta.clicked.connect(lambda: None)

    left.addWidget(eyebrow)
    left.addSpacing(2)
    left.addWidget(title)
    left.addSpacing(4)
    left.addWidget(body)
    left.addSpacing(10)
    left.addWidget(cta, 0, Qt.AlignLeft)
    left.addStretch(1)
    l.addLayout(left, 1)
    return frame


class HomePage(QWidget):
    # Emitted when the user edits a transcript and clicks Save.
    transcript_corrected = Signal(int, str, str)  # row_id, original, corrected

    def __init__(self, hotkey_label: str):
        super().__init__()
        self._hotkey_label = hotkey_label
        self._entrance_played = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        body = QWidget()
        body.setObjectName("MainArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(44, 38, 16, 44)
        bl.setSpacing(26)

        self._greeting = QLabel("Welcome back")
        self._greeting.setObjectName("Greeting")
        bl.addWidget(self._greeting)

        self._hero_widget = _hero(hotkey_label)
        bl.addWidget(self._hero_widget)

        # Feed wrapper - separate widget so we can fade it as one block.
        self._feed_wrapper = QWidget()
        self._feed_holder = QVBoxLayout(self._feed_wrapper)
        self._feed_holder.setContentsMargins(0, 0, 0, 0)
        self._feed_holder.setSpacing(8)
        bl.addWidget(self._feed_wrapper)

        bl.addStretch(1)
        scroll.setWidget(body)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._entrance_played:
            return
        self._entrance_played = True
        # Staggered cascade: greeting first, hero a beat later, feed last.
        _fade_in(self._greeting,       delay_ms=0,   duration_ms=320)
        _fade_in(self._hero_widget,    delay_ms=80,  duration_ms=420)
        _fade_in(self._feed_wrapper,   delay_ms=180, duration_ms=460)

    def refresh(self) -> None:
        # Clear feed
        while self._feed_holder.count():
            item = self._feed_holder.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                lay = item.layout()
                if lay is not None:
                    while lay.count():
                        sub = lay.takeAt(0)
                        sw = sub.widget()
                        if sw:
                            sw.deleteLater()

        import history
        rows = history.recent(limit=300)
        if not rows:
            empty = QLabel(
                f"Hold {self._hotkey_label} anywhere — your first dictation will land here."
            )
            empty.setObjectName("HeroBody")
            empty.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 13px; padding: 32px 0;"
            )
            empty.setWordWrap(True)
            self._feed_holder.addWidget(empty)
            return

        current_day: Optional[date] = None
        for r in rows:
            d = r.ts.date()
            if d != current_day:
                current_day = d
                header = QLabel(_day_header(d))
                header.setObjectName("SectionLabel")
                header.setContentsMargins(4, 22, 0, 10)
                self._feed_holder.addWidget(header)
            row_widget = _TranscriptRow(r.id, r.ts, r.text, r.polished)
            row_widget.saved.connect(self.transcript_corrected.emit)
            self._feed_holder.addWidget(row_widget)
