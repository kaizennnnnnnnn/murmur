"""Mic capture: 16 kHz mono float32 PCM via sounddevice.

Whisper expects exactly this format, so we record natively at 16 kHz to skip resampling.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "float32"


# A sensitivity profile controls how much of the recording survives the
# voice-activity filter: the silero-VAD threshold, where lower is more
# permissive so quieter speech still reaches the model, and whether silero
# runs at all. Level is deliberately not part of it. main.py high-passes and
# peak-normalises every recording to 0.8 whatever the profile says, which
# lifts a quiet microphone considerably more than the old fixed per-profile
# gain did; that gain was removed because it was causing hallucinations.
SENSITIVITY_PROFILES: dict[str, dict] = {
    "normal":    {"vad_threshold": 0.4, "use_vad": True},
    "sensitive": {"vad_threshold": 0.3, "use_vad": True},
    # Silero is switched off here on purpose. Once normalisation has lifted
    # speech and background noise to the same loudness, silero sees only the
    # resulting wash and rejects all of it as non-speech. Whisper's own
    # no-speech detection still catches genuine silence.
    "whisper":   {"vad_threshold": 0.1, "use_vad": False},
}


def get_sensitivity(name: str) -> dict:
    return SENSITIVITY_PROFILES.get(name, SENSITIVITY_PROFILES["normal"])


def normalize_peak(audio: np.ndarray, target: float = 0.9) -> np.ndarray:
    """Rescale so the loudest sample sits at `target`. Skips dead-silent
    buffers so we don't amplify pure noise to full scale."""
    if audio.size == 0:
        return audio
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-4:
        return audio
    return audio * (target / peak)


_HP_SOS = None


def high_pass(audio: np.ndarray, cutoff_hz: int = 100) -> np.ndarray:
    """Strip low-frequency rumble (laptop fan, HVAC, table thumps) before
    transcription. Cutoff is 100 Hz - below the lowest male voice
    fundamental (~85 Hz) so the voice body stays intact, while still
    knocking down the 20-80 Hz HVAC band that's pure noise."""
    if audio.size == 0:
        return audio
    global _HP_SOS
    if _HP_SOS is None:
        from scipy.signal import butter
        _HP_SOS = butter(4, cutoff_hz, btype="high", fs=SAMPLE_RATE, output="sos")
    from scipy.signal import sosfilt
    return sosfilt(_HP_SOS, audio).astype(np.float32)


class Recorder:
    def __init__(self, device: Optional[int] = None):
        self.device = device
        self._stream: Optional[sd.InputStream] = None
        self._chunks: "queue.Queue[np.ndarray]" = queue.Queue()
        self._lock = threading.Lock()
        self._recording = False
        self._latest_level = 0.0  # RMS of most recent chunk; read from any thread
        self._stream_sr = SAMPLE_RATE  # actual stream rate (set at start time)

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio] status: {status}")
        flat = indata.reshape(-1)
        self._chunks.put(flat.copy())
        # Atomic float write - safe to read from the Qt thread without a lock.
        self._latest_level = float(np.sqrt(np.mean(flat ** 2)))

    @property
    def level(self) -> float:
        return self._latest_level

    def _pick_samplerate(self) -> int:
        """Find a sample rate the device will accept. Whisper wants 16 kHz,
        but many WASAPI/WDM-KS devices are fixed at 44.1 or 48 kHz - we
        record at the device's preferred rate and resample on the way out."""
        candidates = [SAMPLE_RATE]
        try:
            info = sd.query_devices(self.device)
            default_sr = int(info.get("default_samplerate") or 0)
            if default_sr and default_sr not in candidates:
                candidates.append(default_sr)
        except Exception:
            pass
        # Common fallbacks Windows mics actually support.
        for sr in (48000, 44100, 32000, 22050):
            if sr not in candidates:
                candidates.append(sr)
        for sr in candidates:
            try:
                sd.check_input_settings(
                    device=self.device, samplerate=sr,
                    channels=CHANNELS, dtype=DTYPE,
                )
                return sr
            except Exception:
                continue
        # Last resort - let PortAudio pick whatever the device wants.
        return SAMPLE_RATE

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            while not self._chunks.empty():
                self._chunks.get_nowait()
            self._latest_level = 0.0
            self._stream_sr = self._pick_samplerate()
            if self._stream_sr != SAMPLE_RATE:
                print(f"[audio] device doesn't support {SAMPLE_RATE}Hz; "
                      f"recording at {self._stream_sr}Hz and resampling")
            self._stream = sd.InputStream(
                samplerate=self._stream_sr,
                channels=CHANNELS,
                dtype=DTYPE,
                device=self.device,
                callback=self._callback,
                blocksize=1024,
            )
            self._stream.start()
            self._recording = True

    def stop(self) -> np.ndarray:
        with self._lock:
            if not self._recording or self._stream is None:
                return np.zeros(0, dtype=np.float32)
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._recording = False
            stream_sr = self._stream_sr

        parts = []
        while not self._chunks.empty():
            parts.append(self._chunks.get_nowait())
        if not parts:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(parts).astype(np.float32)
        # Resample if the device wasn't running at Whisper's native rate.
        if stream_sr != SAMPLE_RATE and audio.size:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(SAMPLE_RATE, stream_sr)
            up = SAMPLE_RATE // g
            down = stream_sr // g
            audio = resample_poly(audio, up, down).astype(np.float32)
        return audio

    @property
    def is_recording(self) -> bool:
        return self._recording


def list_input_devices() -> list[dict]:
    devices = sd.query_devices()
    return [
        {"index": i, "name": d["name"], "channels": d["max_input_channels"]}
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]


if __name__ == "__main__":
    import time

    print("Input devices:")
    for d in list_input_devices():
        print(f"  [{d['index']}] {d['name']} ({d['channels']} ch)")

    print("\nRecording 3 seconds from default device...")
    r = Recorder()
    r.start()
    time.sleep(3)
    audio = r.stop()
    duration = len(audio) / SAMPLE_RATE
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    print(f"Captured {len(audio)} samples ({duration:.2f}s), peak={peak:.3f}")
