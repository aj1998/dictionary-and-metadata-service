"""Tests for shastra_identifiers util."""

import unicodedata
import pytest

from jain_kb_common.shastra_identifiers import (
    get_shastra_entry,
    get_identifier_fields,
    canonical_segment_name,
    build_compound_suffix,
)

# NFC-normalised shastra names used throughout.
_PP = unicodedata.normalize("NFC", "परमात्मप्रकाश")
_SS = unicodedata.normalize("NFC", "समयसार")


def test_get_entry_परमात्मप्रकाश_present():
    entry = get_shastra_entry(_PP)
    assert entry is not None
    assert entry.get("gatha_identifier") == "अधिकार,परमात्मप्रकाशगाथा"


def test_get_identifier_fields_compound():
    fields = get_identifier_fields(_PP)
    assert fields == ["अधिकार", "परमात्मप्रकाशगाथा"]


def test_get_identifier_fields_single_returns_none():
    fields = get_identifier_fields(_SS)
    assert fields is None


def test_canonical_segment_strips_exact_prefix():
    assert canonical_segment_name(_PP, "परमात्मप्रकाशगाथा") == "गाथा"
    assert canonical_segment_name(_PP, "अधिकार") == "अधिकार"


def test_canonical_segment_no_prefix_match():
    # A field that starts with the shastra name but leaves an empty remainder
    # should fall back to the original name.
    assert canonical_segment_name(_PP, _PP) == _PP


def test_build_compound_suffix():
    values = {"अधिकार": "1", "परमात्मप्रकाशगाथा": "2"}
    result = build_compound_suffix(_PP, values)
    assert result == "अधिकार:1:गाथा:2"


def test_build_compound_suffix_missing_field_returns_none():
    values = {"अधिकार": "1"}  # missing परमात्मप्रकाशगाथा
    result = build_compound_suffix(_PP, values)
    assert result is None


def test_build_compound_suffix_no_compound_returns_none():
    result = build_compound_suffix(_SS, {"गाथा": "5"})
    assert result is None


def test_nfc_lookup_matches_decomposed_input():
    # Confirm that NFC normalisation in lookup is stable regardless of input form.
    # For this shastra NFD == NFC (no decomposable code points), so we verify
    # the lookup succeeds via both forms without asserting they differ.
    decomposed = unicodedata.normalize("NFD", _PP)
    entry = get_shastra_entry(decomposed)
    assert entry is not None
    assert unicodedata.normalize("NFC", entry.get("shastra_name", "")) == _PP
