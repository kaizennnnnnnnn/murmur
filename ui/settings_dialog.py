"""Settings dialog: mic, model, hotkey."""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
)

from audio import list_input_devices
from settings import Settings

MODEL_CHOICES = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]
HOTKEY_CHOICES = [
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


class SettingsDialog(QDialog):
    def __init__(self, current: Settings, on_save: Callable[[Settings], None]):
        super().__init__()
        self.setWindowTitle("Murmur Settings")
        self._on_save = on_save

        form = QFormLayout(self)

        self.mic = QComboBox()
        self.mic.addItem("Default device", userData=None)
        for d in list_input_devices():
            self.mic.addItem(f"[{d['index']}] {d['name']}", userData=d["index"])
        self._select_combo_value(self.mic, current.mic_device_index)
        form.addRow("Microphone:", self.mic)

        self.model = QComboBox()
        for m in MODEL_CHOICES:
            self.model.addItem(m, userData=m)
        self._select_combo_value(self.model, current.model_size)
        form.addRow("Whisper model:", self.model)

        self.hotkey = QComboBox()
        for k in HOTKEY_CHOICES:
            self.hotkey.addItem(k, userData=k)
        self._select_combo_value(self.hotkey, current.hotkey_key)
        form.addRow("Push-to-talk key:", self.hotkey)

        form.addRow(QLabel("Changes apply after restart."))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._current = current

    @staticmethod
    def _select_combo_value(combo: QComboBox, value) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _save_and_close(self) -> None:
        s = Settings(
            model_size=self.model.currentData(),
            mic_device_index=self.mic.currentData(),
            hotkey_key=self.hotkey.currentData(),
            min_recording_ms=self._current.min_recording_ms,
        )
        self._on_save(s)
        self.accept()
