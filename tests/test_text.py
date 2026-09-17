# -*- coding: utf-8 -*-
"""The two text filters that sit between the model and the cursor.

Both have a failure mode that looks like nothing at all: a snippet that
expands inside an unrelated word, and a stock phrase Whisper invented being
pasted as though it were speech.
"""
from snippets import expand
from transcribe import _is_hallucination


class TestSnippetExpansion:
    def test_expands_a_trigger(self):
        assert expand("sig", {"sig": "Kind regards, Jovan"}) == "Kind regards, Jovan"

    def test_matches_whole_words_only(self):
        """The documented promise: 'sig' inside 'design' is left alone."""
        assert expand("a design doc", {"sig": "SIGNATURE"}) == "a design doc"

    def test_is_case_insensitive(self):
        assert expand("SIG", {"sig": "x"}) == "x"
        assert expand("Sig", {"sig": "x"}) == "x"

    def test_expands_every_occurrence(self):
        assert expand("sig and sig", {"sig": "x"}) == "x and x"

    def test_leaves_text_alone_when_there_are_no_snippets(self):
        assert expand("untouched", {}) == "untouched"

    def test_empty_text_survives(self):
        assert expand("", {"sig": "x"}) == ""

    def test_a_trigger_with_regex_characters_is_taken_literally(self):
        """Triggers come from a text box, so they can contain anything."""
        assert expand("a.b", {"a.b": "ok"}) == "ok"
        assert expand("axb", {"a.b": "ok"}) == "axb"


class TestHallucinationFilter:
    """Whisper was trained on a great deal of YouTube and podcast audio, so
    handed something unintelligible it returns a stock phrase with real
    confidence rather than returning nothing."""

    def test_blocks_the_stock_phrases(self):
        for phrase in ("Thanks for watching!", "thank you", "Please subscribe.",
                       "Thank you for watching", "you", "Bye."):
            assert _is_hallucination(phrase), phrase

    def test_ignores_case_and_trailing_punctuation(self):
        assert _is_hallucination("THANK YOU")
        assert _is_hallucination("thanks for watching")

    def test_allows_real_speech(self):
        for phrase in ("Thank you for the pull request, I will look tonight.",
                       "Move the migration to Friday.",
                       "Remember to thank you know who",
                       "The quick brown fox jumps over the lazy dog."):
            assert not _is_hallucination(phrase), phrase

    def test_empty_text_is_not_a_hallucination(self):
        """Empty means the filter has nothing to do; the caller already
        handles an empty transcript separately."""
        assert not _is_hallucination("")
