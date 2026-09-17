"""AI polishing via Groq's free tier (Llama 3.3 70B).

Whisper output is already clean, but polishing fixes light punctuation, removes
filler words, and can shift tone per the user's chosen persona.

Designed to fail soft: missing API key, no network, rate limit, malformed
response - any of these return the raw text unchanged. Polishing never blocks
the dictation loop.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib import error as urlerror
from urllib import request as urlrequest


_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT_S = 8.0


@dataclass(frozen=True)
class Persona:
    key: str
    label: str
    description: str
    system_prompt: str


PERSONA_RAW = Persona(
    key="raw",
    label="Raw",
    description="No polishing. Use Whisper's output verbatim.",
    system_prompt="",
)

PERSONA_CASUAL = Persona(
    key="casual",
    label="Casual",
    description="Light cleanup. Friendly, contractions, natural rhythm.",
    system_prompt=(
        "You are a transcription cleaner. Rewrite the user's dictated text "
        "with correct punctuation, capitalization, and spelling. Keep the "
        "tone casual and conversational — use contractions, keep it short. "
        "Remove filler words (um, uh, like, you know). Do not add new "
        "content, do not summarize, do not change meaning. Reply with only "
        "the cleaned text, nothing else."
    ),
)

PERSONA_PROFESSIONAL = Persona(
    key="professional",
    label="Professional",
    description="Polished prose for work messages and docs.",
    system_prompt=(
        "You are a transcription cleaner. Rewrite the user's dictated text "
        "as polished, professional prose. Fix punctuation, capitalization, "
        "and spelling. Use complete sentences, no contractions where "
        "avoidable. Remove filler words. Do not add new content, do not "
        "summarize, do not change meaning. Reply with only the cleaned "
        "text, nothing else."
    ),
)

PERSONA_EMAIL = Persona(
    key="email",
    label="Email",
    description="Formats as a short, well-structured email body.",
    system_prompt=(
        "You are a transcription cleaner. Rewrite the user's dictated text "
        "as a short, well-structured email body. Fix punctuation, "
        "capitalization, and spelling. Use clear paragraph breaks where "
        "natural. Polite but concise. Do not invent greetings or sign-offs "
        "unless the user dictated them. Do not add new content beyond what "
        "was said. Reply with only the email body text, nothing else."
    ),
)

PERSONAS: dict[str, Persona] = {
    p.key: p for p in (PERSONA_RAW, PERSONA_CASUAL, PERSONA_PROFESSIONAL, PERSONA_EMAIL)
}


def get_persona(key: str) -> Persona:
    return PERSONAS.get(key, PERSONA_RAW)


class PolishError(Exception):
    pass


def _post_groq(api_key: str, system_prompt: str, user_text: str) -> str:
    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    req = urlrequest.Request(
        _GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Cloudflare in front of api.groq.com blocks requests without a
            # real-looking UA (returns 403 / error 1010 "browser ID banned").
            "User-Agent": "Murmur/0.1 (https://github.com/local; python-urllib)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8")
    except urlerror.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise PolishError(f"groq http {e.code}: {detail}") from e
    except urlerror.URLError as e:
        raise PolishError(f"groq network: {e.reason}") from e
    except Exception as e:
        raise PolishError(f"groq error: {e}") from e

    try:
        data = json.loads(body)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise PolishError(f"groq malformed response: {e}") from e

    return content.strip()


def polish(
    text: str,
    *,
    persona_key: str,
    api_key: Optional[str],
    enabled: bool,
) -> tuple[str, bool]:
    """Return (polished_text, was_polished).

    Fails soft: any error returns the raw text with was_polished=False.
    """
    text = text.strip()
    if not text:
        return text, False

    if not enabled:
        return text, False

    persona = get_persona(persona_key)
    if persona.key == "raw" or not persona.system_prompt:
        return text, False

    if not api_key:
        return text, False

    try:
        cleaned = _post_groq(api_key, persona.system_prompt, text)
    except PolishError as exc:
        print(f"[polish] failed: {exc} — using raw text")
        return text, False

    if not cleaned:
        return text, False
    return cleaned, True


# ---- standalone smoke test ------------------------------------------------

if __name__ == "__main__":
    import os
    import sys

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        print("Set GROQ_API_KEY in the environment to test live.")
        # Still exercise the no-key path:
        out, ok = polish("hello world this is a test", persona_key="casual",
                         api_key=None, enabled=True)
        print(f"No-key path -> ok={ok} text={out!r}")
        sys.exit(0)

    sample = "um so yeah i was thinking we should maybe like ship the feature on friday"
    for k in ("casual", "professional", "email"):
        out, ok = polish(sample, persona_key=k, api_key=key, enabled=True)
        print(f"--- {k} (ok={ok}) ---")
        print(out)
        print()
