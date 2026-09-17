"""Dictionary page - terms that Murmur biases Whisper toward.

Each entry is appended to the `initial_prompt` passed to faster-whisper on
every transcription, which nudges the model toward recognising names,
product names, and jargon it would otherwise mangle.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from settings import Settings
from .. import theme


class _Chip(QFrame):
    """One dictionary term displayed as a rounded pill with a remove button."""

    def __init__(self, term: str, on_remove: Callable[[str], None]):
        super().__init__()
        self.setObjectName("DictChip")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 6, 8, 6)
        h.setSpacing(8)

        lbl = QLabel(term)
        lbl.setObjectName("DictChipText")
        h.addWidget(lbl)

        x = QPushButton("×")
        x.setObjectName("DictChipX")
        x.setFlat(True)
        x.setFixedSize(20, 20)
        x.setCursor(Qt.PointingHandCursor)
        x.clicked.connect(lambda: on_remove(term))
        h.addWidget(x)


class DictionaryPage(QWidget):
    def __init__(self, cfg: Settings, save: Callable[[Settings], None]):
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
        bl.setContentsMargins(44, 38, 44, 44)
        bl.setSpacing(18)

        title = QLabel("Dictionary")
        title.setObjectName("Greeting")
        bl.addWidget(title)

        sub = QLabel(
            "Words you say often — personal names, product names, jargon. "
            "Murmur passes these to Whisper so it stops mishearing them."
        )
        sub.setObjectName("CardSub")
        sub.setWordWrap(True)
        bl.addWidget(sub)

        # ---- Add row ----
        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a word or short phrase…")
        self._input.returnPressed.connect(self._on_add)
        add_row.addWidget(self._input, 1)

        add_btn = QPushButton("Add")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)
        bl.addLayout(add_row)

        # ---- Chip list ----
        self._chips_holder = QVBoxLayout()
        self._chips_holder.setContentsMargins(0, 0, 0, 0)
        self._chips_holder.setSpacing(8)
        bl.addLayout(self._chips_holder)

        self._empty_label = QLabel(
            "No terms yet. Add a name or product Murmur often mishears, and "
            "your next dictation will pick it up immediately."
        )
        self._empty_label.setObjectName("CardSub")
        self._empty_label.setWordWrap(True)

        bl.addStretch(1)
        scroll.setWidget(body)

        self._rebuild_chips()

    # ---- mutations -----------------------------------------------------

    def _on_add(self) -> None:
        term = self._input.text().strip()
        if not term:
            return
        # Dedupe case-insensitively but preserve original casing.
        existing_lower = {t.lower() for t in self._cfg.dictionary_terms}
        if term.lower() in existing_lower:
            self._input.clear()
            return
        new_terms = list(self._cfg.dictionary_terms) + [term]
        self._persist(new_terms)
        self._input.clear()
        self._input.setFocus()

    def _on_remove(self, term: str) -> None:
        new_terms = [t for t in self._cfg.dictionary_terms if t != term]
        self._persist(new_terms)

    def _persist(self, terms: list[str]) -> None:
        new = replace(self._cfg, dictionary_terms=terms)
        self._cfg = new
        self._save(new)
        self._rebuild_chips()

    # ---- view ----------------------------------------------------------

    def _rebuild_chips(self) -> None:
        # Clear current rows
        while self._chips_holder.count():
            item = self._chips_holder.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        terms = self._cfg.dictionary_terms
        if not terms:
            self._chips_holder.addWidget(self._empty_label)
            self._empty_label.show()
            return
        self._empty_label.hide()

        # Pack chips into wrapping rows manually - 3 per row at ~280px each.
        per_row = 3
        for i in range(0, len(terms), per_row):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            for t in terms[i : i + per_row]:
                row.addWidget(_Chip(t, on_remove=self._on_remove))
            row.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(row)
            self._chips_holder.addWidget(wrap)

    def update_cfg(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._rebuild_chips()
