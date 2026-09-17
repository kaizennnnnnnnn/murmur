"""Murmur dictation history - SQLite at %APPDATA%\\Murmur\\history.db.

Every successful dictation gets a row. Insights and the Voice Profile card on
Home read from this. Pure stdlib - no extra deps.
"""
from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional


def _db_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Murmur" / "history.db"


DB_PATH = _db_path()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    duration_s  REAL    NOT NULL,
    word_count  INTEGER NOT NULL,
    polished    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_transcripts_ts ON transcripts(ts);
"""


# Conservative English stopword set - kept small on purpose so the user's
# actual vocabulary still surfaces as their "favorite word".
_STOPWORDS = frozenset("""
a an and the of to in on at for with from by is am are was were be been being
have has had do does did will would shall should can could may might must
i you he she it we they me him her us them my your his its our their this
that these those there here what which who whom whose when where why how
not no nor so if then than as but or yet just only also too very really
ok okay yeah yep nope um uh er hm well like get got go going gonna
""".split())


_WORD_RE = re.compile(r"[A-Za-z']+")


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _content_tokens(text: str) -> list[str]:
    return [w for w in _tokens(text) if w not in _STOPWORDS and len(w) > 1]


def _ngrams(tokens: list[str], n: int) -> Iterable[tuple[str, ...]]:
    for i in range(len(tokens) - n + 1):
        yield tuple(tokens[i : i + n])


# ---- connection -----------------------------------------------------------

_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


# ---- writes ---------------------------------------------------------------

def add(text: str, duration_s: float, polished: bool = False) -> int:
    """Insert a transcript row. Returns the new row id."""
    text = text.strip()
    if not text:
        return -1
    wc = len(_tokens(text))
    ts = datetime.now().isoformat(timespec="seconds")
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO transcripts (ts, text, duration_s, word_count, polished) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts, text, float(duration_s), wc, 1 if polished else 0),
    )
    conn.commit()
    return cur.lastrowid


def delete(row_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM transcripts WHERE id = ?", (row_id,))
    conn.commit()


def update_text(row_id: int, new_text: str) -> None:
    """Replace a transcript's text after the user corrects it. Word count
    is recomputed so Insights numbers stay honest."""
    new_text = new_text.strip()
    if not new_text:
        return
    wc = len(_tokens(new_text))
    conn = _connect()
    conn.execute(
        "UPDATE transcripts SET text = ?, word_count = ? WHERE id = ?",
        (new_text, wc, row_id),
    )
    conn.commit()


def extract_new_words(
    original: str,
    corrected: str,
    *,
    existing: set[str] | None = None,
) -> list[str]:
    """Proper-noun-style words appearing in `corrected` that weren't in
    `original`.

    Used after the user edits a transcript: any *proper noun* they typed in
    is a candidate to bias Whisper toward next time. Common English words
    are NEVER added - Whisper already knows them, and stuffing the prompt
    with everyday words actively poisons future transcriptions (Whisper
    will sometimes just echo the prompt back instead of transcribing).

    Acceptance gate (a word must pass all):
      - starts with an uppercase letter (proper-noun convention)
      - is NOT the first word of the correction (sentence-initial caps
        aren't reliable proper-noun signals)
      - is at least 3 characters
      - not in the stopword list
      - not already in the user's dictionary (case-insensitive)
      - didn't appear in the original transcription"""
    existing_lower = {w.lower() for w in (existing or set())}
    orig_tokens = {t.lower() for t in _tokens(original)}

    matches = list(_WORD_RE.finditer(corrected))
    if not matches:
        return []
    first_word_lower = matches[0].group(0).lower()

    new_words: list[str] = []
    seen_lower: set[str] = set()
    for m in matches:
        raw = m.group(0)
        lower = raw.lower()
        # Proper-noun gate
        if not raw[:1].isupper():
            continue
        # Skip the sentence-initial capital (could be any common word)
        if lower == first_word_lower and m.start() == matches[0].start():
            continue
        if (
            len(lower) < 3
            or lower in orig_tokens
            or lower in _STOPWORDS
            or lower in existing_lower
            or lower in seen_lower
        ):
            continue
        seen_lower.add(lower)
        new_words.append(raw)
    return new_words


# ---- reads ----------------------------------------------------------------

@dataclass(frozen=True)
class Transcript:
    id: int
    ts: datetime
    text: str
    duration_s: float
    word_count: int
    polished: bool


def _row_to_transcript(row: sqlite3.Row) -> Transcript:
    return Transcript(
        id=row["id"],
        ts=datetime.fromisoformat(row["ts"]),
        text=row["text"],
        duration_s=row["duration_s"],
        word_count=row["word_count"],
        polished=bool(row["polished"]),
    )


def recent(limit: int = 200) -> list[Transcript]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM transcripts ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_transcript(r) for r in rows]


def all_transcripts() -> list[Transcript]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM transcripts ORDER BY ts ASC").fetchall()
    return [_row_to_transcript(r) for r in rows]


# ---- stats (Insights page) ------------------------------------------------

@dataclass(frozen=True)
class Stats:
    total_words: int
    total_dictations: int
    total_seconds: float
    avg_wpm: float
    day_streak: int


