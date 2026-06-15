"""Cross-source compound-ID alignment test.

Verifies that a परमात्मप्रकाश gatha referenced by a JainKosh keyword lands on the
same NK as the gatha node emitted by the NJ envelope — without requiring live
databases. We test at the envelope layer (would_write output).
"""
from __future__ import annotations

import json

import pytest

from jain_kb_common.shastra_identifiers import build_compound_suffix, get_identifier_fields
from workers.ingestion.jainkosh.reference_edges import _build_gatha_nk_from_reference


SHASTRA_NK = "परमात्मप्रकाश"
ADHIKAAR = "1"
GATHA_NUM = "19"
EXPECTED_NK = f"{SHASTRA_NK}:अधिकार:{ADHIKAAR}:गाथा:{GATHA_NUM}"


# ---------------------------------------------------------------------------
# 1. NJ-side NK: build_compound_suffix directly
# ---------------------------------------------------------------------------

def test_nj_compound_gatha_nk():
    """NJ envelope produces the expected compound NK via build_compound_suffix."""
    fields = get_identifier_fields(SHASTRA_NK, "gatha")
    assert fields is not None, "परमात्मप्रकाश must have gatha_identifier in shastra.json"
    identifier_values = {
        "अधिकार": ADHIKAAR,
        "परमात्मप्रकाशगाथा": GATHA_NUM,
    }
    suffix = build_compound_suffix(SHASTRA_NK, identifier_values, kind="gatha")
    assert suffix is not None
    nk = f"{SHASTRA_NK}:{suffix}"
    assert nk == EXPECTED_NK


# ---------------------------------------------------------------------------
# 2. JK-side NK: _build_gatha_nk_from_reference
# ---------------------------------------------------------------------------

def test_jk_compound_gatha_nk():
    """JK reference parser produces the expected compound NK."""
    parsed_fields = {
        "अधिकार": int(ADHIKAAR),
        "परमात्मप्रकाशगाथा": int(GATHA_NUM),
    }
    nk = _build_gatha_nk_from_reference(SHASTRA_NK, parsed_fields)
    assert nk == EXPECTED_NK


# ---------------------------------------------------------------------------
# 3. Cross-source: both sides produce the SAME NK
# ---------------------------------------------------------------------------

def test_cross_source_nj_and_jk_produce_same_gatha_nk():
    """NJ envelope NK == JK reference NK for परमात्मप्रकाश adhikaar:1 gatha:19."""
    # NJ side
    identifier_values = {
        "अधिकार": ADHIKAAR,
        "परमात्मप्रकाशगाथा": GATHA_NUM,
    }
    suffix = build_compound_suffix(SHASTRA_NK, identifier_values, kind="gatha")
    nj_nk = f"{SHASTRA_NK}:{suffix}"

    # JK side (values are ints from resolved_fields)
    parsed_fields = {
        "अधिकार": int(ADHIKAAR),
        "परमात्मप्रकाशगाथा": int(GATHA_NUM),
    }
    jk_nk = _build_gatha_nk_from_reference(SHASTRA_NK, parsed_fields)

    assert nj_nk == jk_nk == EXPECTED_NK, (
        f"NK mismatch: NJ={nj_nk!r} JK={jk_nk!r} expected={EXPECTED_NK!r}"
    )


# ---------------------------------------------------------------------------
# 4. Legacy shastras are unaffected (समयसार still uses old pattern)
# ---------------------------------------------------------------------------

def test_legacy_shastra_nk_unchanged():
    """समयसार (no gatha_identifier) still uses legacy NK pattern."""
    fields = get_identifier_fields("समयसार", "gatha")
    assert fields is None, "समयसार must NOT have gatha_identifier"

    nk = _build_gatha_nk_from_reference("समयसार", {"गाथा": 8})
    assert nk == "समयसार:गाथा:8"


# ---------------------------------------------------------------------------
# 5. Missing compound field → None returned (no edge, no crash)
# ---------------------------------------------------------------------------

def test_missing_compound_field_returns_none():
    """When a required compound field is absent, returns None (no NK, no edge)."""
    parsed_fields = {"परमात्मप्रकाशगाथा": 19}  # अधिकार missing
    nk = _build_gatha_nk_from_reference(SHASTRA_NK, parsed_fields)
    assert nk is None
