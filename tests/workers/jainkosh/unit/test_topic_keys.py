"""Unit tests for topic_keys.py."""

import pytest
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.topic_keys import slug, natural_key, parent_of


@pytest.fixture
def config():
    return load_config()


def test_slug_preserves_devanagari(config):
    assert slug("द्रव्य", config) == "द्रव्य"


def test_slug_strips_danda(config):
    assert "।" not in slug("आत्मा।", config)
    assert "॥" not in slug("गाथा॥", config)


def test_slug_whitespace_to_dash(config):
    result = slug("भेद व लक्षण", config)
    assert " " not in result
    assert "-" in result


def test_slug_collapses_dashes(config):
    # Multiple spaces → multiple dashes → collapsed to one
    result = slug("भेद  लक्षण", config)
    assert "--" not in result


def test_slug_strips_v4_numeric_prefix(config):
    # V4 heading text like "1. भेद व लक्षण" → "भेद-व-लक्षण"
    result = slug("1. भेद व लक्षण", config)
    assert not result.startswith("1")
    assert "भेद" in result


def test_slug_strips_leading_trailing_dash(config):
    result = slug("-भेद-", config)
    assert not result.startswith("-")
    assert not result.endswith("-")


def test_natural_key_single_level(config):
    nk = natural_key("द्रव्य", ["भेद व लक्षण"], config)
    assert nk.startswith("द्रव्य:")
    assert "भेद" in nk


def test_natural_key_two_levels(config):
    nk = natural_key("द्रव्य", ["भेद व लक्षण", "निरुक्त्यर्थ"], config)
    parts = nk.split(":")
    assert parts[0] == "द्रव्य"
    assert len(parts) == 3


def test_parent_of_dotted():
    assert parent_of("1.1.3") == "1.1"
    assert parent_of("1.1") == "1"
    assert parent_of("1") is None


def test_parent_of_none_for_root():
    assert parent_of("2") is None
