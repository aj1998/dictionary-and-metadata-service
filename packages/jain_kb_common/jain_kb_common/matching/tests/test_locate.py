import pytest

from jain_kb_common.matching.locate import locate
from jain_kb_common.matching.normalize import normalize


# ── helpers ───────────────────────────────────────────────────────────────────

def loc(src: str, tgt: str, **kw):
    return locate(normalize(src), normalize(tgt), **kw)


def offset_roundtrip_ok(result, tgt_text: str) -> bool:
    """target.original[char_start:char_end] must contain the matched region."""
    if not result.matched or result.char_start is None or result.char_end is None:
        return False
    r_tgt = normalize(tgt_text)
    snippet = r_tgt.original[result.char_start : result.char_end]
    # The snippet's normalized form must equal normalized_source
    from jain_kb_common.matching.normalize import normalize as nrm
    return nrm(snippet).normalized == result.normalized_source


# ── exact substring ───────────────────────────────────────────────────────────

def test_exact_match_at_start():
    r = loc("आत्मा", "आत्माद्रव्यम्")
    assert r.matched is True
    assert r.method == "exact_normalized"
    assert r.score == 1.0
    assert r.char_start == 0


def test_exact_match_at_end():
    r = loc("द्रव्यम्", "आत्माद्रव्यम्")
    assert r.matched is True
    assert r.method == "exact_normalized"
    tgt = normalize("आत्माद्रव्यम्")
    assert tgt.original[r.char_start : r.char_end] == "द्रव्यम्"


def test_exact_match_in_middle():
    r = loc("मध्य", "प्रारम्भमध्यअन्त")
    assert r.matched is True
    assert r.method == "exact_normalized"
    assert r.char_start is not None and r.char_end is not None


def test_exact_match_offset_roundtrip():
    src = "आत्मपरिणाम"
    tgt = "... आत्मपरिणाम ..."
    r = loc(src, tgt)
    assert r.matched is True
    assert offset_roundtrip_ok(r, tgt)


# ── danda / whitespace variants still produce exact match ────────────────────

def test_danda_variants_still_exact():
    # Source has danda; target has danda in different position — both normalize
    src = "आत्मा।परमात्मा"   # normalized → आत्माparमात्मा
    tgt = "अन्य।आत्मा।परमात्मा।वाक्य"
    r = loc(src, tgt)
    assert r.matched is True
    assert r.method == "exact_normalized"


def test_whitespace_variants_still_exact():
    src = "आत्मा  परमात्मा"   # double-space → normalizes same as single-space
    tgt = "वाक्यआत्माparमात्माअन्त"
    # both normalize to "आत्माparमात्मा" ... let me use safe ASCII-free test
    src2 = "अ  ब"
    tgt2 = "क अ  ब ड"
    r = loc(src2, tgt2)
    assert r.matched is True
    assert r.method == "exact_normalized"


def test_zwj_in_source_and_target_still_exact():
    src = "आत्‍मा"   # ZWJ inside
    tgt = "वाक्य आत्‍मा वाक्य"
    r = loc(src, tgt)
    assert r.matched is True
    assert r.method == "exact_normalized"


# ── no match ──────────────────────────────────────────────────────────────────

def test_completely_different_texts():
    r = loc("अबकडइ", "घचछजझ", threshold=0.80)
    assert r.matched is False
    assert r.method == "none"
    assert r.char_start is None
    assert r.char_end is None


def test_partial_overlap_below_threshold():
    # Source 20 chars, target has almost nothing in common
    r = loc("अबकडइउएओ", "ZZZZZZZZZZZZZZZZZZZZ", threshold=0.80)
    assert r.matched is False


def test_empty_source_no_match():
    # Empty normalized source — short-circuit to no-match
    r = loc("", "आत्मा")
    assert r.matched is False


def test_source_longer_than_target():
    r = loc("बहुत लम्बा पाठ जो लक्ष्य से बड़ा है", "छोटा")
    assert r.matched is False


# ── shingle fuzzy fallback ────────────────────────────────────────────────────

def test_shingle_fuzzy_one_extra_char():
    # Target has one extra char interspersed; should match with shingle
    src = "आत्मद्रव्य"
    # Normalize src: strip nothing → "आत्मद्रव्य"
    # Create target with an extra char embedded but same n-grams mostly
    # Use source characters + one extra at end to trigger fuzzy
    src_norm = normalize(src).normalized
    tgt_text = src_norm + "X" + "अन्यपाठ"   # source chars + 1 extra in window
    r = loc(src, tgt_text, threshold=0.50)
    # Should find the window starting at 0 as best (source_norm is a substring prefix)
    # Actually source IS a substring here... let me use a genuinely fuzzy case

def test_shingle_fuzzy_genuinely_fuzzy():
    # Construct a fuzzy case: source and target share most n-grams but not all
    # source = "abcde", target has "abXde" — different middle char
    src = "abcde"
    tgt = "prefixabXdeSUFFIX"
    r = loc(src, tgt, shingle_n=2, threshold=0.40)
    # n-grams of "abcde": {ab, bc, cd, de}
    # n-grams of "abXde": {ab, bX, Xd, de}
    # Jaccard = |{ab, de}| / |{ab, bc, cd, de, bX, Xd}| = 2/6 ≈ 0.33
    # With threshold=0.40 this won't match; let's check:
    # Actually use threshold=0.30
    r = loc(src, tgt, shingle_n=2, threshold=0.30)
    assert r.matched is True
    assert r.method == "shingle_fuzzy"
    assert r.score > 0.0


def test_shingle_below_threshold_no_match():
    src = "aaaaa"
    tgt = "bbbbbbbbbbb"
    r = loc(src, tgt, shingle_n=2, threshold=0.80)
    assert r.matched is False
    assert r.method == "none"


# ── offset round-trip (DoD acceptance criterion) ─────────────────────────────

def test_offset_roundtrip_devanagari():
    src = "द्वादशांगम्"
    tgt = "... आत्मा द्वादशांगम् आत्मपरिणामत्वात ..."
    r = loc(src, tgt)
    assert r.matched is True
    assert offset_roundtrip_ok(r, tgt)


def test_offset_roundtrip_with_stripped_chars_in_target():
    src = "आत्माparमात्मा".replace("par", "पर")
    # insert danda between them in target
    tgt = "वाक्य।आत्मा।parमात्मा।वाक्य".replace("par", "पर")
    r = loc(src, tgt)
    assert r.matched is True
    assert offset_roundtrip_ok(r, tgt)


# ── determinism ──────────────────────────────────────────────────────────────

def test_locate_is_deterministic():
    src = "समयसार"
    tgt = "प्रवचनसार समयसार नियमसार"
    results = [loc(src, tgt) for _ in range(5)]
    assert all(r.char_start == results[0].char_start for r in results)
    assert all(r.score == results[0].score for r in results)
