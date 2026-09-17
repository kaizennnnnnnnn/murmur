"""Subtle UI sound effects for Murmur.

Generates short tonal blips in-memory at import time and plays them async via
the Windows `winsound` API. No external WAV files needed.
"""
from __future__ import annotations

import io
import sys
import threading
import wave

import numpy as np

_SAMPLE_RATE = 22_050


def _make_double_blip(volume: float = 0.10) -> bytes:
    """Two quick blips ('tap-tap') — second one slightly higher pitch.
    Conversational pair instead of a single held tone."""
    duration_ms = 100
    n_total = int(_SAMPLE_RATE * duration_ms / 1000)
    out = np.zeros(n_total)

    def _short_blip(target: np.ndarray, start_idx: int, length_ms: int, freq: float):
        n = int(_SAMPLE_RATE * length_ms / 1000)
        end_idx = min(start_idx + n, len(target))
        actual_n = end_idx - start_idx
        if actual_n <= 0:
            return
        t = np.arange(actual_n) / _SAMPLE_RATE
        wave = np.sin(2 * np.pi * freq * t)
        env = np.exp(-t * 30.0)
        attack = int(0.002 * _SAMPLE_RATE)
        if attack > 0 and actual_n >= attack:
            env[:attack] *= np.linspace(0.0, 1.0, attack)
        target[start_idx:end_idx] += wave * env

    # Note 1 — D5, 0 → 40 ms
    _short_blip(out, 0, 40, 587.0)
    # Note 2 — F5 (minor third above), 50 → 100 ms
    _short_blip(out, int(_SAMPLE_RATE * 0.050), 50, 698.0)

    out /= max(1e-6, np.max(np.abs(out)))
    samples = (out * volume * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


_START_BLIP = _make_double_blip(volume=0.10)


def _make_learned_chime(volume: float = 0.10) -> bytes:
    """Soft two-note rising chime — C5 → G5 with a longer decay than the
    start blip. Reads as a gentle confirmation rather than a click."""
    duration_ms = 280
    n_total = int(_SAMPLE_RATE * duration_ms / 1000)
    out = np.zeros(n_total)

    def _note(target: np.ndarray, start_idx: int, length_ms: int,
              freq: float, decay: float = 14.0):
        n = int(_SAMPLE_RATE * length_ms / 1000)
        end_idx = min(start_idx + n, len(target))
        actual_n = end_idx - start_idx
        if actual_n <= 0:
            return
        t = np.arange(actual_n) / _SAMPLE_RATE
        wave_sig = np.sin(2 * np.pi * freq * t)
        # Add a quiet harmonic for warmth (octave above at 25% amplitude).
        wave_sig += 0.25 * np.sin(2 * np.pi * freq * 2 * t)
        env = np.exp(-t * decay)
        attack = int(0.004 * _SAMPLE_RATE)
        if attack > 0 and actual_n >= attack:
            env[:attack] *= np.linspace(0.0, 1.0, attack)
        target[start_idx:end_idx] += wave_sig * env

    # C5 → G5 (perfect fifth, friendly rising interval)
    _note(out, 0, 140, 523.25, decay=12.0)
    _note(out, int(_SAMPLE_RATE * 0.070), 200, 783.99, decay=10.0)

    out /= max(1e-6, np.max(np.abs(out)))
    samples = (out * volume * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


_LEARNED_CHIME = _make_learned_chime(volume=0.10)


def _play_blocking(data: bytes) -> None:
    try:
        import winsound
        winsound.PlaySound(data, winsound.SND_MEMORY)
    except Exception as exc:
        print(f"[sound] play failed: {exc}")


def play_start() -> None:
    """Subtle blip when dictation begins. Non-blocking — runs on a daemon thread
    so the 75ms playback doesn't stall the hotkey path."""
    if sys.platform != "win32":
        return
    threading.Thread(target=_play_blocking, args=(_START_BLIP,), daemon=True).start()


def play_learned() -> None:
    """Soft rising chime when Murmur learns a new correction. Pairs with the
    'Learned' toast notification."""
    if sys.platform != "win32":
        return
    threading.Thread(target=_play_blocking, args=(_LEARNED_CHIME,), daemon=True).start()


if __name__ == "__main__":
    import time
    print("Playing start blip...")
    play_start()
    time.sleep(1.0)
