"""faster-whisper wrapper with lazy load, GPU auto-detection, and CPU fallback.

If ctranslate2 reports a CUDA device but the CUDA runtime DLLs (cuBLAS, cuDNN)
are missing or broken, we transparently fall back to CPU. This is common on
Windows machines that have an NVIDIA GPU but no CUDA Toolkit installed.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np


def _register_nvidia_dll_dirs() -> None:
    """Make Windows pick up the cuBLAS / cuDNN / NVRTC DLLs that ship via the
    `nvidia-*-cu12` pip packages.

    Those wheels drop their DLLs under site-packages/nvidia/<pkg>/bin/, but
    Windows doesn't auto-search there. Without this, ctranslate2 reports
    'cublas64_12.dll not found' even though the file exists on disk."""
    if sys.platform != "win32":
        return
    try:
        import site
        candidates = list(site.getsitepackages())
        try:
            candidates.append(site.getusersitepackages())
        except Exception:
            pass
        # Also probe Python install prefix Lib/site-packages directly.
        candidates.append(str(Path(sys.prefix) / "Lib" / "site-packages"))
        seen: set[str] = set()
        added: list[str] = []
        for site_dir in candidates:
            nvidia_root = Path(site_dir) / "nvidia"
            if not nvidia_root.is_dir():
                continue
            for pkg in nvidia_root.iterdir():
                bin_dir = pkg / "bin"
                if bin_dir.is_dir() and str(bin_dir) not in seen:
                    seen.add(str(bin_dir))
                    os.add_dll_directory(str(bin_dir))
                    # Also prepend to PATH - belt-and-suspenders since some
                    # loaders (CUDA's own loader inside libs) read PATH not
                    # the AddDllDirectory list.
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                    added.append(str(bin_dir))
        print(f"[transcribe] registered {len(added)} nvidia DLL dir(s):")
        for d in added:
            print(f"  + {d}")
    except Exception as exc:
        print(f"[transcribe] couldn't register nvidia DLL dirs: {exc}")


_register_nvidia_dll_dirs()

try:
    import ctranslate2
    _CUDA_DEVICE_COUNT = ctranslate2.get_cuda_device_count()
except Exception:
    _CUDA_DEVICE_COUNT = 0


# Whisper's training data includes massive amounts of YouTube and podcast
# content, so under uncertainty it falls back to these stock phrases verbatim.
# When we see one of these and nothing else, the audio was unintelligible
# noise - never paste it.
_HALLUCINATION_PHRASES = frozenset({
    "thank you.",
    "thank you",
    "thank you so much.",
    "thank you so much",
    "thanks for watching.",
    "thanks for watching",
    "thanks for watching!",
    "thank you for watching.",
    "thank you for watching",
    "the world is changing.",
    "the world is changing",
    "please subscribe.",
    "please subscribe",
    "subscribe to my channel.",
    "see you next time.",
    "see you in the next video.",
    "bye.",
    "bye!",
    "yup.",
    "yup",
    "yup, yup, yup.",
    "you",
    "you.",
    "ok.",
    "ok",
    ".",
    "music",
    "[music]",
    "♪",
})


def _is_hallucination(text: str) -> bool:
    """Match Whisper's well-known fallback phrases. Conservative: only blocks
    the literal stock outputs, never real user transcripts."""
    if not text:
        return False
    norm = text.strip().lower().rstrip("!?,. ").strip()
    if norm in _HALLUCINATION_PHRASES:
        return True
    if (text + ".").lower().strip() in _HALLUCINATION_PHRASES:
        return True
    # Very short outputs (<=2 words) that match the blocklist by prefix
    if len(norm.split()) <= 3 and any(
        norm == p.rstrip(".") or norm == p for p in _HALLUCINATION_PHRASES
    ):
        return True
    return False


class Transcriber:
    def __init__(self, model_size: str = "small.en"):
        self.model_size = model_size
        self._model = None
        self._device = "cpu"
        self._lock = threading.Lock()

    def _try_load(self, device: str, compute_type: str):
        from faster_whisper import WhisperModel

        print(f"[transcribe] loading {self.model_size} on {device} ({compute_type})...")
        model = WhisperModel(self.model_size, device=device, compute_type=compute_type)

        # Force the runtime to actually load CUDA libs (cuBLAS/cuDNN) by running
        # a tiny inference. If DLLs are missing, this is where it will raise.
        probe = np.zeros(1600, dtype=np.float32)  # 0.1s of silence
        segments, _ = model.transcribe(probe, beam_size=1, vad_filter=False)
        _ = list(segments)
        return model

    def _load(self) -> None:
        if _CUDA_DEVICE_COUNT > 0:
            try:
                self._model = self._try_load("cuda", "float16")
                self._device = "cuda"
                print(f"[transcribe] model ready (cuda)")
                return
            except Exception as exc:
                print(f"[transcribe] CUDA load failed: {exc}")
                print(f"[transcribe] falling back to CPU (install CUDA 12.x + cuDNN for GPU speed)")
                self._model = None

        self._model = self._try_load("cpu", "int8")
        self._device = "cpu"
        print(f"[transcribe] model ready (cpu)")

    def ensure_loaded(self) -> None:
        with self._lock:
            if self._model is None:
                self._load()

    def transcribe(
        self,
        audio: np.ndarray,
        initial_prompt: Optional[str] = None,
        vad_threshold: float = 0.5,
        use_vad: bool = True,
    ) -> str:
        if audio.size == 0:
            return ""

        self.ensure_loaded()

        kwargs = dict(
            beam_size=5,
            vad_filter=use_vad,
            vad_parameters={
                "min_silence_duration_ms": 300,
                "threshold": vad_threshold,
            },
            # Anti-hallucination guards. Whisper is famous for inventing
            # YouTube-style filler ("Okay, here we go.", "Thanks for watching")
            # when audio is short, quiet, or ambiguous. These tighten the
            # cutoffs so the model returns nothing instead of fabricating,
            # but if they're too aggressive on a quiet mic, every recording
            # comes back empty. The current values are tuned for typical
            # laptop-array audio (peak ~0.15 after normalisation) - looser
            # than the old defaults but still firmly anti-hallucination.
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.2,
            log_prob_threshold=-1.0,
            temperature=0.0,
        )
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        segments, info = self._model.transcribe(audio, **kwargs)
        seg_list = list(segments)
        text = "".join(seg.text for seg in seg_list).strip()
        # Surface what Whisper actually thought of the audio so empty results
        # are explainable instead of mysterious.
        try:
            print(
                f"[transcribe] segments={len(seg_list)} "
                f"lang={info.language} lang_prob={info.language_probability:.2f} "
                f"duration={info.duration:.2f}s "
                f"duration_after_vad={info.duration_after_vad:.2f}s"
            )
        except Exception:
            pass
        if _is_hallucination(text):
            print(f"[transcribe] BLOCKED hallucination: {text!r}")
            return ""
        return text


if __name__ == "__main__":
    import time

    from audio import SAMPLE_RATE, Recorder

    t = Transcriber()
    t.ensure_loaded()

    print("Recording 4 seconds... say something.")
    r = Recorder()
    r.start()
    time.sleep(4)
    audio = r.stop()
    print(f"Got {len(audio) / SAMPLE_RATE:.2f}s of audio. Transcribing...")
    start = time.time()
    text = t.transcribe(audio)
    elapsed = time.time() - start
    print(f"\nTranscript ({elapsed:.2f}s): {text!r}")
