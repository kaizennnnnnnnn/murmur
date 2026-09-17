# Murmur

Push-to-talk dictation for Windows. Hold a key, speak, release — the transcript
is pasted at your cursor in whatever app has focus: Gmail, VS Code, Slack,
Discord, a browser, a terminal.

Speech recognition runs locally on your machine by default, through
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). No account, no
subscription, and nothing leaves the computer unless you deliberately turn on
the optional cloud features described below.

About 7,300 lines of Python across 32 files.

---

## Quick start

```bash
git clone https://github.com/kaizennnnnnnnn/murmur.git
cd murmur
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Murmur appears in the system tray and as a dock at the bottom of the screen.
Hold **Ctrl + Win**, say something, release. A second or two later the text
lands at your cursor.

The first run downloads the Whisper model (464 MB for the default `small.en`)
into `~/.cache/huggingface/`. Every run after that starts from disk.

Once it is set up, launch it without a console window using `Murmur.bat`
(tray only) or `Murmur-Open.bat` (opens the window). The `.vbs` files do the
same with no window flash at all — `Murmur-Silent.vbs` is the one to put in
your Startup folder.

**Requires Windows.** Text injection, the global hotkey, the tray, and the
notification sounds are all built on Windows APIs.

---

## What it does

**Dictation.** Push-to-talk on a configurable hotkey, or click the dock.

**Local by default.** `small.en` runs on your CPU. If an NVIDIA GPU is present
it is used automatically, and the app falls back to CPU on its own if the CUDA
runtime DLLs turn out to be missing — a common state on Windows machines that
have the GPU but not the CUDA Toolkit installed.

**A dictionary.** Names, jargon and product names you want recognised, fed to
Whisper as a vocabulary hint.

**Snippets.** Short spoken triggers that expand into longer stored text, matched
whole-word and case-insensitively, so `sig` inside `design` is left alone.

**Optional AI polish.** Punctuation, capitalisation and filler-word removal in
one of three voices — casual, professional, or email. Off unless you enable it.

**Transforms.** Copy text anywhere, open Murmur, click Shorten / Make formal /
Make casual, and your clipboard comes back rewritten. A custom transform is just
a prompt you write yourself.

**History and insights.** Every dictation is logged to a local SQLite database.
The Insights page reports words dictated, time saved, vocabulary size and your
most-used words.

**Correction learning.** After Murmur pastes, it watches briefly to see whether
you edit what it wrote, and records the correction. It reads keystrokes to do
that, so it is confined to the window the paste landed in: move focus anywhere
else and the buffer is discarded rather than saved. It can be switched off
entirely in Settings, under Corrections.

**A scratchpad**, autosaved to disk.

---

## Where your data lives

Everything is under `%APPDATA%\Murmur\`:

| File | What it holds |
|---|---|
| `config.json` | Settings, including the Groq API key if you set one |
| `history.db` | SQLite log of every dictation |
| `scratchpad.txt` | Scratchpad contents |
| `murmur.log` | The current session's log, truncated at each start |
| `debug\` | The last 5 recordings as WAV, for diagnosing bad transcripts |

None of it is written into the repository, and none of it is transmitted
anywhere.

---

## The cloud features are opt-in, and they are a real trade-off

Murmur can use [Groq](https://groq.com) for two things. Both need an API key you
paste into Settings, and each has its own switch, because they do not send the
same thing. **Holding a key uploads nothing on its own.**

1. **Cloud transcription** — Whisper Large v3 Turbo. Considerably more robust
   than local `small.en` on a quiet or noisy microphone. **This uploads your
   recorded audio**, as a WAV, on every dictation. Off by default.
2. **AI polish and transforms** — Llama 3.3 70B. This uploads the transcribed
   **text**, never the audio. Off by default.

Leave both switches off and Murmur is fully offline: the network is never touched
after the initial model download, whether or not a key is stored.

Both paths fail soft. A missing key, a dead connection, a rate limit or a
malformed response all return your raw text unchanged; nothing in the dictation
loop blocks on the network.

---

## Configuration

Open the window (`Murmur-Open.bat`, or the tray icon) and use the Settings page:

- Microphone device
- Whisper model
- Push-to-talk hotkey — a single key (`ctrl_r`) or a combo (`ctrl+win`)
- Theme, light or dark
- Microphone sensitivity — `normal`, `sensitive`, or `whisper`
- Groq API key, and separately: cloud transcription on/off, AI polish on/off, persona
- Correction learning on/off

### Choosing a model

| Model | Size | Speed on CPU | Quality |
|---|---|---|---|
| `tiny.en` | 74 MB | ~10x real-time | Fine for short commands |
| `base.en` | ~140 MB | ~5x real-time | Reasonable if CPU-only |
| `small.en` | 464 MB | ~2x real-time | **Default — best balance** |
| `medium.en` | ~1.5 GB | ~0.5x real-time | Good on a GPU, slow on CPU |
| `large-v3` | ~3 GB | GPU realistically | Best accuracy, multilingual |

---

## How a dictation actually runs

```
hotkey down    ->  mic capture starts (16 kHz mono float32)
hotkey up      ->  audio handed to a Qt worker thread
                   |- trim 200 ms head / 100 ms tail  (kills the key-press thump)
                   |- 100 Hz high-pass                (kills fan and HVAC rumble)
                   |- peak-normalise to 0.8           (lifts quiet speech)
                   |- transcribe: Groq if cloud STT is switched on, else local
                   |- reject known Whisper hallucinations
                   |- AI polish, if enabled
                   \- expand snippets
               ->  save clipboard -> set transcript -> Ctrl+V -> restore clipboard
