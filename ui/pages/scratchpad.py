"""Scratchpad — a single free-form text area, autosaved to disk."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from .. import theme


def _scratch_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Murmur" / "scratchpad.txt"


class ScratchpadPage(QWidget):
    """QTextEdit with debounced autosave (writes ~500 ms after last keystroke)."""

    def __init__(self):
        super().__init__()
        self._path = _scratch_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 32, 40, 32)
        outer.setSpacing(14)

        title = QLabel("Scratchpad")
        title.setObjectName("Greeting")
        outer.addWidget(title)

        sub = QLabel("A quiet place for thoughts. Autosaves as you type.")
        sub.setObjectName("CardSub")
        outer.addWidget(sub)

        self._editor = QTextEdit()
        self._editor.setAcceptRichText(False)
        self._editor.setPlaceholderText("Start typing — or dictate here.")
        self._editor.setStyleSheet(
            f"QTextEdit {{ background: {theme.SURFACE}; "
            f"border: 1px solid {theme.BORDER_2}; border-radius: 12px; "
            f"padding: 16px 18px; font-size: 14px; }}"
        )
        outer.addWidget(self._editor, 1)

        self._editor.setPlainText(self._load())

        self._save_timer = QTimer(self)
        self._save_timer.setInterval(500)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save)
        self._editor.textChanged.connect(self._save_timer.start)

    def _load(self) -> str:
        try:
            return self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
        except Exception as exc:
            print(f"[scratchpad] load failed: {exc}")
            return ""

    def _save(self) -> None:
        try:
            self._path.write_text(self._editor.toPlainText(), encoding="utf-8")
        except Exception as exc:
            print(f"[scratchpad] save failed: {exc}")
