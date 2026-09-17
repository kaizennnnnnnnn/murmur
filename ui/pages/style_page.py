"""Style page - pick which AI persona polishes your dictation."""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import polish


def _persona_card(p: polish.Persona, btn: QRadioButton) -> QFrame:
    card = QFrame()
    card.setObjectName("Card")
    l = QHBoxLayout(card)
    l.setContentsMargins(18, 14, 18, 14)
    l.setSpacing(14)
    l.addWidget(btn, 0, Qt.AlignTop)

    col = QVBoxLayout()
    col.setSpacing(4)
    title = QLabel(p.label)
    title.setObjectName("CardTitle")
    desc = QLabel(p.description)
    desc.setObjectName("CardSub")
    desc.setWordWrap(True)
    col.addWidget(title)
    col.addWidget(desc)
    l.addLayout(col, 1)
    return card


class StylePage(QWidget):
    def __init__(self, cfg, save: Callable[[object], None]):
        super().__init__()
        self._cfg = cfg
        self._save = save

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
        bl.setContentsMargins(40, 32, 40, 40)
        bl.setSpacing(16)

        title = QLabel("Style")
        title.setObjectName("Greeting")
        bl.addWidget(title)

        sub = QLabel(
            "Pick how Murmur cleans up your dictation. Polishing uses Groq's "
            "free Llama 3.3 70B — set your API key in Settings to enable it."
        )
        sub.setObjectName("CardSub")
        sub.setWordWrap(True)
        bl.addWidget(sub)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QRadioButton] = {}

        order = ["raw", "casual", "professional", "email"]
        for key in order:
            p = polish.get_persona(key)
            btn = QRadioButton()
            btn.setChecked(self._cfg.style_persona == key)
            self._group.addButton(btn)
            self._buttons[key] = btn
            card = _persona_card(p, btn)
            bl.addWidget(card)
            btn.toggled.connect(
                lambda checked, k=key: checked and self._on_pick(k)
            )

        # Status row showing polish enabled / api key set
        status = QLabel(self._status_text())
        status.setObjectName("FieldHelp")
        status.setWordWrap(True)
        bl.addWidget(status)
        self._status = status

        bl.addStretch(1)
        scroll.setWidget(body)

    def _status_text(self) -> str:
        if self._cfg.style_persona == "raw":
            return "Currently Raw — polishing is off regardless of API key."
        if not self._cfg.polish_enabled:
            return "Polishing is disabled — turn it on in Settings to use this persona."
        if not self._cfg.groq_api_key.strip():
            return "No Groq API key — paste one in Settings to start polishing."
        return f"Polishing ON — using the {polish.get_persona(self._cfg.style_persona).label} persona."

    def _on_pick(self, key: str) -> None:
        if key == self._cfg.style_persona:
            return
        self._cfg = replace(self._cfg, style_persona=key)
        self._save(self._cfg)
        self._status.setText(self._status_text())

    def update_cfg(self, cfg) -> None:
        """Called when settings change elsewhere - keep persona radio in sync."""
        self._cfg = cfg
        btn = self._buttons.get(cfg.style_persona)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        self._status.setText(self._status_text())
