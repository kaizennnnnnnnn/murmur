"""Snippet expansion - substitute short triggers with their stored expansions.

Applied to the transcript after AI polish (if any) and right before the
text is pasted at the cursor. Match is case-insensitive but only on whole
words, so a trigger 'sig' inside 'design' is left alone.
"""
from __future__ import annotations

import re
from typing import Mapping


def expand(text: str, snippets: Mapping[str, str]) -> str:
    if not snippets or not text:
        return text
    out = text
    for trigger, expansion in snippets.items():
        if not trigger:
            continue
        pattern = r'\b' + re.escape(trigger) + r'\b'
        out = re.sub(pattern, expansion, out, flags=re.IGNORECASE)
    return out
