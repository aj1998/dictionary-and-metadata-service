"""Unit tests for the text pre-processing pipeline in parse_reference.py."""

import pytest

from workers.ingestion.jainkosh.config import (
    ReferenceNoisePhraseConfig,
    ReferenceSectionKeywordsConfig,
    load_config,
)
from workers.ingestion.jainkosh.parse_reference import (
    _collapse_ws,
    _preprocess_text,
    _strip_noise_phrases,
    _strip_parens,
    _strip_punct,
    _strip_section_keywords,
    _strip_trailing_non_numeric,
)

DEFAULT_KEYWORDS = [
    "गाथा", "श्लोक", "पंक्ति", "कलश", "अधिकार", "अध्याय",
    "सर्ग", "परिच्छेद", "प्रकरण", "खण्ड", "भाग", "पुस्तक",
]


@pytest.fixture
def kw_config():
    return ReferenceSectionKeywordsConfig(enabled=True, keywords=DEFAULT_KEYWORDS)


@pytest.fixture
def noise_config():
    return ReferenceNoisePhraseConfig(enabled=True, phrases=["मूल गाथा या टीका"])


# ---------------------------------------------------------------------------
# _strip_parens
# ---------------------------------------------------------------------------

class TestStripParens:
    @pytest.mark.parametrize("text,expected", [
        ("( ज्ञानसार श्लोक 29)", " ज्ञानसार श्लोक 29"),
        ("(द्रव्यसंग्रह / मूल गाथा या टीका 14/46)", "द्रव्यसंग्रह / मूल गाथा या टीका 14/46"),
        ("धवला 1/5", "धवला 1/5"),
        ("(( nested ))", " nested "),
    ])
    def test_strip_parens(self, text, expected):
        assert _strip_parens(text) == expected


# ---------------------------------------------------------------------------
# _strip_noise_phrases
# ---------------------------------------------------------------------------

class TestStripNoisePhrases:
    def test_removes_exact_phrase(self, noise_config):
        result = _strip_noise_phrases("द्रव्यसंग्रह / मूल गाथा या टीका 14/46", noise_config)
        assert "मूल गाथा या टीका" not in result
        assert "द्रव्यसंग्रह" in result

    def test_unrelated_phrase_unchanged(self, noise_config):
        text = "समाधिशतक / मूल या टीका गाथा 4"
        assert _strip_noise_phrases(text, noise_config) == text

    def test_disabled_skips_removal(self):
        cfg = ReferenceNoisePhraseConfig(enabled=False, phrases=["मूल गाथा या टीका"])
        text = "X / मूल गाथा या टीका 1"
        assert _strip_noise_phrases(text, cfg) == text

    def test_phrase_replaced_with_space(self, noise_config):
        # Phrase replaced with " "; adjacent spaces are collapsed later by _collapse_ws
        result = _strip_noise_phrases("A मूल गाथा या टीका B", noise_config)
        assert "मूल गाथा या टीका" not in result
        assert "A" in result and "B" in result


# ---------------------------------------------------------------------------
# _strip_section_keywords
# ---------------------------------------------------------------------------

class TestStripSectionKeywords:
    @pytest.mark.parametrize("text,expected", [
        ("धवला पुस्तक 13/5", "धवला 13/5"),
        ("ज्ञानार्णव अधिकार 32/5/317", "ज्ञानार्णव 32/5/317"),
        ("ज्ञानसार श्लोक 29", "ज्ञानसार 29"),
        ("समयसार / आत्मख्याति गाथा 8", "समयसार / आत्मख्याति 8"),
    ])
    def test_removes_surrounded_keyword(self, kw_config, text, expected):
        assert _strip_section_keywords(text, kw_config) == expected

    def test_keyword_at_start_not_removed(self, kw_config):
        # No whitespace before keyword — must not remove
        assert _strip_section_keywords("गाथा 5", kw_config) == "गाथा 5"

    def test_keyword_at_end_not_removed(self, kw_config):
        assert _strip_section_keywords("धवला गाथा", kw_config) == "धवला गाथा"

    def test_disabled_skips_removal(self):
        cfg = ReferenceSectionKeywordsConfig(enabled=False, keywords=["गाथा"])
        assert _strip_section_keywords("A गाथा B", cfg) == "A गाथा B"


# ---------------------------------------------------------------------------
# _preprocess_text (full pipeline)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _strip_punct (14A.6a)
# ---------------------------------------------------------------------------

class TestStripPunct:
    @pytest.mark.parametrize("text,expected", [
        ("धवला 1/5।", "धवला 1/5 "),
        ("ज्ञानसार 29॥", "ज्ञानसार 29 "),
        ("धवला 1/5", "धवला 1/5"),          # no dandas → unchanged
        ("धवला 1/1,1,1/84/1", "धवला 1/1,1,1/84/1"),  # commas NOT stripped
    ])
    def test_strip_punct(self, text, expected):
        assert _strip_punct(text) == expected


# ---------------------------------------------------------------------------
# _strip_trailing_non_numeric (14A.8)
# ---------------------------------------------------------------------------

class TestStripTrailingNonNumeric:
    @pytest.mark.parametrize("numeric,expected", [
        ("3/1,2,1/2/ नं.", "3/1,2,1/2"),
        ("3/1,2,1/2/पृ.", "3/1,2,1/2"),
        ("1/5/317", "1/5/317"),           # all numeric → unchanged
        ("", ""),                          # empty → unchanged
        ("नं.", ""),                        # all non-numeric → empty
        ("1/5/ ", "1/5"),                  # whitespace-only segment → dropped
    ])
    def test_trailing_strip(self, numeric, expected):
        assert _strip_trailing_non_numeric(numeric) == expected


class TestPreprocessText:
    @pytest.fixture
    def cfg(self):
        return load_config()

    @pytest.mark.parametrize("text,expected", [
        ("( ज्ञानार्णव अधिकार 32/5/317)", "ज्ञानार्णव 32/5/317"),
        ("(द्रव्यसंग्रह / मूल गाथा या टीका 14/46)", "द्रव्यसंग्रह / 14/46"),
        ("धवला पुस्तक 13/5,5,50/282/9", "धवला 13/5,5,50/282/9"),
        ("समयसार / आत्मख्याति गाथा 8", "समयसार / आत्मख्याति 8"),
        # jainkosh.yaml includes "मूल या टीका" as a noise phrase, so it is stripped:
        ("(परमात्मप्रकाश / मूल या टीका अधिकार 1/11)", "परमात्मप्रकाश / 1/11"),
        ("( ज्ञानसार श्लोक 29)", "ज्ञानसार 29"),
        ("धवला 1/5", "धवला 1/5"),
    ])
    def test_full_pipeline(self, cfg, text, expected):
        assert _preprocess_text(text, cfg.reference) == expected
