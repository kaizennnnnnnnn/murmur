# -*- coding: utf-8 -*-
"""The two promises Murmur makes about what it does not do.

Both are negative claims, and a negative claim cannot be checked by reading
the code around it. These drive the real objects and assert that the call
never happens and the keystrokes never arrive.
"""
import numpy as np
import pytest

from settings import Settings


def noise(seconds=2.0, level=0.02):
    """Long enough to survive the 200 ms head and 100 ms tail trim."""
    rng = np.random.default_rng(0)
    return rng.normal(0, level, int(16_000 * seconds)).astype(np.float32)


class StubTranscriber:
    """Stands in for faster-whisper so no model is loaded and no GPU needed."""

    def __init__(self):
        self.calls = 0

    def ensure_loaded(self):
        pass

    def transcribe(self, audio, initial_prompt=None, vad_threshold=0.5, use_vad=True):
        self.calls += 1
        return "local result"


def run_worker(murmur_main, qapp, monkeypatch, cfg):
    """Run one dictation through the real worker with a spy on the uploader.

    Returns (uploads, local_calls, text).
    """
    uploads = []

    def spy(audio, key, initial_prompt=None):
        uploads.append(len(audio))
        return "cloud result"

    monkeypatch.setattr(murmur_main, "groq_transcribe", spy)

    stub = StubTranscriber()
    worker = murmur_main.TranscribeWorker(stub, lambda: cfg)
    out = []
    worker.done.connect(out.append)
    worker.run((noise(), 2.0))
    qapp.processEvents()
    return uploads, stub.calls, (out[0].text if out else None)


class TestCloudTranscriptionIsOptIn:
    """An API key is needed for polish and for transforms. It must not, on its
    own, start uploading recordings."""

    def test_key_without_the_switch_uploads_nothing(self, murmur_main, qapp, monkeypatch):
        uploads, local, text = run_worker(
            murmur_main, qapp, monkeypatch,
            Settings(groq_api_key="gsk_pretend", cloud_stt_enabled=False))
        assert uploads == []
        assert local == 1
        assert text == "local result"

    def test_switch_on_uploads_once(self, murmur_main, qapp, monkeypatch):
        uploads, local, text = run_worker(
            murmur_main, qapp, monkeypatch,
            Settings(groq_api_key="gsk_pretend", cloud_stt_enabled=True))
        assert len(uploads) == 1
        assert local == 0
        assert text == "cloud result"

    def test_switch_on_without_a_key_uploads_nothing(self, murmur_main, qapp, monkeypatch):
        uploads, local, _ = run_worker(
            murmur_main, qapp, monkeypatch,
            Settings(groq_api_key="", cloud_stt_enabled=True))
        assert uploads == []
        assert local == 1

    def test_polish_does_not_drag_the_audio_along(self, murmur_main, qapp, monkeypatch):
        """Polish uploads text. It must not also enable the audio upload,
        which is the confusion the separate switch exists to remove."""
        uploads, local, _ = run_worker(
            murmur_main, qapp, monkeypatch,
            Settings(groq_api_key="gsk_pretend", cloud_stt_enabled=False,
                     polish_enabled=True))
        assert uploads == []
        assert local == 1


@pytest.fixture
def watcher(monkeypatch, qapp):
    """A CorrectionWatcher with no real keyboard hook and no live timers, so
    the test is not racing a five second clock."""
    import correction_watcher as cw
    from pynput import keyboard

    w = cw.CorrectionWatcher()
    monkeypatch.setattr(w, "_start_listener", lambda: None)
    monkeypatch.setattr(w, "_reset_max_timer", lambda: None)
    monkeypatch.setattr(w, "_reset_idle_timer", lambda: None)
    monkeypatch.setattr(w, "_reset_idle_timer_unsafe", lambda: None)

    captured = []
    w.correction_captured.connect(lambda r, o, c: captured.append((r, o, c)))

    def focus(hwnd):
        monkeypatch.setattr(cw, "_foreground_window", lambda: hwnd)

    def typed(text):
        for ch in text:
            w._on_press(keyboard.KeyCode.from_char(ch))

    return w, captured, focus, typed


class TestCorrectionsStayInOneWindow:
    """The watcher reads keystrokes after a paste. Anything typed once focus
    has moved belongs to another application and must never be recorded."""

    def test_an_edit_in_the_same_window_is_captured(self, watcher):
        w, captured, focus, typed = watcher
        focus(1000)
        w.start_watching(1, "helo world")
        typed("!")
        w.finalize_now()
        assert len(captured) == 1
        assert captured[0][2] == "helo world!"

    def test_focus_change_discards_instead_of_committing(self, watcher):
        w, captured, focus, typed = watcher
        focus(1000)
        w.start_watching(2, "dear alice")
        typed(" x")
        assert w._buffer == "dear alice x"

        focus(2000)                       # alt-tab to something else
        typed("Hunter2Correct")
        assert w._active is False
        assert w._buffer == ""
        w.finalize_now()
        assert captured == []

    def test_text_typed_elsewhere_never_enters_the_buffer(self, watcher):
        w, captured, focus, typed = watcher
        focus(1000)
        w.start_watching(3, "meeting at five")
        focus(4242)
        typed("sup3rs3cr3t")
        assert "s3cr3t" not in (w._buffer or "")
        assert captured == []

    def test_an_unreadable_window_handle_does_not_break_normal_use(self, watcher):
        """_foreground_window returns 0 when it cannot tell. Discarding a real
        correction because a ctypes call failed would be the worse outcome."""
        w, captured, focus, typed = watcher
        focus(0)
        w.start_watching(4, "plain text")
        typed("!")
        assert w._buffer == "plain text!"
        w.finalize_now()
        assert len(captured) == 1
