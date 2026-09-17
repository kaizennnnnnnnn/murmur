"""Embedded Settings page - replaces the old standalone dialog."""
from __future__ import annotations

from dataclasses import replace
from typing import Callable
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from audio import list_input_devices
import polish
from settings import Settings
from .. import theme


_MODEL_CHOICES = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]
_HOTKEY_CHOICES = [
    "ctrl+win",
    "ctrl+alt",
    "ctrl+shift",
    "alt+space",
    "ctrl_r",
    "ctrl_l",
    "alt_r",
    "f8",
    "f9",
    "f10",
    "caps_lock",
    "pause",
]


def _row(label_text: str, control: QWidget, helper: str = "") -> QWidget:
    w = QWidget()
    l = QVBoxLayout(w)
    l.setContentsMargins(0, 0, 0, 0)
    l.setSpacing(6)
    lab = QLabel(label_text)
    lab.setObjectName("FieldLabel")
    l.addWidget(lab)
    l.addWidget(control)
    if helper:
        h = QLabel(helper)
        h.setObjectName("FieldHelp")
        h.setWordWrap(True)
        l.addWidget(h)
    return w


def _select_combo_value(combo: QComboBox, value) -> None:
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return


class SettingsPage(QWidget):
    def __init__(self, cfg: Settings, save: Callable[[Settings], None]):
        super().__init__()
        self._cfg = cfg
        self._save_cb = save

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
        bl.setSpacing(20)

        title = QLabel("Settings")
        title.setObjectName("Greeting")
        bl.addWidget(title)

        # ---- Section: Appearance ------------------------------------------
        bl.addWidget(self._section("Appearance"))

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Light", userData="light")
        self.theme_combo.addItem("Dark", userData="dark")
        _select_combo_value(self.theme_combo, cfg.theme)
        self.theme_combo.activated.connect(self._on_theme_picked)
        bl.addWidget(_row(
            "Theme", self.theme_combo,
            helper="Applies instantly — no Save needed.",
        ))

        # ---- Section: Dictation -------------------------------------------
        bl.addWidget(self._section("Dictation"))

        self.mic = QComboBox()
        self.mic.addItem("Default device", userData=None)
        try:
            for d in list_input_devices():
                self.mic.addItem(f"[{d['index']}] {d['name']}", userData=d["index"])
        except Exception as exc:
            print(f"[settings] mic enumeration failed: {exc}")
        _select_combo_value(self.mic, cfg.mic_device_index)
        bl.addWidget(_row("Microphone", self.mic))

        self.model = QComboBox()
        for m in _MODEL_CHOICES:
            self.model.addItem(m, userData=m)
        _select_combo_value(self.model, cfg.model_size)
        bl.addWidget(_row(
            "Whisper model", self.model,
            helper="small.en is the sweet spot. Smaller = faster, less accurate.",
        ))

        self.hotkey = QComboBox()
        for k in _HOTKEY_CHOICES:
            self.hotkey.addItem(k, userData=k)
        _select_combo_value(self.hotkey, cfg.hotkey_key)
        bl.addWidget(_row("Push-to-talk hotkey", self.hotkey))

        self.sensitivity = QComboBox()
        self.sensitivity.addItem("Normal — everyday speech volume", userData="normal")
        self.sensitivity.addItem("Sensitive — soft talk or noisy room", userData="sensitive")
        self.sensitivity.addItem("Whisper-quiet — actual whispering", userData="whisper")
        _select_combo_value(self.sensitivity, cfg.mic_sensitivity)
        self.sensitivity.activated.connect(self._on_sensitivity_picked)
        bl.addWidget(_row(
            "Microphone sensitivity", self.sensitivity,
            helper="Higher levels amplify quiet audio and loosen Whisper's "
                   "silence filter. Applies immediately.",
        ))

        # ---- Section: AI polish -------------------------------------------
        bl.addWidget(self._section("AI Polish (optional)"))

        self.polish_toggle = QCheckBox("Polish my dictation with Groq")
        self.polish_toggle.setChecked(cfg.polish_enabled)
        bl.addWidget(self.polish_toggle)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("gsk_…")
        self.api_key.setText(cfg.groq_api_key)
        bl.addWidget(_row(
            "Groq API key", self.api_key,
            helper="Free at console.groq.com/keys — no credit card. Stored locally.",
        ))

        self.persona = QComboBox()
        for key, p in polish.PERSONAS.items():
            self.persona.addItem(f"{p.label} — {p.description}", userData=key)
        _select_combo_value(self.persona, cfg.style_persona)
        bl.addWidget(_row(
            "Polish style", self.persona,
            helper="You can also switch styles from the Style page.",
        ))

        # ---- Save row -----------------------------------------------------
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("PrimaryBtn")
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.clicked.connect(self._on_save)
        save_row.addWidget(self._save_btn)
        bl.addLayout(save_row)

        self._status = QLabel("")
        self._status.setObjectName("FieldHelp")
        bl.addWidget(self._status)

        bl.addStretch(1)
        scroll.setWidget(body)

    def _section(self, text: str) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 12, 0, 0)
        l.setSpacing(8)
        lab = QLabel(text.upper())
        lab.setObjectName("SectionLabel")
        l.addWidget(lab)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {theme.BORDER}; background: {theme.BORDER};")
        line.setFixedHeight(1)
        l.addWidget(line)
        return w

    def _on_sensitivity_picked(self) -> None:
        new_val = self.sensitivity.currentData() or "normal"
        if new_val == self._cfg.mic_sensitivity:
            return
        new = replace(self._cfg, mic_sensitivity=new_val)
        self._cfg = new
        self._save_cb(new)

    def _on_theme_picked(self) -> None:
        """Live theme switch - fires the moment the user picks an option,
        without waiting for the Save button. Only the theme field is sent
        through; any unsaved typing in other fields (API key etc.) stays
        in the UI and only persists when the user clicks Save."""
        new_mode = self.theme_combo.currentData() or "light"
        if new_mode == self._cfg.theme:
            return
        print(f"[settings_page] live theme pick -> {new_mode}", file=sys.stderr)
        new = replace(self._cfg, theme=new_mode)
        self._cfg = new
        self._save_cb(new)

    def _on_save(self) -> None:
        new = replace(
            self._cfg,
            model_size=self.model.currentData(),
            mic_device_index=self.mic.currentData(),
            hotkey_key=self.hotkey.currentData(),
            polish_enabled=self.polish_toggle.isChecked(),
            groq_api_key=self.api_key.text().strip(),
            style_persona=self.persona.currentData() or "raw",
            theme=self.theme_combo.currentData() or "light",
            mic_sensitivity=self.sensitivity.currentData() or "normal",
        )
        self._cfg = new
        self._save_cb(new)
        self._status.setText(
            "Saved. Hotkey / mic / model changes apply after restarting Murmur."
        )

    def update_cfg(self, cfg: Settings) -> None:
        self._cfg = cfg
        _select_combo_value(self.persona, cfg.style_persona)
        self.polish_toggle.setChecked(cfg.polish_enabled)
        self.api_key.setText(cfg.groq_api_key)
