"""Unit tests for normalize.py."""

import unicodedata
import pytest
from workers.ingestion.jainkosh.normalize import (
    nfc, strip_zwj, normalize_whitespace, normalize_text, decode_keyword_from_url
)


def test_nfc_basic():
    # NFD form → NFC
    nfd = unicodedata.normalize("NFD", "आत्मा")
    assert nfc(nfd) == "आत्मा"


def test_nfc_already_nfc():
    s = "द्रव्य"
    assert nfc(s) == s


def test_strip_zwj_removes_zwj():
    s = "क‍ष"  # ZWJ between characters
    result = strip_zwj(s)
    assert "‍" not in result


def test_strip_zwj_removes_zwnj():
    s = "क‌ष"  # ZWNJ
    result = strip_zwj(s)
    assert "‌" not in result


def test_normalize_whitespace_collapses():
    # collapses horizontal whitespace runs; newlines are not collapsed
    result = normalize_whitespace("a  b\tc")
    assert result == "a b c"


def test_normalize_whitespace_nbsp_replaced():
    # NBSP and narrow NBSP are replaced with regular space
    result = normalize_whitespace("a b")
    assert result == "a b"


def test_normalize_text_full():
    nfd_with_zwj = unicodedata.normalize("NFD", "आत्मा") + "‍"
    result = normalize_text("  " + nfd_with_zwj + "  ")
    assert result == "आत्मा"
    assert "‍" not in result


def test_decode_keyword_from_url_simple():
    url = "https://jainkosh.org/wiki/%E0%A4%A6%E0%A5%8D%E0%A4%B0%E0%A4%B5%E0%A5%8D%E0%A4%AF"
    result = decode_keyword_from_url(url)
    assert result == "द्रव्य"


def test_decode_keyword_from_url_devanagari():
    url = "https://jainkosh.org/wiki/आत्मा"
    result = decode_keyword_from_url(url)
    assert result == "आत्मा"


def test_decode_keyword_fragment_stripped():
    url = "https://jainkosh.org/wiki/आत्मा#1.2"
    result = decode_keyword_from_url(url)
    assert result == "आत्मा"


def test_decode_keyword_percent_encoded():
    # %E0%A4%A6%E0%A5%8D%E0%A4%B0%E0%A4%B5%E0%A5%8D%E0%A4%AF = द्रव्य
    url = "https://jainkosh.org/wiki/%E0%A4%A6%E0%A5%8D%E0%A4%B0%E0%A4%B5%E0%A5%8D%E0%A4%AF"
    result = decode_keyword_from_url(url)
    assert result == "द्रव्य"
