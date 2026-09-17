"""Inline correction detection - the "Wispr Flow" trick.

After Murmur pastes a transcription, this module hooks a global keyboard
listener for a short window. It maintains a virtual text buffer that starts
out equal to the pasted text. Each keystroke the user makes is replayed
onto the buffer:

  - a character key  -> appended
  - space/enter/tab  -> appended
  - backspace        -> trims the last char off the buffer
  - any modifier-down event (Ctrl/Alt/Win) -> ignored (so Ctrl+V paste,
    save shortcuts, etc. don't corrupt the buffer)
  - arrow / home / end / delete / esc / etc. -> invalidates tracking
    (we can no longer be sure where the cursor is, so we stop)

When the window closes (timeout, idle, or a new dictation starts), the
virtual buffer is compared to the original. If they differ meaningfully,
that's the user's correction - emitted as a Qt signal back to the main
thread, where it joins the same learning pipeline as the manual edit on
the Home page.

Best-effort by design. Doesn't try to track cursor position or detect
edits in the middle of the pasted text - those cases just invalidate.
That's still enough to capture the common case: "Murmur typed 'Erin',
I backspaced and typed 'Aaron'."
"""
from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal


# Tunables
_MAX_WINDOW_SEC = 18.0    # hard cap on watch duration after a paste
_IDLE_FINALIZE_SEC = 5.0  # finalize once the user stops typing for this long


