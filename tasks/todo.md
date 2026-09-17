# Murmur Desktop App — v1 Plan

> **Historical.** This is the original v1 plan, kept as a record of how the
> app was scoped before it was built. It is out of date: the three sections
> marked "later" below (Dictionary, Snippets, Transforms) all shipped.
> See the README for what Murmur actually does today.

## Locked decisions
- **AI polish:** Groq free tier, Llama 3.3 70B (online, free, no card)
- **Open window:** tray double-click **and** a new "Open Murmur" menu item
- **Close (X):** minimize to tray; only "Quit" in tray menu actually exits
- **Hero card:** kept, Murmur copy ("Hold Ctrl + Win to dictate…")
- **Theme:** light/cream to match reference; serif headings, sans body

## Scope — v1
| Section | Status | Notes |
|---|---|---|
| Home (hero + transcript feed) | ✅ build | Grouped by day, copy-on-click |
| Insights (stats) | ✅ build | Total words, wpm, streak |
| Scratchpad | ✅ build | Autosaved `QTextEdit` |
| Style (AI personas) | ✅ build | Switches polish prompt |
| Settings (embedded) | ✅ build | Replaces the old dialog |
| Dictionary | ⏸ later | Needs whisper prompt wiring |
| Snippets | ⏸ later | Trigger → expansion engine |
| Transforms | ⏸ later | Cross-app text rewrite |

## File plan
**New**
- `history.py` — SQLite at `%APPDATA%\Murmur\history.db` (`id, ts, text, duration_s, word_count`)
- `polish.py` — Groq client + persona prompts (Casual / Professional / Email / Raw)
- `ui/window.py` — `QMainWindow` shell: sidebar | stacked content | right rail
- `ui/theme.py` — light stylesheet (cream `#FAFAF7`, black hero, Georgia headings, Segoe UI body)
- `ui/pages/home.py` — hero card + day-grouped transcript feed
- `ui/pages/insights.py` — stats panel
- `ui/pages/scratchpad.py` — autosaved notes
- `ui/pages/style_page.py` — persona picker + preview
- `ui/pages/settings_page.py` — embedded settings (mic / model / hotkey / polish / API key / style)

**Edit**
- `settings.py` — add `polish_enabled: bool`, `groq_api_key: str`, `style_persona: str`
- `main.py` — instantiate window, run polish in worker after transcribe, write history row
- `ui/tray.py` — add "Open Murmur" menu item, wire double-click → open window
- `requirements.txt` — add `groq`

## Implementation steps
1. [ ] **Storage** — `history.py` with SQLite, helpers `add()`, `recent(days)`, `stats()`
2. [ ] **Polish** — `polish.py` with Groq client + 4 persona prompts; graceful fallback if no key / network fail (use raw text)
3. [ ] **Settings extend** — new fields in `settings.py`, defaults: polish off, persona = "Raw"
4. [ ] **Wire polish + history into dictation flow** — after `transcribe`, optionally polish, then inject, then write history row
5. [ ] **Theme** — `ui/theme.py` Qt stylesheet
6. [ ] **Window shell** — `ui/window.py` 3-column `QMainWindow` with sidebar nav + `QStackedWidget` content + collapsible right rail
7. [ ] **Tray integration** — "Open Murmur" menu item, double-click handler, signal to controller
8. [ ] **Home page** — hero card with Murmur tip + scrollable transcript feed (day groups, time stamps, click to copy)
9. [ ] **Insights page** — total words, wpm (computed from durations), day streak, simple charts (optional)
10. [ ] **Scratchpad page** — `QTextEdit`, autosaves to `%APPDATA%\Murmur\scratchpad.txt` on edit
11. [ ] **Style page** — persona radio list + a small preview ("hello world this is murmur" → polished)
12. [ ] **Settings page** — port the existing dialog into the embedded page; add polish toggle, API key field (password mask), persona dropdown
13. [ ] **Close-to-tray** — override `closeEvent` to hide; only tray Quit truly exits

## Verification
- Hold Ctrl + Win, speak → text injects + appears in Home feed within ~2 s
- Double-click tray icon → window opens; right-click → "Open Murmur" → opens
- Close button (X) → window hides, app + tray still alive, hotkey still works
- Switching sidebar items swaps main content; right rail only shows on Home/Insights
- Insights numbers match what's in the SQLite DB
- Scratchpad content survives app restart
- Polish ON + valid Groq key → "hello world this is a test" → "Hello, world. This is a test."
- Polish ON + missing/invalid key → falls back to raw text, shows non-blocking toast
- Style switch changes polish tone (Casual vs Professional visibly different)

## Resolved
1. **Groq API key** — leave blank by default; polish silently no-ops until user pastes one in Settings.
2. **Voice Profile card** — keep, but fill with real personal insights computed from history:
   - **Favorite word** (most-used token, stopwords filtered)
   - **Top phrases** (top 3 two-/three-word ngrams)
   - **Most active hour** ("You dictate most around 9 PM")
   - **Vocabulary size** (unique words ever spoken)
3. **Sidebar** — full Wispr order. Dictionary / Snippets / Transforms shown but greyed out with a "Coming soon" badge.

## Voice Profile — computation spec
- `favorite_word`: `Counter(tokens).most_common(1)` excluding a built-in stopword set (~50 words: the, a, and, is, I, you, …)
- `top_phrases`: `Counter(2- and 3-grams).most_common(3)`, drop n-grams that are *entirely* stopwords
- `active_hour`: mode of `hour(ts)`, displayed as "9 PM" / "2 AM" etc.
- `vocab_size`: `len(set(lower(tokens)))` across all transcripts
- All computed in `history.py::profile()` — pure SQLite read + Python counting, no extra deps
