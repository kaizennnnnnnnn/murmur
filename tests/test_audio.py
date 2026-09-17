# -*- coding: utf-8 -*-
"""The signal processing every dictation runs through.

These are the functions whose behaviour is easiest to get quietly wrong: a
filter that does nothing still returns an array of the right shape, and a
normaliser that amplifies silence only shows up later as a hallucinated
transcript. So the assertions are about what the numbers actually do.
"""
import numpy as np
import pytest

from audio import (
    SAMPLE_RATE,
    get_sensitivity,
    high_pass,
    normalize_peak,
)


def tone(hz, seconds=0.5, amplitude=0.5):
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def rms(x):
    return float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0


class TestHighPass:
    """100 Hz, 4th order. Below the lowest male fundamental (~85 Hz) so the
    voice survives, above the 20-80 Hz band that is fan and HVAC rumble."""

    def test_removes_low_rumble(self):
        out = high_pass(tone(40))
        # 60 Hz below a 4th-order corner is heavy attenuation, not a trim.
        assert rms(out) < rms(tone(40)) * 0.25

    def test_keeps_the_voice(self):
        src = tone(300)
        out = high_pass(src)
        assert rms(out) > rms(src) * 0.85

    def test_passband_is_flatter_than_stopband(self):
        """The point of a filter is the ratio between the two, so compare them
        rather than trusting either number alone."""
        low = rms(high_pass(tone(40))) / rms(tone(40))
        high = rms(high_pass(tone(300))) / rms(tone(300))
        assert high > low * 3

    def test_empty_input_survives(self):
        out = high_pass(np.zeros(0, dtype=np.float32))
        assert out.size == 0

    def test_returns_float32(self):
        """faster-whisper expects float32; float64 silently doubles memory."""
        assert high_pass(tone(300)).dtype == np.float32


class TestNormalizePeak:
    def test_lifts_a_quiet_recording_to_the_target(self):
        out = normalize_peak(tone(200, amplitude=0.02), target=0.8)
        assert np.max(np.abs(out)) == pytest.approx(0.8, abs=1e-3)

    def test_brings_a_loud_recording_down(self):
        out = normalize_peak(tone(200, amplitude=0.99), target=0.8)
        assert np.max(np.abs(out)) == pytest.approx(0.8, abs=1e-3)

    def test_leaves_near_silence_alone(self):
        """Without this guard, a silent room is amplified to full scale and
        Whisper invents a sentence out of the boosted noise."""
        quiet = (np.ones(1000, dtype=np.float32) * 1e-6)
        out = normalize_peak(quiet, target=0.8)
        assert np.max(np.abs(out)) < 1e-4

    def test_empty_input_survives(self):
        assert normalize_peak(np.zeros(0, dtype=np.float32)).size == 0


class TestSensitivityProfiles:
    def test_unknown_name_falls_back_to_normal(self):
        assert get_sensitivity("nonsense") == get_sensitivity("normal")

    def test_every_profile_carries_what_the_worker_reads(self):
        """main.py reads exactly these two keys. A profile missing one would
        raise mid-dictation rather than at startup."""
        for name in ("normal", "sensitive", "whisper"):
            profile = get_sensitivity(name)
            assert "vad_threshold" in profile
            assert "use_vad" in profile

    def test_sensitive_is_more_permissive_than_normal(self):
        assert get_sensitivity("sensitive")["vad_threshold"] < \
               get_sensitivity("normal")["vad_threshold"]

    def test_whisper_profile_disables_vad(self):
        """Deliberate: after normalisation lifts speech and noise to the same
        loudness, silero rejects the whole recording as non-speech."""
        assert get_sensitivity("whisper")["use_vad"] is False
