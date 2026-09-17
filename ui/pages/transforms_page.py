"""Transforms page - clipboard-in, AI-rewritten clipboard-out.

Workflow:
  1. User copies text in any app (Ctrl+C)
  2. Switches to Murmur, opens this page
  3. Clicks an Apply button on the transform they want
  4. Murmur sends the clipboard text to Groq, replaces clipboard with the
     result, and shows a status line
  5. User pastes (Ctrl+V) wherever they want the rewritten text
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

import pyperclip
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import transforms as transforms_mod
from settings import Settings


# ---- background worker -----------------------------------------------------

class _TransformWorker(QObject):
    done = Signal(str, bool, str)  # (result, ok, transform_name)

    def __init__(self, text: str, prompt: str, api_key: str, name: str):
        super().__init__()
        self._text = text
        self._prompt = prompt
        self._api_key = api_key
        self._name = name

    @Slot()
    def run(self) -> None:
        result, ok = transforms_mod.apply(self._text, self._prompt, self._api_key)
        self.done.emit(result, ok, self._name)


# ---- transform card --------------------------------------------------------

class _TransformCard(QFrame):
    """One transform displayed as a card with name + description + Apply."""

    apply_clicked = Signal(str, str)  # name, prompt

    def __init__(self, name: str, description: str, prompt: str, removable: bool = False,
                 on_remove: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.setObjectName("SnippetRow")  # reuse the snippet row card style
        self._name = name
        self._prompt = prompt

        h = QHBoxLayout(self)
        h.setContentsMargins(20, 16, 14, 16)
        h.setSpacing(16)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setObjectName("TransformName")
        text_col.addWidget(name_lbl)
        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("CardSub")
        desc_lbl.setWordWrap(True)
        text_col.addWidget(desc_lbl)
        h.addLayout(text_col, 1)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setObjectName("PrimaryBtn")
        self._apply_btn.setCursor(Qt.PointingHandCursor)
        self._apply_btn.setFixedWidth(96)
        self._apply_btn.clicked.connect(
            lambda: self.apply_clicked.emit(self._name, self._prompt)
        )
        h.addWidget(self._apply_btn, 0, Qt.AlignVCenter)

        if removable and on_remove is not None:
            x = QPushButton("×")
            x.setObjectName("DictChipX")
            x.setFlat(True)
            x.setFixedSize(22, 22)
            x.setCursor(Qt.PointingHandCursor)
            x.clicked.connect(lambda: on_remove(name))
            h.addWidget(x, 0, Qt.AlignVCenter)

    def set_applying(self, is_applying: bool) -> None:
        if is_applying:
            self._apply_btn.setText("Applying…")
            self._apply_btn.setEnabled(False)
        else:
            self._apply_btn.setText("Apply")
            self._apply_btn.setEnabled(True)


# ---- the page --------------------------------------------------------------

class TransformsPage(QWidget):
    def __init__(self, cfg: Settings, save: Callable[[Settings], None]):
        super().__init__()
        self._cfg = cfg
        self._save = save
        self._workers: list[tuple[QThread, _TransformWorker]] = []

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
        bl.setSpacing(16)

        title = QLabel("Transforms")
        title.setObjectName("Greeting")
        bl.addWidget(title)

        sub = QLabel(
            "Rewrite text from anywhere. Copy text in any app (Ctrl + C), "
            "click a transform below, then paste the result (Ctrl + V)."
        )
        sub.setObjectName("CardSub")
        sub.setWordWrap(True)
        bl.addWidget(sub)

        self._status = QLabel(self._status_text())
        self._status.setObjectName("FieldHelp")
        self._status.setWordWrap(True)
        bl.addWidget(self._status)

        # ---- Built-in transforms ----
        builtin_label = QLabel("BUILT-IN")
        builtin_label.setObjectName("SectionLabel")
        builtin_label.setContentsMargins(0, 12, 0, 4)
        bl.addWidget(builtin_label)

        self._cards_by_name: dict[str, _TransformCard] = {}
        for t in transforms_mod.DEFAULT_TRANSFORMS:
            card = _TransformCard(t["name"], t["description"], t["prompt"])
            card.apply_clicked.connect(self._on_apply)
            bl.addWidget(card)
            self._cards_by_name[t["name"]] = card

        # ---- Custom transforms ----
        custom_label = QLabel("CUSTOM")
        custom_label.setObjectName("SectionLabel")
        custom_label.setContentsMargins(0, 16, 0, 4)
        bl.addWidget(custom_label)

        self._custom_holder = QVBoxLayout()
        self._custom_holder.setContentsMargins(0, 0, 0, 0)
        self._custom_holder.setSpacing(8)
        bl.addLayout(self._custom_holder)

        # Form to add a custom transform
        form_card = QFrame()
        form_card.setObjectName("Card")
        fl = QVBoxLayout(form_card)
        fl.setContentsMargins(20, 16, 20, 16)
        fl.setSpacing(10)

        fl.addWidget(self._field_label("Transform name"))
        self._new_name = QLineEdit()
        self._new_name.setPlaceholderText("e.g. Translate to Spanish")
        self._new_name.setMaximumWidth(320)
        fl.addWidget(self._new_name)

        fl.addWidget(self._field_label("Prompt"))
        self._new_prompt = QTextEdit()
        self._new_prompt.setPlaceholderText(
            "Translate the user's text to Spanish, keeping the tone. "
            "Reply with only the translation."
        )
        self._new_prompt.setFixedHeight(80)
        self._new_prompt.setAcceptRichText(False)
        fl.addWidget(self._new_prompt)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        add_btn = QPushButton("Save transform")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_save_custom)
        btn_row.addWidget(add_btn)
        fl.addLayout(btn_row)

        bl.addWidget(form_card)
        bl.addStretch(1)
        scroll.setWidget(body)

        self._rebuild_custom_rows()

    # ---- helpers ------------------------------------------------------

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("FieldLabel")
        return lab

    def _status_text(self) -> str:
        if not self._cfg.groq_api_key.strip():
            return ("Transforms send your text to Groq and need an API key — add one in Settings, "
                    "then come back.")
        return "Ready. Copy some text first, then click a transform below."

    # ---- custom transforms (storage) ----------------------------------

    def _on_save_custom(self) -> None:
        name = self._new_name.text().strip()
        prompt = self._new_prompt.toPlainText().strip()
        if not name:
            self._status.setText("Custom transform needs a name.")
            return
        if not prompt:
            self._status.setText("Custom transform needs a prompt.")
            return
        existing_lower = {n.lower() for n in self._cfg.custom_transforms.keys()}
        builtin_lower = {t["name"].lower() for t in transforms_mod.DEFAULT_TRANSFORMS}
        if name.lower() in existing_lower or name.lower() in builtin_lower:
            self._status.setText(f"A transform called '{name}' already exists.")
            return

        new_customs = dict(self._cfg.custom_transforms)
        new_customs[name] = prompt
        self._persist_customs(new_customs)
        self._new_name.clear()
        self._new_prompt.clear()
        self._status.setText(f"Saved '{name}'.")

    def _on_remove_custom(self, name: str) -> None:
        new_customs = dict(self._cfg.custom_transforms)
        new_customs.pop(name, None)
        # Also stop showing 'applying' state if mid-flight.
        card = self._cards_by_name.pop(name, None)
        if card is not None:
            card.set_applying(False)
        self._persist_customs(new_customs)
        self._status.setText(f"Removed '{name}'.")

    def _persist_customs(self, customs: dict) -> None:
        new = replace(self._cfg, custom_transforms=customs)
        self._cfg = new
        self._save(new)
        self._rebuild_custom_rows()

    def _rebuild_custom_rows(self) -> None:
        while self._custom_holder.count():
            item = self._custom_holder.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if not self._cfg.custom_transforms:
            empty = QLabel(
                "No custom transforms yet. Define one below to add your own "
                "rewrite styles (translations, summaries, persona-specific "
                "rewrites, anything)."
            )
            empty.setObjectName("CardSub")
            empty.setWordWrap(True)
            self._custom_holder.addWidget(empty)
            return
        for name, prompt in self._cfg.custom_transforms.items():
            # Use the first sentence of the prompt as the description.
            desc = prompt.strip().split(".")[0]
            if len(desc) > 80:
                desc = desc[:80] + "…"
            card = _TransformCard(
                name, desc, prompt,
                removable=True, on_remove=self._on_remove_custom,
            )
            card.apply_clicked.connect(self._on_apply)
            self._custom_holder.addWidget(card)
            self._cards_by_name[name] = card

    # ---- apply --------------------------------------------------------

    def _on_apply(self, name: str, prompt: str) -> None:
        try:
            clip_text = pyperclip.paste() or ""
        except Exception as exc:
            self._status.setText(f"Couldn't read clipboard: {exc}")
            return
        if not clip_text.strip():
            self._status.setText(
                "Clipboard is empty. Copy some text first, then click Apply."
            )
            return
        if not self._cfg.groq_api_key.strip():
            self._status.setText(
                "Transforms need a Groq API key — add one in Settings."
            )
            return

        card = self._cards_by_name.get(name)
        if card is not None:
            card.set_applying(True)
        self._status.setText(f"Applying '{name}' to clipboard text…")

        worker = _TransformWorker(
            clip_text, prompt, self._cfg.groq_api_key, name,
        )
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_transform_done)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Keep refs so neither gets garbage-collected mid-flight.
        self._workers.append((thread, worker))
        thread.finished.connect(lambda t=thread: self._cleanup_worker(t))
        thread.start()

    def _cleanup_worker(self, thread: QThread) -> None:
        self._workers = [(t, w) for t, w in self._workers if t is not thread]

    @Slot(str, bool, str)
    def _on_transform_done(self, result: str, ok: bool, name: str) -> None:
        card = self._cards_by_name.get(name)
        if card is not None:
            card.set_applying(False)
        if not ok:
            self._status.setText(
                "Transform failed — your clipboard wasn't changed. "
                "Check your API key + network connection."
            )
            return
        try:
            pyperclip.copy(result)
        except Exception as exc:
            self._status.setText(f"Got result, but couldn't write clipboard: {exc}")
            return
        preview = result[:80].replace("\n", " ")
        if len(result) > 80:
            preview += "…"
        self._status.setText(
            f"Done — “{preview}” copied. Switch to your app and Ctrl + V to paste."
        )

    # ---- external sync ------------------------------------------------

    def update_cfg(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._status.setText(self._status_text())
        self._rebuild_custom_rows()
