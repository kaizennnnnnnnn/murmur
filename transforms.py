"""Text transforms - clipboard text in, AI-rewritten text out.

Each transform is just a system prompt that gets paired with the user's
text and sent to Groq. Reuses the existing polish.py infrastructure for
the HTTP call so we don't duplicate retry / fallback handling.
"""
from __future__ import annotations

from typing import Optional

from polish import PolishError, _post_groq


DEFAULT_TRANSFORMS: list[dict[str, str]] = [
    {
        "name": "Shorten",
        "description": "Cut it down without losing meaning.",
        "prompt": (
            "Rewrite the user's text to be significantly shorter while "
            "preserving the meaning, tone, and key information. Aim for "
            "60-80% of the original length. Reply with only the rewritten "
            "text, nothing else."
        ),
    },
    {
        "name": "Make formal",
        "description": "Professional tone — for work and emails.",
        "prompt": (
            "Rewrite the user's text in a more formal, professional tone "
            "suitable for work emails or business communication. Keep the "
            "meaning intact. Reply with only the rewritten text."
        ),
    },
    {
        "name": "Make casual",
        "description": "Friendly tone — for messages and chat.",
        "prompt": (
            "Rewrite the user's text in a casual, friendly tone — like a "
            "quick message to a colleague. Use contractions, keep it warm. "
            "Reply with only the rewritten text."
        ),
    },
    {
        "name": "Fix grammar",
        "description": "Clean up errors without changing tone.",
        "prompt": (
            "Fix any grammar, spelling, and punctuation errors in the "
            "user's text without changing the meaning, tone, or style. "
            "Reply with only the corrected text."
        ),
    },
    {
        "name": "Expand",
        "description": "Add detail and supporting context.",
        "prompt": (
            "Expand the user's text with additional detail and supporting "
            "context, while keeping the original tone and intent. Reply "
            "with only the expanded text."
        ),
    },
    {
        "name": "As bullets",
        "description": "Rewrite as a bulleted list of key points.",
        "prompt": (
            "Rewrite the user's text as a concise bulleted list of the "
            "key points. Use '- ' for each bullet. Reply with only the "
            "bullet list."
        ),
    },
]


def apply(text: str, prompt: str, api_key: Optional[str]) -> tuple[str, bool]:
    """Returns (result, ok). On any failure returns (text, False)."""
    text = text.strip()
    if not text:
        return text, False
    if not api_key:
        return text, False
    try:
        cleaned = _post_groq(api_key, prompt, text)
    except PolishError as exc:
        print(f"[transforms] failed: {exc}")
        return text, False
    if not cleaned:
        return text, False
    return cleaned, True
