"""Settings persistence at %APPDATA%\\Murmur\\config.json."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


def _config_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Murmur"


CONFIG_PATH = _config_dir() / "config.json"


@dataclass
class Settings:
    model_size: str = "small.en"
    mic_device_index: Optional[int] = None
    hotkey_key: str = "ctrl+win"
    min_recording_ms: int = 300
    polish_enabled: bool = False
    groq_api_key: str = ""
    style_persona: str = "raw"
    theme: str = "light"
    mic_sensitivity: str = "normal"  # normal | sensitive | whisper
    dictionary_terms: List[str] = field(default_factory=list)
    snippets: dict = field(default_factory=dict)
    custom_transforms: dict = field(default_factory=dict)  # name -> prompt


def load() -> Settings:
    if not CONFIG_PATH.exists():
        return Settings()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return Settings(**{k: v for k, v in data.items() if k in Settings.__annotations__})
    except Exception as exc:
        print(f"[settings] load failed ({exc}); using defaults")
        return Settings()


def save(s: Settings) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")


if __name__ == "__main__":
    print(f"Config path: {CONFIG_PATH}")
    s = load()
    print(f"Loaded: {s}")
    save(s)
    print("Saved.")