class CorrectionWatcher(QObject):
    """Single shared watcher. Call `start_watching(row_id, pasted_text)` after
    every successful paste. Emits `correction_captured` if the user makes a
    contiguous edit on the pasted text."""

    correction_captured = Signal(int, str, str)  # row_id, original, corrected

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._active = False
        self._row_id: Optional[int] = None
        self._original: str = ""
        self._buffer: str = ""
        self._listener = None
        self._max_timer: Optional[threading.Timer] = None
        self._idle_timer: Optional[threading.Timer] = None
        # Modifier state - events with these held are shortcuts, not text.
        self._ctrl = False
        self._alt = False
        self._cmd = False  # Windows / Meta key

    # ---- public API ---------------------------------------------------

    def start_watching(self, row_id: int, pasted_text: str) -> None:
        if not pasted_text:
            return
        with self._lock:
            if self._active:
                # Finalize whatever the previous paste's edits looked like
                # before clobbering it with a fresh tracker.
                self._finalize_locked()
            self._row_id = row_id
            self._original = pasted_text
            self._buffer = pasted_text
            self._ctrl = False
            self._alt = False
            self._cmd = False
            self._active = True
        self._start_listener()
        self._reset_max_timer()
        self._reset_idle_timer()

    def finalize_now(self) -> None:
        """Force an immediate finalize - called when the next dictation
        starts so the previous correction commits before recording the new
        transcript."""
        with self._lock:
            if self._active:
                self._finalize_locked()

    def cancel(self) -> None:
        with self._lock:
            self._cancel_locked()

    # ---- listener -----------------------------------------------------

    def _start_listener(self):
        if self._listener is not None:
            return
        try:
            from pynput import keyboard
        except Exception as exc:
            print(f"[corrections] pynput unavailable: {exc}")
            return
        self._listener = keyboard.Listener(
            on_press=self._on_press_safe,
            on_release=self._on_release_safe,
        )
        self._listener.daemon = True
        self._listener.start()

    def _stop_listener(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _on_press_safe(self, key):
        try:
            self._on_press(key)
        except Exception as exc:
            print(f"[corrections] on_press error: {exc}")

    def _on_release_safe(self, key):
        try:
            self._on_release(key)
        except Exception as exc:
            print(f"[corrections] on_release error: {exc}")

    def _on_press(self, key) -> None:
        from pynput import keyboard
        K = keyboard.Key
        with self._lock:
            if not self._active:
                return
            # Modifier presses - track but don't modify buffer
            if key in (K.ctrl, K.ctrl_l, K.ctrl_r):
                self._ctrl = True
                return
            if key in (K.alt, K.alt_l, K.alt_r, getattr(K, "alt_gr", K.alt)):
                self._alt = True
                return
            if key in (K.cmd, K.cmd_l, K.cmd_r):
                self._cmd = True
                return
            # Shift is fine - it's used while typing capitals.
            if key in (K.shift, K.shift_l, K.shift_r):
                return
            # Any non-shift modifier held -> shortcut chord, ignore the chord key.
            if self._ctrl or self._alt or self._cmd:
                return
            # Backspace: trim
            if key == K.backspace:
                if not self._buffer:
                    # Backspaced past the pasted region - user is editing
                    # unrelated text now, stop tracking.
                    self._cancel_locked()
                    return
                self._buffer = self._buffer[:-1]
                self._reset_idle_timer_unsafe()
                return
            # Whitespace specials
            if key == K.space:
                self._buffer += " "
                self._reset_idle_timer_unsafe()
                return
            if key == K.enter:
                self._buffer += "\n"
                self._reset_idle_timer_unsafe()
                return
            if key == K.tab:
                self._buffer += "\t"
                self._reset_idle_timer_unsafe()
                return
            # Character key (key.char available)
            try:
                ch = key.char
            except AttributeError:
                # Arrow/Home/End/Delete/F-keys/etc - invalidate.
                self._finalize_locked()
                return
            if ch is None:
                return
            self._buffer += ch
            self._reset_idle_timer_unsafe()

    def _on_release(self, key) -> None:
        from pynput import keyboard
        K = keyboard.Key
        with self._lock:
            if key in (K.ctrl, K.ctrl_l, K.ctrl_r):
                self._ctrl = False
            elif key in (K.alt, K.alt_l, K.alt_r, getattr(K, "alt_gr", K.alt)):
                self._alt = False
            elif key in (K.cmd, K.cmd_l, K.cmd_r):
                self._cmd = False

    # ---- timers -------------------------------------------------------

    def _reset_max_timer(self):
        if self._max_timer:
            self._max_timer.cancel()
        self._max_timer = threading.Timer(
            _MAX_WINDOW_SEC, self._on_timer_finalize
        )
        self._max_timer.daemon = True
        self._max_timer.start()

    def _reset_idle_timer(self):
        if self._idle_timer:
            self._idle_timer.cancel()
        self._idle_timer = threading.Timer(
            _IDLE_FINALIZE_SEC, self._on_timer_finalize
        )
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _reset_idle_timer_unsafe(self):
        """Caller must hold the lock."""
        if self._idle_timer:
            self._idle_timer.cancel()
        self._idle_timer = threading.Timer(
            _IDLE_FINALIZE_SEC, self._on_timer_finalize
        )
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_timers(self):
        if self._max_timer:
            self._max_timer.cancel()
            self._max_timer = None
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _on_timer_finalize(self):
        with self._lock:
            self._finalize_locked()

    # ---- finalize / cancel (called with lock held) ---------------------

    def _finalize_locked(self):
        if not self._active:
            return
        self._active = False
        self._stop_listener()
        self._cancel_timers()
        original = self._original
        buffer = self._buffer.strip()
        row_id = self._row_id
        original_stripped = original.strip()
        # Only emit a correction if there's a real, non-trivial difference.
        if (
            buffer
            and row_id is not None
            and buffer != original_stripped
            and self._meaningful_diff(original_stripped, buffer)
        ):
            self.correction_captured.emit(row_id, original_stripped, buffer)

    def _cancel_locked(self):
        self._active = False
        self._stop_listener()
        self._cancel_timers()

    @staticmethod
    def _meaningful_diff(a: str, b: str) -> bool:
        """Skip tiny noise diffs (a stray trailing space, a single char of
        drift) so we don't toast on every random keystroke."""
        if a == b:
            return False
        # If the new buffer is a strict prefix of the original - user is
        # mid-deletion - don't fire yet (the idle timer will catch the
        # final state).
        if a.startswith(b) and len(b) < len(a) - 1:
            return False
        # Reject diffs that lost most of the text - likely Ctrl+A + delete.
        if len(b) < max(2, len(a) // 4):
            return False
        return True
