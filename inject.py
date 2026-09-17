"""Text injection: save clipboard → set transcript → simulate Ctrl+V → restore.

Clipboard-paste is the most reliable cross-app injection: works in Chrome,
VS Code, Slack, Discord, Notepad, Word, terminals, etc.
"""
from __future__ import annotations

import time

import pyperclip
from pynput.keyboard import Controller, Key

_kb = Controller()


def _safe_get_clipboard() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def inject_text(text: str, restore_delay: float = 0.1) -> None:
    if not text:
        return

    previous = _safe_get_clipboard()

    try:
        pyperclip.copy(text)
    except Exception as exc:
        print(f"[inject] clipboard write failed: {exc}")
        return

    time.sleep(0.02)

    with _kb.pressed(Key.ctrl):
        _kb.press("v")
        _kb.release("v")

    time.sleep(restore_delay)

    try:
        pyperclip.copy(previous)
    except Exception:
        pass


if __name__ == "__main__":
    print("Switch to a text field within 4 seconds...")
    time.sleep(4)
    inject_text("Hello from MyWisprFlow injection test.")
    print("Done. Check the target window.")