def stats() -> Stats:
    conn = _connect()
    row = conn.execute(
        "SELECT COALESCE(SUM(word_count), 0) AS w, "
        "       COUNT(*) AS n, "
        "       COALESCE(SUM(duration_s), 0) AS s "
        "FROM transcripts"
    ).fetchone()
    total_words = int(row["w"])
    total_dictations = int(row["n"])
    total_seconds = float(row["s"])
    avg_wpm = (total_words / total_seconds * 60.0) if total_seconds > 0 else 0.0

    # Day streak: walk back from today while each day has at least one row.
    streak = 0
    today = date.today()
    for i in range(0, 3650):  # cap at 10 years
        d = today - timedelta(days=i)
        start = datetime(d.year, d.month, d.day).isoformat()
        end = (datetime(d.year, d.month, d.day) + timedelta(days=1)).isoformat()
        hit = conn.execute(
            "SELECT 1 FROM transcripts WHERE ts >= ? AND ts < ? LIMIT 1",
            (start, end),
        ).fetchone()
        if hit:
            streak += 1
        else:
            # If today is empty, the streak is whatever the previous days had.
            if i == 0:
                continue
            break
    return Stats(total_words, total_dictations, total_seconds, avg_wpm, streak)


# ---- Voice Profile --------------------------------------------------------

@dataclass(frozen=True)
class VoiceProfile:
    favorite_word: Optional[str]
    favorite_word_count: int
    top_phrases: list[tuple[str, int]]   # [(phrase, count), ...]
    active_hour: Optional[int]            # 0..23
    vocab_size: int


def _format_hour(h: Optional[int]) -> str:
    if h is None:
        return "—"
    if h == 0:
        return "12 AM"
    if h == 12:
        return "12 PM"
    if h < 12:
        return f"{h} AM"
    return f"{h - 12} PM"


def format_active_hour(h: Optional[int]) -> str:
    return _format_hour(h)


def voice_type(s: "Stats", p: "VoiceProfile") -> tuple[str, str]:
    """A short, characteristic label for the user's voice habits + a one-line
    description. Used as the right-rail teaser. Mirrors how Wispr labels a
    profile ('Visual Critique' etc.) - except ours is computed locally from
    the user's actual dictation history."""
    if s.total_dictations < 3:
        return ("Just getting started",
                "Your voice profile takes shape as you dictate.")

    avg_words = s.total_words / s.total_dictations if s.total_dictations else 0

    if s.day_streak >= 7:
        return ("Daily Devotee",
                f"{s.day_streak} days dictating in a row.")
    if s.avg_wpm >= 140:
        return ("Quick Speaker",
                f"averaging {int(round(s.avg_wpm))} words per minute.")
    if avg_words > 35:
        return ("The Storyteller",
                "you go long — detailed, layered dictations.")
    if avg_words < 7:
        return ("Quick & Concise",
                "short, punchy dictations.")
    if p.vocab_size >= 250 and s.total_dictations < 80:
        return ("Word Collector",
                f"{p.vocab_size} unique words and growing.")
    if p.active_hour is not None:
        if 5 <= p.active_hour < 10:
            return ("Early Riser",
                    f"most active around {_format_hour(p.active_hour)}.")
        if p.active_hour >= 21 or p.active_hour < 4:
            return ("Night Owl",
                    f"most active around {_format_hour(p.active_hour)}.")
    if p.favorite_word:
        return ("Steady Speaker",
                f"a rhythm forming — \"{p.favorite_word}\" keeps coming up.")
    return ("Steady Speaker",
            f"{s.total_dictations} dictations and counting.")


def profile() -> VoiceProfile:
    conn = _connect()
    rows = conn.execute("SELECT text, ts FROM transcripts").fetchall()

    all_toks: list[str] = []
    content_toks_per_row: list[list[str]] = []
    hour_counts: Counter[int] = Counter()

    for r in rows:
        toks = _tokens(r["text"])
        all_toks.extend(toks)
        content_toks_per_row.append(_content_tokens(r["text"]))
        try:
            hour_counts[datetime.fromisoformat(r["ts"]).hour] += 1
        except ValueError:
            pass

    content_flat = [t for row in content_toks_per_row for t in row]
    word_counter = Counter(content_flat)
    fav = word_counter.most_common(1)
    favorite_word, favorite_count = (fav[0] if fav else (None, 0))

    # N-grams: compute on the content-token rows so we never get
    # "of the" / "and the" style phrases. Use 2-grams primarily, then
    # fall in 3-grams to round out top 3.
    phrase_counter: Counter[tuple[str, ...]] = Counter()
    for toks in content_toks_per_row:
        for n in (2, 3):
            for ng in _ngrams(toks, n):
                phrase_counter[ng] += 1
    top = [
        (" ".join(ng), c)
        for ng, c in phrase_counter.most_common(20)
        if c >= 2
    ][:3]

    active_hour = hour_counts.most_common(1)[0][0] if hour_counts else None
    vocab_size = len({t for t in all_toks if len(t) > 1})

    return VoiceProfile(
        favorite_word=favorite_word,
        favorite_word_count=favorite_count,
        top_phrases=top,
        active_hour=active_hour,
        vocab_size=vocab_size,
    )


# ---- standalone smoke test ------------------------------------------------

if __name__ == "__main__":
    print(f"DB path: {DB_PATH}")
    _connect()
    s = stats()
    print(f"Stats: {s}")
    p = profile()
    print(f"Profile: favorite={p.favorite_word!r} ({p.favorite_word_count}x), "
          f"phrases={p.top_phrases}, hour={_format_hour(p.active_hour)}, "
          f"vocab={p.vocab_size}")
    rs = recent(5)
    print(f"Recent {len(rs)}:")
    for r in rs:
        print(f"  {r.ts}  ({r.duration_s:.1f}s, {r.word_count}w) {r.text[:60]!r}")
