"""Global push-to-talk hotkey listener via pynput.

Supports single keys ("ctrl_r") or combos ("ctrl+win", "ctrl+alt+space").
Combo semantics: on_press fires when ALL keys in the combo are held simultaneously.
on_release fires when ANY one of those keys is released.
"""
from __future__ import annotations

from typing import Callable, Optional

from pynput import keyboard

K = keyboard.Key

# Logical name → set of pynput keys that satisfy this slot.
# Left/right variants of modifiers all satisfy the bare modifier name,
# so "ctrl+win" works whether the user uses left or right Ctrl/Win.
_KEY_GROUPS: dict[str, set] = {
    "ctrl":     {K.ctrl_l, K.ctrl_r, K.ctrl},
    "ctrl_l":   {K.ctrl_l},
    "ctrl_r":   {K.ctrl_r},
    "alt":      {K.alt_l, K.alt_r, K.alt, K.alt_gr},
    "alt_l":    {K.alt_l},
    "alt_r":    {K.alt_r},
    "shift":    {K.shift_l, K.shift_r, K.shift},
    "shift_l":  {K.shift_l},
    "shift_r":  {K.shift_r},
    "win":      {K.cmd, K.cmd_l, K.cmd_r},   # Windows key on Win, Command on Mac
    "cmd":      {K.cmd, K.cmd_l, K.cmd_r},   # alias for "win"
    "space":    {K.space},
    "f8":       {K.f8},
    "f9":       {K.f9},
    "f10":      {K.f10},
    "f12":      {K.f12},
    "caps_lock":{K.caps_lock},
    "pause":    {K.pause},
}


def _parse_combo(spec: str) -> list[set]:
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"Empty hotkey spec: {spec!r}")
    groups = []
    for p in parts:
        if p not in _KEY_GROUPS:
            raise ValueError(
                f"Unsupported hotkey part: {p!r}. Choose from {sorted(_KEY_GROUPS)}."
            )
        groups.append(_KEY_GROUPS[p])
    return groups


class HotkeyListener:
    def __init__(
        self,
        key_spec: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ):
        self._groups: list[set] = _parse_combo(key_spec)
        self._all_target_keys: set = set().union(*self._groups)
        self._on_press = on_press
        self._on_release = on_release
        self._held: set = set()  # pynput keys currently held that belong to the combo
        self._fired: bool = False
        self._listener: Optional[keyboard.Listener] = None

    def _combo_satisfied(self) -> bool:
        # Every required group must have at least one of its keys currently held.
        return all(any(k in self._held for k in g) for g in self._groups)

    def _press(self, key):
        if key not in self._all_target_keys:
            return
        self._held.add(key)
        if not self._fired and self._combo_satisfied():
            self._fired = True
            try:
                self._on_press()
            except Exception as exc:
                print(f"[hotkey] on_press error: {exc}")

    def _release(self, key):
        if key not in self._all_target_keys:
            return
        self._held.discard(key)
        if self._fired and not self._combo_satisfied():
            self._fired = False
            try:
                self._on_release()
            except Exception as exc:
                print(f"[hotkey] on_release error: {exc}")

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


if __name__ == "__main__":
    import time

    spec = "ctrl+win"
    print(f"Hold {spec.upper().replace('+', ' + ')} to test (Ctrl+C to exit)...")
    hk = HotkeyListener(
        spec,
        on_press=lambda: print("  PRESS"),
        on_release=lambda: print("  RELEASE"),
    )
    hk.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        hk.stop()
