"""Murmur - push-to-talk dictation for Windows.

Hold the configured hotkey (default: Ctrl + Win), or click the bottom dock,
speak, release / click ✓. Transcribed text is pasted at the cursor in any app.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def _setup_logging() -> None:
    """Redirect stdout/stderr to a rotating log file so pythonw errors are visible."""
    try:
        log_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "Murmur"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "murmur.log"
        # Truncate at start of each run so we only see the current session.
        f = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
        # Print location to console too (no-op under pythonw).
        print(f"[startup] logging to {log_path}")
    except Exception:
        pass


_setup_logging()


def _excepthook(exc_type, exc, tb):
    import traceback
    traceback.print_exception(exc_type, exc, tb)
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _excepthook

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox


_IPC_PIPE = "Murmur.SingleInstance.v1"


def _signal_running_instance(message: str, timeout_ms: int = 400) -> bool:
    """Try to talk to an already-running Murmur via the named pipe.

    Returns True if a Murmur was found and the message delivered. Used by
    Open-Murmur shortcuts: if Murmur is already running, just tell it to
    pop the window; otherwise the caller proceeds to launch normally."""
    socket = QLocalSocket()
    socket.connectToServer(_IPC_PIPE)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(message.encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True

import history
import settings as settings_mod
import sound
from audio import SAMPLE_RATE, Recorder, get_sensitivity, high_pass, normalize_peak
from hotkey import HotkeyListener
from inject import inject_text
from correction_watcher import CorrectionWatcher
from polish import polish
import snippets as snippets_mod
from transcribe import Transcriber
from transcribe_cloud import groq_transcribe
from ui import theme as theme_mod
from ui.overlay import Overlay
from ui.overlay_toast import OverlayToast
from ui.tray import State, Tray
from ui.window import MurmurWindow


def _correction_added_content(original: str, corrected: str) -> bool:
    """True iff the user's edit added at least one token that wasn't in the
    original. Pure deletions and whitespace tweaks return False so we don't
    toast on every random backspace."""
    import re
    word_re = re.compile(r"[A-Za-z0-9']+")
    orig_tokens = {t.lower() for t in word_re.findall(original)}
    new_tokens = {t.lower() for t in word_re.findall(corrected)}
    return bool(new_tokens - orig_tokens)


def _save_debug_wav(audio, sens_label: str) -> None:
    """Save the post-processing audio to a WAV so we can inspect what was
    captured when transcription comes back empty. Keeps the last 5 files
    so the folder doesn't grow unbounded."""
    import wave
    import time as _time
    import os as _os
    import numpy as _np
    if audio is None or getattr(audio, "size", 0) == 0:
        return
    base = _os.path.join(_os.path.expandvars(r"%APPDATA%"), "Murmur", "debug")
    _os.makedirs(base, exist_ok=True)
    # Prune to 5 most recent
    try:
        wavs = sorted(
            [p for p in _os.listdir(base) if p.endswith(".wav")],
            key=lambda n: _os.path.getmtime(_os.path.join(base, n)),
        )
        for old in wavs[:-4]:
            try:
                _os.remove(_os.path.join(base, old))
            except OSError:
                pass
    except OSError:
        pass
    name = f"rec_{int(_time.time())}_{sens_label}.wav"
    path = _os.path.join(base, name)
    samples = _np.clip(audio, -1.0, 1.0)
    int16 = (samples * 32767.0).astype(_np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(int16.tobytes())
    print(f"[worker] saved debug wav: {path}")


@dataclass
class TranscribeResult:
    text: str
    polished: bool
    duration_s: float


class TranscribeWorker(QObject):
    done = Signal(object)  # TranscribeResult
    failed = Signal(str)
    warmed = Signal()

    def __init__(self, transcriber: Transcriber, get_settings):
        super().__init__()
        self._t = transcriber
        self._get_settings = get_settings

    @Slot()
    def warm(self) -> None:
        try:
            self._t.ensure_loaded()
            self.warmed.emit()
        except Exception as exc:
            self.failed.emit(f"model load failed: {exc}")

    @Slot(object)
    def run(self, job) -> None:
        audio, duration_s = job
        s = self._get_settings()
        sens = get_sensitivity(s.mic_sensitivity)
        import numpy as np
        # Trim the first 200ms and last 100ms - the hotkey press/release
        # creates a massive mechanical transient that dwarfs the actual
        # speech (peak=0.8 transient vs. peak=0.05 voice). Cutting these
        # edges before any processing prevents the transient from distorting
        # the normalize step and the STT.
        trim_start = int(0.20 * 16_000)
        trim_end = int(0.10 * 16_000)
        if audio.size > trim_start + trim_end + 8000:
            audio = audio[trim_start:audio.size - trim_end]
        pre_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        # Always: HP filter (strips rumble) -> normalize (lifts quiet speech
        # to usable levels). The old gain-only path was causing hallucinations
        # because quiet mic audio (peak 0.05) went to Whisper as-is. With
        # the transients trimmed and rumble stripped, normalize is safe.
        if audio.size:
            audio = high_pass(audio)
            audio = normalize_peak(audio, target=0.8)
        post_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        mode = "trim+hp+normalize"
        print(f"[worker] transcribe: samples={audio.size} sens={s.mic_sensitivity} "
              f"{mode} vad_thr={sens['vad_threshold']} "
              f"peak {pre_peak:.3f}->{post_peak:.3f}")
        # Diagnostic WAV dump - keeps the last 5 recordings under
        # %APPDATA%/Murmur/debug/ so we can inspect what the mic actually
        # captured when transcription returns empty.
        try:
            _save_debug_wav(audio, s.mic_sensitivity)
        except Exception as exc:
            print(f"[worker] debug wav save failed: {exc}")
        # Phrase the dictionary as a vocabulary hint in a natural sentence,
        # never as a bare comma-separated list. Whisper treats the prompt as
        # text-to-continue: feed it "Foo, Bar, Baz" and it will sometimes
        # just output "Foo, Bar, Baz" instead of transcribing the audio.
        # Wrapping the terms in a sentence anchors the prompt as context.
        # Dictionary terms are deliberately NOT sent as a prompt to the
        # cloud STT - Whisper treats prompts as text-to-continue, so any
        # word from the dictionary that appears in the prompt becomes
        # something Whisper will happily fall back to when the audio is
        # unclear (it returns "Aaron, Amina, Igor" instead of admitting it
        # didn't hear anything). The prompt is only useful for local
        # transcription on very clear audio with rare proper nouns.
        prompt = None
        # Cloud STT (Groq's Whisper Large v3 Turbo) is far more robust on
        # quiet or noisy mic audio than the local small.en model. It also
        # uploads the recording, so it needs its own explicit opt-in:
        # holding an API key for the polish or transform features must not
        # be enough to start sending audio off the machine. When it is on
        # it runs first, and local Whisper still catches a failure.
        from transcribe import _is_hallucination
        text = ""
        used_cloud = False
        if s.groq_api_key and s.cloud_stt_enabled:
            try:
                raw = groq_transcribe(audio, s.groq_api_key, initial_prompt=prompt)
                if raw and _is_hallucination(raw):
                    print(f"[worker] groq BLOCKED hallucination: {raw!r}")
                    raw = ""
                text = raw
                used_cloud = bool(text)
            except Exception as exc:
                print(f"[worker] groq stt failed: {exc}")
        if not text:
            try:
                text = self._t.transcribe(
                    audio,
                    initial_prompt=prompt,
                    vad_threshold=sens["vad_threshold"],
                    use_vad=sens.get("use_vad", True),
                )
            except Exception as exc:
                self.failed.emit(str(exc))
                return
        engine = "groq" if used_cloud else "local"
        print(f"[worker] transcribe done ({engine}): text={text!r}")
        cleaned, was_polished = polish(
            text,
            persona_key=s.style_persona,
            api_key=s.groq_api_key,
            enabled=s.polish_enabled,
        )
        cleaned = snippets_mod.expand(cleaned, s.snippets)
        self.done.emit(TranscribeResult(
            text=cleaned, polished=was_polished, duration_s=duration_s,
        ))


class Controller(QObject):
    # Cross-thread bridges from pynput's listener to the Qt main thread.
    _press_signal = Signal()
    _release_signal = Signal()
    _transcribe_requested = Signal(object)
    _warm_requested = Signal()

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._cfg = settings_mod.load()
        self._recorder = Recorder(device=self._cfg.mic_device_index)
        self._transcriber = Transcriber(model_size=self._cfg.model_size)
        self._record_start_ts = 0.0

        # Apply the user's theme choice before building any widgets so the
        # initial stylesheet reflects it.
        theme_mod.set_mode(self._cfg.theme)
        self._app.setStyleSheet(theme_mod.STYLESHEET)

        self._tray = Tray(
            on_settings=self._open_settings,
            on_quit=self._quit,
            on_open=self._open_window,
        )
        self._overlay = Overlay()
        # Floating toast pinned just above the voice bar, used for "Learned X".
        self._overlay_toast = OverlayToast()
        # Watches keyboard activity after each paste - captures user edits
        # so we can learn from them ("Wispr Flow"-style inline corrections).
        self._correction_watcher = CorrectionWatcher()
        self._correction_watcher.correction_captured.connect(
            self._on_transcript_corrected
        )
        pretty_key = self._cfg.hotkey_key.upper().replace('+', ' + ')
        self._window = MurmurWindow(
            cfg=self._cfg,
            save_settings=self._on_settings_saved,
            hotkey_label=pretty_key,
        )
        self._window.settings_changed.connect(self._on_window_settings_changed)
        self._window.transcript_corrected.connect(self._on_transcript_corrected)
        self._overlay.start_clicked.connect(self._start_via_click)
        self._overlay.finish_clicked.connect(self._finish_dictation)
        self._overlay.cancel_clicked.connect(self._cancel_dictation)

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(40)
        self._level_timer.timeout.connect(self._poll_level)

        self._worker_thread = QThread()
        self._worker = TranscribeWorker(self._transcriber, lambda: self._cfg)
        self._worker.moveToThread(self._worker_thread)
        self._transcribe_requested.connect(self._worker.run)
        self._warm_requested.connect(self._worker.warm)
        self._worker.done.connect(self._on_transcribed)
        self._worker.failed.connect(self._on_failed)
        self._worker.warmed.connect(self._on_warmed)
        self._worker_thread.start()

        self._press_signal.connect(self._start_via_hotkey)
        self._release_signal.connect(self._finish_dictation)

        self._hotkey = HotkeyListener(
            self._cfg.hotkey_key,
            on_press=self._press_signal.emit,
            on_release=self._release_signal.emit,
        )
        self._hotkey.start()

        self._tray.set_state(State.IDLE)
        self._overlay.show_idle()
        self._tray.show_message("Murmur", f"Hold {pretty_key} or tap the bar to dictate.")

        self._warm_requested.emit()

    # ---- dictation lifecycle -----------------------------------------------

    @Slot()
    def _start_via_hotkey(self) -> None:
        self._start_dictation(via_click=False)

    @Slot()
    def _start_via_click(self) -> None:
        self._start_dictation(via_click=True)

    def _start_dictation(self, via_click: bool) -> None:
        # If the previous paste's correction-watcher is still running, finalize
        # it now - commits whatever edits the user made before this dictation.
        try:
            self._correction_watcher.finalize_now()
        except Exception:
            pass
        if self._recorder.is_recording:
            print("[main] start ignored — already recording")
            return
        print(f"[main] start (via_click={via_click}) sensitivity={self._cfg.mic_sensitivity}")
        sound.play_start()
        self._record_start_ts = time.monotonic()
        try:
            self._recorder.start()
            self._tray.set_state(State.RECORDING)
            self._overlay.show_listening(with_buttons=via_click)
            self._level_timer.start()
        except Exception as exc:
            print(f"[main] mic start failed: {exc}")
            self._tray.show_message("Mic error", str(exc))
            self._overlay.show_idle()

    @Slot()
    def _finish_dictation(self) -> None:
        self._level_timer.stop()
        if not self._recorder.is_recording:
            print("[main] finish: not recording — overlay reset only")
            self._overlay.show_idle()
            return
        audio = self._recorder.stop()
        elapsed_s = time.monotonic() - self._record_start_ts
        import numpy as np
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
        print(f"[main] finish: samples={audio.size} elapsed={elapsed_s:.2f}s "
              f"peak={peak:.3f} rms={rms:.4f}")
        if elapsed_s * 1000 < self._cfg.min_recording_ms or audio.size == 0:
            print(f"[main] finish: discarded (too short, min={self._cfg.min_recording_ms}ms)")
            self._tray.set_state(State.IDLE)
            self._overlay.show_idle()
            return
        duration = audio.size / SAMPLE_RATE
        self._tray.set_state(State.TRANSCRIBING, f"{duration:.1f}s")
        self._overlay.show_transcribing()
        self._transcribe_requested.emit((audio, duration))

    @Slot()
    def _cancel_dictation(self) -> None:
        self._level_timer.stop()
        if self._recorder.is_recording:
            _ = self._recorder.stop()  # discard buffer
        self._tray.set_state(State.IDLE)
        self._overlay.show_idle()
        print("[main] dictation cancelled")

    def _poll_level(self) -> None:
        self._overlay.update_level(self._recorder.level)

    # ---- worker callbacks --------------------------------------------------

    @Slot(object)
    def _on_transcribed(self, result: TranscribeResult) -> None:
        self._tray.set_state(State.IDLE)
        self._overlay.show_idle()
        text = result.text.strip()
        if not text:
            return
        tag = " (polished)" if result.polished else ""
        print(f"[main] transcript{tag}: {text!r}")
        inject_text(text)
        row_id = -1
        try:
            row_id = history.add(
                text, duration_s=result.duration_s, polished=result.polished,
            )
        except Exception as exc:
            print(f"[main] history write failed: {exc}")
        try:
            self._window.notify_new_dictation()
        except Exception as exc:
            print(f"[main] window refresh failed: {exc}")
        # Watch for inline edits the user makes right after the paste. The
        # watcher reads keystrokes, so it is scoped to the window that got
        # the paste and can be turned off entirely in Settings.
        if row_id > 0 and self._cfg.correction_learning_enabled:
            try:
                self._correction_watcher.start_watching(row_id, text)
            except Exception as exc:
                print(f"[main] correction watcher start failed: {exc}")

    @Slot()
    def _on_warmed(self) -> None:
        print("[main] model warmed; ready for dictation")

    @Slot(str)
    def _on_failed(self, msg: str) -> None:
        self._tray.set_state(State.IDLE)
        self._overlay.show_idle()
        print(f"[main] transcribe failed: {msg}")
        self._tray.show_message("Transcription failed", msg)

    # ---- window / settings -------------------------------------------------

    def _open_window(self) -> None:
        print("[main] open_window called")
        try:
            self._window.go("home")
            print("[main] navigated to home")
            self._window.show_and_raise()
            print(f"[main] show_and_raise done; visible={self._window.isVisible()} "
                  f"geom={self._window.geometry()}")
        except Exception as exc:
            import traceback
            print(f"[main] open_window FAILED: {exc}")
            traceback.print_exc()

    def _open_settings(self) -> None:
        print("[main] open_settings called")
        try:
            self._window.go("settings")
            self._window.show_and_raise()
        except Exception as exc:
            import traceback
            print(f"[main] open_settings FAILED: {exc}")
            traceback.print_exc()

    def _on_settings_saved(self, new: settings_mod.Settings) -> None:
        """Called by the embedded Settings page when the user clicks Save."""
        print(f"[main] _on_settings_saved: new.theme={new.theme!r} "
              f"current.theme={self._cfg.theme!r}")
        settings_mod.save(new)
        theme_changed = new.theme != self._cfg.theme
        live_changes = (
            new.polish_enabled != self._cfg.polish_enabled
            or new.groq_api_key != self._cfg.groq_api_key
            or new.style_persona != self._cfg.style_persona
            or theme_changed
        )
        restart_changes = (
            new.model_size != self._cfg.model_size
            or new.mic_device_index != self._cfg.mic_device_index
            or new.hotkey_key != self._cfg.hotkey_key
        )
        self._cfg = new
        if theme_changed:
            theme_mod.set_mode(new.theme)
            self._app.setStyleSheet(theme_mod.STYLESHEET)
            self._window.apply_theme()
        if restart_changes:
            self._tray.show_message(
                "Settings saved",
                "Mic / model / hotkey changes apply after restarting Murmur.",
            )
        elif live_changes:
            self._tray.show_message("Settings saved", "Applied immediately.")

    @Slot()
    def _on_window_settings_changed(self) -> None:
        # Keep dependent page views in sync with whatever was just written.
        try:
            self._window._style.update_cfg(self._cfg)  # internal but fine
            self._window._settings.update_cfg(self._cfg)
            self._window._dictionary.update_cfg(self._cfg)
            self._window._snippets.update_cfg(self._cfg)
            self._window._transforms.update_cfg(self._cfg)
        except Exception:
            pass

    @Slot(int, str, str)
    def _on_transcript_corrected(
        self, row_id: int, original: str, corrected: str
    ) -> None:
        """User edited a transcript on the Home feed.

        Pipeline:
          1. Persist the corrected text into the history DB.
          2. Diff old vs new - any words the user typed that Whisper didn't
             land on become candidates for the dictionary so Whisper hears
             them next time.
          3. Save the updated dictionary into settings (and notify pages).
          4. Toast a short confirmation on the window."""
        try:
            from history import update_text as _update_text, extract_new_words
            _update_text(row_id, corrected)
        except Exception as exc:
            print(f"[main] history.update_text failed: {exc}")

        existing = set(self._cfg.dictionary_terms)
        new_words = extract_new_words(original, corrected, existing=existing)
        if new_words:
            updated = list(self._cfg.dictionary_terms) + new_words
            self._cfg = settings_mod.Settings(
                **{**self._cfg.__dict__, "dictionary_terms": updated}
            )
            try:
                settings_mod.save(self._cfg)
            except Exception as exc:
                print(f"[main] settings.save failed: {exc}")
            # Sync the dictionary page view with the new terms.
            try:
                self._window._dictionary.update_cfg(self._cfg)
            except Exception:
                pass
            preview = ", ".join(f"“{w}”" for w in new_words[:3])
            extra = f"  + {len(new_words) - 3} more" if len(new_words) > 3 else ""
            self._overlay_toast.show_message("Learned", f"{preview}{extra}")
            sound.play_learned()
        elif _correction_added_content(original, corrected):
            # Real substitution / addition that didn't yield a new dictionary
            # term (lowercase words, punctuation, etc) - still worth a quiet
            # "Saved" so the user knows the edit was captured.
            self._overlay_toast.show_message("Saved", "Your correction")
            sound.play_learned()
        # Pure deletions / whitespace edits get no toast - Murmur shouldn't
        # celebrate every backspace.

    # ---- quit --------------------------------------------------------------

    def _quit(self) -> None:
        self._hotkey.stop()
        self._level_timer.stop()
        self._overlay.hide_overlay()
        try:
            self._overlay_toast.hide()
        except Exception:
            pass
        try:
            self._correction_watcher.cancel()
        except Exception:
            pass
        try:
            self._window.hide()
        except Exception:
            pass
        self._worker_thread.quit()
        self._worker_thread.wait(2000)
        self._app.quit()


class _NoScrollFilter(QObject):
    """Swallow mouse-wheel events on closed comboboxes and spin boxes.

    Without this, scrolling the page over a QComboBox unintentionally changes
    its value. With the filter, the wheel only adjusts the value while the
    user has actually opened the dropdown (the popup is a separate widget,
    not affected here)."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(
            obj, (QComboBox, QAbstractSpinBox)
        ):
            event.ignore()
            return True
        return False


def _register_app_id() -> None:
    """Tell Windows our AppUserModelID so toasts say 'Murmur' instead of 'Python'."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Murmur.Dictation")
    except Exception:
        pass


