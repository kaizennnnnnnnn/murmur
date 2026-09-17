"""Groq cloud transcription - Whisper Large v3 Turbo.

Used as a fallback when local `small.en` fails (returns empty on quiet
audio) and also as the primary path when the user's mic just doesn't
capture loud-enough signal for the local model.

Why Groq and not the OpenAI Whisper API?
  - Free generous tier already required for the polish feature
  - Whisper Large v3 Turbo is the strongest STT in their lineup, MUCH
    more robust to quiet/noisy audio than local small.en
  - Single endpoint, simple multipart POST, no SDK needed
"""
from __future__ import annotations

import io
import json
import urllib.request
import urllib.error
import uuid
import wave
from typing import Optional

import numpy as np


GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = "whisper-large-v3-turbo"


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16_000) -> bytes:
    """Pack a mono float32 numpy array into a 16-bit PCM WAV in memory."""
    buf = io.BytesIO()
    samples = np.clip(audio, -1.0, 1.0)
    int16 = (samples * 32767.0).astype(np.int16)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(int16.tobytes())
    return buf.getvalue()


def _build_multipart(wav_bytes: bytes, model: str, prompt: Optional[str]) -> tuple[bytes, str]:
    """Hand-roll the multipart/form-data body so we don't need `requests`."""
    boundary = f"----murmur{uuid.uuid4().hex}"
    crlf = "\r\n"
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.append(
            f"--{boundary}{crlf}"
            f'Content-Disposition: form-data; name="{name}"{crlf}{crlf}'
            f"{value}{crlf}".encode("utf-8")
        )

    field("model", model)
    field("response_format", "json")
    field("language", "en")
    if prompt:
        field("prompt", prompt)

    parts.append(
        f"--{boundary}{crlf}"
        f'Content-Disposition: form-data; name="file"; filename="audio.wav"{crlf}'
        f"Content-Type: audio/wav{crlf}{crlf}".encode("utf-8")
    )
    parts.append(wav_bytes)
    parts.append(f"{crlf}--{boundary}--{crlf}".encode("utf-8"))

    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def groq_transcribe(
    audio: np.ndarray,
    api_key: str,
    *,
    initial_prompt: Optional[str] = None,
    timeout_s: int = 20,
) -> str:
    """POST the audio to Groq's Whisper endpoint and return the text.

    Returns empty string on any failure - callers should fall through to
    whatever they had before instead of crashing the dictation flow."""
    if not api_key or audio.size == 0:
        return ""

    try:
        wav_bytes = _audio_to_wav_bytes(audio)
        body, content_type = _build_multipart(wav_bytes, GROQ_STT_MODEL, initial_prompt)
        req = urllib.request.Request(
            GROQ_STT_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": content_type,
                # Cloudflare rejects requests without a UA (returns 1010).
                "User-Agent": "Murmur/0.1 (https://github.com/local; python-urllib)",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            text = (payload.get("text") or "").strip()
            print(f"[groq-stt] {len(wav_bytes)} bytes -> {text!r}")
            return text
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<no body>"
        print(f"[groq-stt] HTTP {exc.code}: {body[:200]}")
        return ""
    except Exception as exc:
        print(f"[groq-stt] failed: {exc}")
        return ""
