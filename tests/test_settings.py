# -*- coding: utf-8 -*-
"""Config persistence, and what happens to a file written by an older build.

config.json is the only copy of the API key and the dictionary, and new fields
get added to Settings over time, so the interesting case is not the round trip
but the upgrade.
"""
import json
from dataclasses import asdict, replace

import settings as S
from settings import Settings

KEY = "gsk_pretend_key_for_the_test"


class TestRoundTrip:
    def test_save_then_load_returns_the_same_values(self, config_path):
        cfg = replace(Settings(), model_size="base.en", theme="dark",
                      groq_api_key=KEY, cloud_stt_enabled=True,
                      correction_learning_enabled=False)
        S.save(cfg)
        assert S.load() == cfg

    def test_missing_file_gives_defaults(self, config_path):
        assert not config_path.exists()
        assert S.load() == Settings()

    def test_unreadable_file_falls_back_instead_of_crashing(self, config_path):
        config_path.write_text("{not json at all", encoding="utf-8")
        assert S.load() == Settings()


class TestUpgradeFromAnOlderConfig:
    """A file written before cloud_stt_enabled and correction_learning_enabled
    existed. It has to keep working, and the new switches have to come up at
    their defaults rather than inheriting anything."""

    def write_old(self, config_path):
        config_path.write_text(json.dumps({
            "model_size": "small.en",
            "hotkey_key": "ctrl+win",
            "polish_enabled": True,
            "groq_api_key": KEY,
            "style_persona": "casual",
            "theme": "dark",
            "mic_sensitivity": "sensitive",
            "dictionary_terms": ["Supabase"],
        }), encoding="utf-8")

    def test_old_values_survive(self, config_path):
        self.write_old(config_path)
        cfg = S.load()
        assert cfg.style_persona == "casual"
        assert cfg.theme == "dark"
        assert cfg.groq_api_key == KEY
        assert cfg.dictionary_terms == ["Supabase"]

    def test_audio_upload_stays_off_after_an_upgrade(self, config_path):
        """The whole point of the separate switch: an install that already had
        a key must not start uploading because it was upgraded."""
        self.write_old(config_path)
        assert S.load().cloud_stt_enabled is False

    def test_correction_learning_keeps_working_after_an_upgrade(self, config_path):
        self.write_old(config_path)
        assert S.load().correction_learning_enabled is True

    def test_unknown_keys_are_ignored(self, config_path):
        """A config written by a newer build, opened by an older one."""
        config_path.write_text(json.dumps({
            "model_size": "base.en",
            "some_future_setting": 42,
        }), encoding="utf-8")
        assert S.load().model_size == "base.en"


class TestTheKeyIsNotPrinted:
    """settings.py has a __main__ block that prints the loaded Settings, and
    the README tells people to run it. It used to print the key."""

    def test_repr_does_not_contain_the_key(self):
        assert KEY not in repr(replace(Settings(), groq_api_key=KEY))

    def test_formatting_does_not_contain_the_key(self):
        cfg = replace(Settings(), groq_api_key=KEY)
        assert KEY not in f"{cfg}"
        assert KEY not in str(cfg)

    def test_but_it_is_still_persisted(self, config_path):
        """repr=False must not stop the key reaching disk, or the app forgets
        it on every restart."""
        cfg = replace(Settings(), groq_api_key=KEY)
        assert asdict(cfg)["groq_api_key"] == KEY
        S.save(cfg)
        assert KEY in config_path.read_text(encoding="utf-8")
        assert S.load().groq_api_key == KEY


class TestDefaults:
    def test_nothing_that_sends_data_is_on_by_default(self):
        fresh = Settings()
        assert fresh.groq_api_key == ""
        assert fresh.cloud_stt_enabled is False
        assert fresh.polish_enabled is False
