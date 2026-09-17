"""Insights page - two tabs, 'Your Usage' (stats grid) and 'Your Voice'
(voice profile detail). Matches the Wispr-Flow reference layout: title +
tab strip + progress bar + content."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from .voice_profile import VoiceProfilePanel


# ---- helpers ---------------------------------------------------------------

def _stat_card(big: str, label: str, helper: str = "") -> QFrame:
    card = QFrame()
    card.setObjectName("Card")
    l = QVBoxLayout(card)
    l.setContentsMargins(22, 20, 22, 20)
    l.setSpacing(6)
    big_l = QLabel(big)
    big_l.setObjectName("StatBig")
    label_l = QLabel(label)
    label_l.setObjectName("StatLabel")
    l.addWidget(big_l)
    l.addWidget(label_l)
    if helper:
        help_l = QLabel(helper)
        help_l.setObjectName("CardSub")
        help_l.setWordWrap(True)
        l.addWidget(help_l)
    l.addStretch(1)
    return card


def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.1f}K"
    if n >= 1_000:
        return f"{n / 1000:.2f}K"
    return str(n)


def _fmt_seconds(s: float) -> str:
    if s < 60:
        return f"{int(s)}s"
    if s < 3600:
        return f"{int(s // 60)}m"
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    return f"{h}h {m}m"


# ---- usage panel -----------------------------------------------------------

class _UsagePanel(QWidget):
    """The 'Your Usage' tab - 2-row stats grid."""

    def __init__(self):
        super().__init__()
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(14)
        l.addLayout(self._grid)
        l.addStretch(1)

    def refresh(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        import history
        s = history.stats()
        p = history.profile()

        cards = [
            _stat_card(_fmt_count(s.total_words), "total words"),
            _stat_card(str(int(round(s.avg_wpm))), "average wpm"),
            _stat_card(str(s.day_streak), "day streak"),
            _stat_card(str(s.total_dictations), "dictations"),
            _stat_card(_fmt_seconds(s.total_seconds), "time spoken"),
            _stat_card(
                str(p.vocab_size),
                "unique words",
                helper=(f"Favorite: “{p.favorite_word}”" if p.favorite_word else ""),
            ),
        ]
        for i, c in enumerate(cards):
            self._grid.addWidget(c, i // 3, i % 3)


# ---- progress bar (between tabs and content) -------------------------------

class _ProgressBar(QWidget):
    """Slim 4px progress track. Shows how many more words until the voice
    profile crosses the next 'maturity' milestone (every 2000 words)."""

    MILESTONE = 2000  # words per maturity tier

    def __init__(self):
        super().__init__()
        self.setFixedHeight(34)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        track = QFrame()
        track.setObjectName("ProgressTrack")
        track.setFixedHeight(4)
        outer.addWidget(track)
        self._track = track

        # Fill is positioned absolutely via a child frame inside the track.
        self._fill = QFrame(track)
        self._fill.setObjectName("ProgressFill")
        self._fill.setGeometry(0, 0, 0, 4)

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        self._left = QLabel("")
        self._left.setObjectName("FieldHelp")
        self._right = QLabel("")
        self._right.setObjectName("FieldHelp")
        meta.addWidget(self._left)
        meta.addStretch(1)
        meta.addWidget(self._right)
        outer.addLayout(meta)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_fill_width()

    def refresh(self) -> None:
        import history
        s = history.stats()
        w = s.total_words
        tier = w // self.MILESTONE
        next_at = (tier + 1) * self.MILESTONE
        in_tier = w - tier * self.MILESTONE
        self._fraction = in_tier / self.MILESTONE if self.MILESTONE else 0.0

        if tier == 0:
            self._left.setText("Building your voice profile")
        else:
            self._left.setText(f"Tier {tier} voice profile · {w:,} words spoken")
        remaining = next_at - w
        self._right.setText(f"Next update in {remaining:,} more words")
        self._update_fill_width()

    def _update_fill_width(self) -> None:
        if not hasattr(self, "_fraction"):
            return
        full_w = self._track.width()
        self._fill.setGeometry(0, 0, int(full_w * self._fraction), 4)


# ---- the page itself -------------------------------------------------------

class InsightsPage(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header block - title + tabs + progress bar - pinned, not scrolled.
        header = QWidget()
        header.setObjectName("MainArea")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(44, 36, 44, 0)
        hl.setSpacing(0)

        title = QLabel("Insights")
        title.setObjectName("Greeting")
        hl.addWidget(title)
        hl.addSpacing(20)

        # Tab strip
        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        tabs_row.setSpacing(28)

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)

        self._usage_btn = QPushButton("Your Usage")
        self._usage_btn.setObjectName("TabBtn")
        self._usage_btn.setCheckable(True)
        self._usage_btn.setChecked(True)
        self._usage_btn.setCursor(Qt.PointingHandCursor)
        self._tab_group.addButton(self._usage_btn, 0)

        self._voice_btn = QPushButton("Your Voice")
        self._voice_btn.setObjectName("TabBtn")
        self._voice_btn.setCheckable(True)
        self._voice_btn.setCursor(Qt.PointingHandCursor)
        self._tab_group.addButton(self._voice_btn, 1)

        tabs_row.addWidget(self._usage_btn)
        tabs_row.addWidget(self._voice_btn)
        tabs_row.addStretch(1)
        hl.addLayout(tabs_row)
        hl.addSpacing(18)

        self._progress = _ProgressBar()
        hl.addWidget(self._progress)
        hl.addSpacing(20)

        outer.addWidget(header)

        # Scrollable content area - swaps panels based on active tab.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        body = QWidget()
        body.setObjectName("MainArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(44, 0, 44, 44)
        bl.setSpacing(0)

        self._stack = QStackedWidget()
        bl.addWidget(self._stack)
        bl.addStretch(1)
        scroll.setWidget(body)

        self._usage = _UsagePanel()
        self._voice = VoiceProfilePanel()
        self._stack.addWidget(self._usage)
        self._stack.addWidget(self._voice)

        self._tab_group.idClicked.connect(self._switch)

    def _switch(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        if idx == 0:
            self._usage.refresh()
        else:
            self._voice.refresh()

    def refresh(self) -> None:
        self._progress.refresh()
        idx = self._stack.currentIndex()
        if idx == 0:
            self._usage.refresh()
        else:
            self._voice.refresh()

    def show_tab(self, name: str) -> None:
        if name == "voice":
            self._voice_btn.setChecked(True)
            self._switch(1)
        else:
            self._usage_btn.setChecked(True)
            self._switch(0)
