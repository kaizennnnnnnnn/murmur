"""Voice Profile detail view - the premium 'Your Voice' tab.

Visual style mirrors the reference: each insight gets its own surface card
with a large serif-italic display value and a small uppercase eyebrow label.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)



def _profile_card(
    eyebrow: str,
    display: str,
    *,
    italic: bool = True,
    body: str = "",
    min_height: int = 130,
) -> QFrame:
    card = QFrame()
    card.setObjectName("Card")
    card.setMinimumHeight(min_height)
    l = QVBoxLayout(card)
    l.setContentsMargins(26, 24, 26, 24)
    l.setSpacing(6)

    if italic:
        display_lbl = QLabel(f"<i>{display}</i>")
        display_lbl.setTextFormat(Qt.RichText)
    else:
        display_lbl = QLabel(display)
    display_lbl.setObjectName("ProfileDisplay")
    display_lbl.setWordWrap(True)
    l.addWidget(display_lbl)

    l.addSpacing(2)
    eb = QLabel(eyebrow.upper())
    eb.setObjectName("SectionLabel")
    l.addWidget(eb)

    if body:
        bd = QLabel(body)
        bd.setObjectName("CardSub")
        bd.setWordWrap(True)
        l.addSpacing(6)
        l.addWidget(bd)

    l.addStretch(1)
    return card


def _hero_card(summary: str) -> QFrame:
    """Top-of-page card with a short generated description and an eyebrow.

    No illustration - Murmur is a local tool, no marketing avatar belongs
    here. Just a clean statement of who the user *is*, as inferred from
    their dictation history."""
    card = QFrame()
    card.setObjectName("Card")
    l = QVBoxLayout(card)
    l.setContentsMargins(28, 26, 28, 26)
    l.setSpacing(8)

    title = QLabel("Your voice, captured")
    title.setObjectName("ProfileDisplay")
    title.setWordWrap(True)
    l.addWidget(title)

    eb = QLabel("VOICE PROFILE")
    eb.setObjectName("SectionLabel")
    l.addWidget(eb)
    l.addSpacing(8)

    body = QLabel(summary)
    body.setObjectName("CardSub")
    body.setWordWrap(True)
    l.addWidget(body)
    return card


def _fmt_seconds(s: float) -> str:
    if s < 60:
        return f"{int(s)} seconds"
    if s < 3600:
        return f"{int(s // 60)} minutes"
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    return f"{h}h {m}m"


def _generate_summary(stats, profile) -> str:
    """A short, factual paragraph derived from the user's own history.

    Stays out of the way when there isn't enough data yet."""
    if stats.total_dictations == 0:
        return (
            "Murmur builds your voice profile as you dictate. Hold your "
            "hotkey, speak, and this page fills in with the words you use "
            "most, your favorite phrases, and when you're most active."
        )
    pieces: list[str] = []
    pieces.append(
        f"You've spoken {stats.total_words:,} words across "
        f"{stats.total_dictations} dictations"
    )
    if stats.total_seconds > 0:
        pieces.append(f", totalling {_fmt_seconds(stats.total_seconds)} of audio")
    if profile.active_hour is not None:
        from history import format_active_hour
        pieces.append(
            f". You're most active around {format_active_hour(profile.active_hour)}"
        )
    if profile.favorite_word:
        pieces.append(
            f", and the word you reach for most is "
            f"\"{profile.favorite_word}\""
        )
    pieces.append(".")
    return "".join(pieces)


class VoiceProfilePanel(QWidget):
    """Pure content panel - embedded as the 'Your Voice' tab inside Insights."""

    def __init__(self):
        super().__init__()

        bl = QVBoxLayout(self)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(16)

        self._hero_holder = QVBoxLayout()
        self._hero_holder.setSpacing(0)
        bl.addLayout(self._hero_holder)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        bl.addLayout(self._grid)

        bl.addStretch(1)

    def refresh(self) -> None:
        # Clear hero + grid
        while self._hero_holder.count():
            it = self._hero_holder.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        import history
        s = history.stats()
        p = history.profile()

        self._hero_holder.addWidget(_hero_card(_generate_summary(s, p)))

        # Build cards
        cards: list[QFrame] = []

        if p.favorite_word:
            cards.append(_profile_card(
                "Most used word",
                f"“{p.favorite_word}”",
                body=f"{p.favorite_word_count}× across all dictations.",
            ))
        else:
            cards.append(_profile_card(
                "Most used word", "—", italic=False,
                body="Keep dictating — your favorite word will appear here.",
            ))

        if p.top_phrases:
            phrase, count = p.top_phrases[0]
            extra = ""
            if len(p.top_phrases) >= 2:
                others = ", ".join(f"“{ph}”" for ph, _c in p.top_phrases[1:])
                extra = f" Runners-up: {others}."
            cards.append(_profile_card(
                "Favorite phrase",
                f"“{phrase}”",
                body=f"Repeated {count}×.{extra}",
            ))
        else:
            cards.append(_profile_card(
                "Favorite phrase", "—", italic=False,
                body="Phrases you say often will land here.",
            ))

        if p.active_hour is not None:
            cards.append(_profile_card(
                "Your peak time",
                f"around {history.format_active_hour(p.active_hour)}",
                italic=False,
                body="When you dictate most often — a window where your "
                     "voice profile is most reliable.",
            ))
        else:
            cards.append(_profile_card(
                "Your peak time", "—", italic=False,
                body="Once you've dictated across a few hours, your most "
                     "active time will surface here.",
            ))

        cards.append(_profile_card(
            "Vocabulary",
            f"{p.vocab_size:,} words",
            italic=False,
            body="Unique words you've spoken into Murmur.",
        ))

        cards.append(_profile_card(
            "Current streak",
            f"{s.day_streak} day{'s' if s.day_streak != 1 else ''}",
            italic=False,
            body="Consecutive days you've used Murmur.",
        ))

        cards.append(_profile_card(
            "Time spoken",
            _fmt_seconds(s.total_seconds),
            italic=False,
            body=(
                f"Across {s.total_dictations} dictation"
                f"{'s' if s.total_dictations != 1 else ''}, "
                f"averaging {int(round(s.avg_wpm))} wpm."
            ),
        ))

        for i, c in enumerate(cards):
            self._grid.addWidget(c, i // 2, i % 2)