def main() -> int:
    show_on_start = "--show" in sys.argv

    # If another Murmur is already running, hand the request to it and exit.
    # The running instance will pop its window (if --show) or just ack.
    if _signal_running_instance("show" if show_on_start else "ping"):
        print("[main] handed off to existing Murmur instance; exiting.")
        return 0

    _register_app_id()
    QApplication.setApplicationName("Murmur")
    QApplication.setApplicationDisplayName("Murmur")
    QApplication.setOrganizationName("Murmur")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    from ui.window import make_app_icon
    app.setWindowIcon(make_app_icon())

    app._no_scroll_filter = _NoScrollFilter(app)
    app.installEventFilter(app._no_scroll_filter)

    ctrl = Controller(app)

    # Listen for "show" messages from later Murmur invocations (desktop shortcut).
    QLocalServer.removeServer(_IPC_PIPE)  # clean up stale socket file
    app._ipc_server = QLocalServer()
    if not app._ipc_server.listen(_IPC_PIPE):
        print(f"[main] IPC server failed to bind: {app._ipc_server.errorString()}")

    def _on_ipc_connection():
        sock = app._ipc_server.nextPendingConnection()
        if sock is None:
            return
        if sock.waitForReadyRead(400):
            msg = bytes(sock.readAll()).decode("utf-8", errors="replace").strip()
            print(f"[main] IPC message: {msg!r}")
            if msg == "show":
                ctrl._open_window()
        sock.disconnectFromServer()
        sock.deleteLater()

    app._ipc_server.newConnection.connect(_on_ipc_connection)

    if show_on_start:
        ctrl._open_window()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