```

Several of those steps exist because of a specific failure:

**The head and tail get trimmed** because pressing the hotkey produces a
mechanical transient that dwarfs the voice — a 0.8 peak against speech at 0.05.
Normalising before cutting that off scales the whole recording to the thump and
leaves the speech inaudible.

**Hallucinations are filtered by an explicit blocklist.** Whisper was trained on
an enormous amount of YouTube and podcast audio, so when handed something
unintelligible it does not return nothing — it returns `"Thanks for watching!"`
or `"Please subscribe."` with real confidence. Those stock phrases are matched
and dropped rather than pasted.

**The dictionary is phrased as a sentence, never a bare word list.** Whisper
treats `initial_prompt` as text to continue, so a prompt of `"Foo, Bar, Baz"`
sometimes comes back as the transcript `"Foo, Bar, Baz"` regardless of what was
actually said. For the same reason the dictionary is never sent to the cloud
model, which is confident enough to fall back on it wholesale.

**Injection goes through the clipboard**, not synthetic keystrokes. Save, set,
Ctrl+V, restore. It is the only method that works reliably across Chrome, VS
Code, Slack, Electron apps and terminals alike.

**The `whisper` sensitivity profile disables silero-VAD deliberately.** That
profile normalises every recording to about 0.9 peak, which lifts background
noise to the same loudness as the voice; silero then looks at the resulting wash
and rejects all of it as non-speech. Whisper's own no-speech detection handles
genuine silence anyway.

---

## Project layout

```
main.py                 Qt application, controller, dictation worker thread
audio.py                Mic capture, high-pass, noise gate, sensitivity profiles
transcribe.py           faster-whisper wrapper, CUDA detection, CPU fallback
transcribe_cloud.py     Groq Whisper Large v3 Turbo
polish.py               Groq Llama 3.3 70B, persona prompts
transforms.py           Clipboard-in, rewritten-clipboard-out
snippets.py             Whole-word trigger expansion
history.py              SQLite history and the statistics behind Insights
correction_watcher.py   Detects edits made to pasted text
hotkey.py               Global push-to-talk listener (single keys and combos)
inject.py               Clipboard-preserving paste
sound.py                UI blips, synthesised in memory at import
settings.py             Dataclass persisted to config.json
ui/                     Qt widgets: window, dock overlay, tray, theme
ui/pages/               Home, Insights, Voice Profile, Scratchpad, Settings,
                        Dictionary, Snippets, Style, Transforms
scripts/export_icon.py  Regenerates Murmur.ico from assets/ (needs Pillow)
```

---

## Running the modules on their own

Most modules have a `__main__` block:

```bash
python audio.py        # list microphones, record 3s, print the peak level
python transcribe.py   # record 4s and transcribe it
python hotkey.py       # print PRESS / RELEASE as you hold the hotkey
python inject.py       # type a test string into whatever has focus
python settings.py     # print the config path and current settings
python history.py      # print history statistics
python sound.py        # play each UI blip
```

---

## Troubleshooting

**Nothing happens when I hold the hotkey.** Check `%APPDATA%\Murmur\murmur.log`.
Under `pythonw` there is no console, so that file is where errors go.

**The transcript is empty.** Listen to the newest WAV in
`%APPDATA%\Murmur\debug\` — that is exactly what the model received. If it is
silent, the wrong microphone is selected. If it is very quiet, raise the
sensitivity to `sensitive` or `whisper` in Settings.

**`No module named scipy`.** Install the requirements. scipy is not optional:
the high-pass filter runs on every dictation, and resampling is needed whenever
the microphone will not open at 16 kHz, which is most of them.

**The first dictation takes 30+ seconds.** That is the one-time model download.

**CUDA errors in the log, but it works anyway.** Expected. ctranslate2 reported
a GPU but the cuBLAS/cuDNN DLLs were missing, so Murmur fell back to CPU.
Install the CUDA 12.x runtime and cuDNN for the GPU speed-up.

**Paste does not happen in one specific app.** UAC-elevated windows reject
synthetic input from a normal-privilege process. Run Murmur as administrator if
you need dictation inside one.

**The tray icon is missing.** Windows hides new tray icons by default. Click the
`^` chevron in the taskbar and drag it out.

---

## Prior art

Murmur began as a free, local reimplementation of
[Wispr Flow](https://wisprflow.ai/), and the Insights and Voice Profile pages
follow its layout closely. It is not affiliated with Wispr Flow in any way.
