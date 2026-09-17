"""Snippets page — short triggers that expand to longer phrases.

After every transcription, each trigger present in the text is replaced
with its expansion before the result lands at your cursor. Whole-word,
case-insensitive matching, so 'sig' inside 'design' is left alone.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from PySide6.QtCore import Qt
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


class _SnippetRow(QFrame):
    """One snippet displayed as a card: trigger → expansion + remove."""

    def __init__(self, trigger: str, expansion: str, on_remove: Callable[[str], None]):
        super().__init__()
        self.setObjectName("SnippetRow")
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 14, 14, 14)
        h.setSpacing(16)

        trig_lbl = QLabel(trigger)
        trig_lbl.setObjectName("SnippetTrigger")
        trig_lbl.setMinimumWidth(80)
        h.addWidget(trig_lbl, 0, Qt.AlignTop)

        arrow = QLabel("→")
        arrow.setObjectName("SnippetArrow")
        h.addWidget(arrow, 0, Qt.AlignTop)

        exp_lbl = QLabel(expansion)
        exp_lbl.setObjectName("SnippetExpansion")
        exp_lbl.setWordWrap(True)
        h.addWidget(exp_lbl, 1)

        x = QPushButton("×")
        x.setObjectName("DictChipX")
        x.setFlat(True)
        x.setFixedSize(22, 22)
        x.setCursor(Qt.PointingHandCursor)
        x.clicked.connect(lambda: on_remove(trigger))
        h.addWidget(x, 0, Qt.AlignTop)


class SnippetsPage(QWidget):
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

        title = QLabel("Snippets")
        title.setObjectName("Greeting")
        bl.addWidget(title)

        sub = QLabel(
            "Type a short trigger and Murmur swaps it for the longer text "
            "right before pasting. Great for signatures, addresses, or "
            "anything you say often."
        )
        sub.setObjectName("CardSub")
        sub.setWordWrap(True)
        bl.addWidget(sub)

        # ---- Add form ----
        form_card = QFrame()
        form_card.setObjectName("Card")
        fl = QVBoxLayout(form_card)
        fl.setContentsMargins(20, 16, 20, 16)
        fl.setSpacing(10)

        trig_label = QLabel("Trigger")
        trig_label.setObjectName("FieldLabel")
        fl.addWidget(trig_label)

        self._trigger_input = QLineEdit()
        self._trigger_input.setPlaceholderText("sig")
        self._trigger_input.setMaximumWidth(260)
        self._trigger_input.returnPressed.connect(
            lambda: self._expansion_input.setFocus()
        )
        fl.addWidget(self._trigger_input)

        exp_label = QLabel("Expansion")
        exp_label.setObjectName("FieldLabel")
        fl.addWidget(exp_label)

        self._expansion_input = QLineEdit()
        self._expansion_input.setPlaceholderText(
            "Aaron Smith, aaron@example.com"
        )
        self._expansion_input.returnPressed.connect(self._on_add)
        fl.addWidget(self._expansion_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        add_btn = QPushButton("Add snippet")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(add_btn)
        fl.addLayout(btn_row)

        bl.addWidget(form_card)

        # ---- Status line (errors / confirmations) ----
        self._status = QLabel("")
        self._status.setObjectName("FieldHelp")
        bl.addWidget(self._status)

        # ---- List of snippets ----
        self._rows_holder = QVBoxLayout()
        self._rows_holder.setContentsMargins(0, 0, 0, 0)
        self._rows_holder.setSpacing(8)
        bl.addLayout(self._rows_holder)

        self._empty_label = QLabel(
            "No snippets yet. Add one above and your next dictation will "
            "expand it automatically."
        )
        self._empty_label.setObjectName("CardSub")
        self._empty_label.setWordWrap(True)

        bl.addStretch(1)
        scroll.setWidget(body)

        self._rebuild_rows()

    # ---- mutations ----------------------------------------------------

    def _on_add(self) -> None:
        trigger = self._trigger_input.text().strip()
        expansion = self._expansion_input.text()
        if not trigger:
            self._status.setText("Trigger can't be empty.")
            return
        if " " in trigger:
            self._status.setText("Trigger must be a single word (no spaces).")
            return
        if not expansion:
            self._status.setText("Expansion can't be empty.")
            return

        # Case-insensitive collision check against existing triggers.
        for existing in self._cfg.snippets.keys():
            if existing.lower() == trigger.lower():
                self._status.setText(
                    f"A snippet for '{existing}' already exists — remove it first to replace."
                )
                return

        new_snippets = dict(self._cfg.snippets)
        new_snippets[trigger] = expansion
        self._persist(new_snippets)
        self._trigger_input.clear()
        self._expansion_input.clear()
        self._status.setText(f"Added '{trigger}'.")
        self._trigger_input.setFocus()

    def _on_remove(self, trigger: str) -> None:
        new_snippets = dict(self._cfg.snippets)
        new_snippets.pop(trigger, None)
        self._persist(new_snippets)
        self._status.setText(f"Removed '{trigger}'.")

    def _persist(self, snippets: dict) -> None:
        new = replace(self._cfg, snippets=snippets)
        self._cfg = new
        self._save(new)
        self._rebuild_rows()

    # ---- view ---------------------------------------------------------

    def _rebuild_rows(self) -> None:
        while self._rows_holder.count():
            item = self._rows_holder.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if not self._cfg.snippets:
            self._rows_holder.addWidget(self._empty_label)
            self._empty_label.show()
            return
        self._empty_label.hide()

        for trigger, expansion in self._cfg.snippets.items():
            self._rows_holder.addWidget(
                _SnippetRow(trigger, expansion, on_remove=self._on_remove)
            )

    def update_cfg(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._rebuild_rows()
