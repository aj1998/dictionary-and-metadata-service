import unicodedata

import pytest

from jain_kb_common.matching.normalize import normalize


# ── helpers ──────────────────────────────────────────────────────────────────

def roundtrip_holds(text: str) -> bool:
    """Every char in normalized must equal original[n2o[i]]."""
    r = normalize(text)
    if len(r.normalized) != len(r.n2o):
        return False
    return all(r.original[r.n2o[i]] == r.normalized[i] for i in range(len(r.normalized)))


# ── identity (no stripping needed) ───────────────────────────────────────────

def test_identity_pure_devanagari():
    text = "आत्मा"
    r = normalize(text)
    assert r.normalized == text
    assert r.n2o == list(range(len(text)))


def test_identity_latin():
    text = "hello"
    r = normalize(text)
    assert r.normalized == text


# ── round-trip property ───────────────────────────────────────────────────────

def test_roundtrip_simple():
    assert roundtrip_holds("आत्मा द्वादशांगम्")


def test_roundtrip_with_danda():
    assert roundtrip_holds("गाथा।पाठ।अर्थ")


def test_roundtrip_mixed_zwj_danda_digits():
    assert roundtrip_holds("आत्‍मा।39।परमात्मा")


def test_roundtrip_with_punctuation():
    assert roundtrip_holds("पाठ, 'उद्धरण' (भाग 1)।")


# ── rule 1: ZWJ / ZWNJ ───────────────────────────────────────────────────────

def test_zwj_stripped():
    r = normalize("आत्‍मा")
    assert "‍" not in r.normalized
    assert roundtrip_holds("आत्‍मा")


def test_zwnj_stripped():
    r = normalize("आत्‌मा")
    assert "‌" not in r.normalized


# ── rule 2: whitespace ────────────────────────────────────────────────────────

def test_space_stripped():
    r = normalize("अ ब")
    assert r.normalized == "अब"
    assert r.n2o == [0, 2]


def test_non_breaking_space_stripped():
    r = normalize("अ ब")
    assert r.normalized == "अब"


def test_tab_stripped():
    r = normalize("अ\tब")
    assert r.normalized == "अब"


# ── rule 3: danda / double-danda / pipe ──────────────────────────────────────

def test_danda_stripped():
    r = normalize("गाथा।पाठ")
    assert "।" not in r.normalized


def test_double_danda_stripped():
    r = normalize("गाथा॥पाठ")
    assert "॥" not in r.normalized


def test_pipe_stripped():
    r = normalize("अ|ब")
    assert "|" not in r.normalized
    assert r.normalized == "अब"


# ── rule 4: hyphens / underscore / tilde ─────────────────────────────────────

def test_ascii_hyphen_stripped():
    r = normalize("आत्मा-परमात्मा")
    assert "-" not in r.normalized


def test_unicode_hyphen_stripped():
    # U+2010 HYPHEN
    r = normalize("आत्मा‐परमात्मा")
    assert "‐" not in r.normalized


def test_em_dash_stripped():
    # U+2014 EM DASH
    r = normalize("अ—ब")
    assert "—" not in r.normalized


def test_underscore_stripped():
    r = normalize("अ_ब")
    assert "_" not in r.normalized


def test_tilde_stripped():
    r = normalize("अ~ब")
    assert "~" not in r.normalized


# ── rule 5: ASCII punctuation ────────────────────────────────────────────────

def test_comma_stripped():
    r = normalize("अ,ब")
    assert "," not in r.normalized


def test_period_stripped():
    r = normalize("अ.ब")
    assert "." not in r.normalized


def test_parens_stripped():
    r = normalize("(अ)")
    assert "(" not in r.normalized
    assert ")" not in r.normalized
    assert r.normalized == "अ"


def test_slash_stripped():
    r = normalize("अ/ब")
    assert "/" not in r.normalized


# ── rule 6: digit runs surrounded by stripped chars ──────────────────────────

def test_digit_run_between_dandas_stripped():
    # ।39। — digits bounded by dandas (stripped chars)
    r = normalize("।39।")
    assert r.normalized == ""


def test_devanagari_digit_run_between_dandas_stripped():
    r = normalize("।३९।")
    assert r.normalized == ""


def test_digit_at_string_boundary_stripped():
    # "39" with nothing else — bounded by string edges (treated as boundary)
    r = normalize("39")
    assert r.normalized == ""


def test_digit_standalone_inside_word_kept():
    # digit not surrounded by stripped chars on BOTH sides
    # 'अ' (left) and 'ब' (right) are NOT stripped → digit stays
    r = normalize("अ3ब")
    assert "3" in r.normalized


def test_digit_with_only_left_boundary_kept():
    # digit has stripped char on left but NOT on right
    r = normalize("।3ब")
    assert "3" in r.normalized


def test_digit_with_only_right_boundary_kept():
    r = normalize("अ3।")
    assert "3" in r.normalized


def test_digit_verse_marker_pattern():
    # Realistic verse marker: "।39।" inside a longer text
    r = normalize("आत्मा।39।द्रव्यम्")
    assert "3" not in r.normalized
    assert "9" not in r.normalized
    assert "आत्मा" in r.normalized
    assert "द्रव्यम्" in r.normalized


# ── rule 7: avagraha ─────────────────────────────────────────────────────────

def test_avagraha_stripped():
    r = normalize("आत्मऽपरमात्म")
    assert "ऽ" not in r.normalized


# ── rule 8: visarga ≡ ASCII colon ────────────────────────────────────────────

def test_visarga_stripped():
    r = normalize("स्वभावः")
    assert "ः" not in r.normalized
    assert r.normalized == "स्वभाव"


def test_visarga_and_ascii_colon_match():
    # Corpus typo: ASCII ':' typed in place of visarga (U+0903). Both forms
    # must normalize to the same string so the matcher finds the quote.
    a = normalize("स्वस्य भवनं तु स्वभाव:।")
    b = normalize("स्वस्य भवनं तु स्वभावः ।")
    assert a.normalized == b.normalized


# ── NFC normalization ────────────────────────────────────────────────────────

def test_nfc_applied():
    # NFD form of 'क' (U+0915) + combining nukta → NFC should produce क़ (if applicable)
    # Use a simpler case: NFD decomposed vowel sign
    nfd_text = unicodedata.normalize("NFD", "का")  # क + ा in NFD
    r = normalize(nfd_text)
    # The original is stored as NFC
    assert r.original == unicodedata.normalize("NFC", nfd_text)


# ── offset correctness ───────────────────────────────────────────────────────

def test_n2o_indices_are_within_original():
    text = "अ।ब॥क"
    r = normalize(text)
    for idx in r.n2o:
        assert 0 <= idx < len(r.original)


def test_n2o_monotonically_increasing():
    text = "अ।ब।क।ड"
    r = normalize(text)
    for i in range(1, len(r.n2o)):
        assert r.n2o[i] > r.n2o[i - 1]


def test_empty_input():
    r = normalize("")
    assert r.normalized == ""
    assert r.n2o == []
    assert r.original == ""


# ── Rule 11: र्-gemination collapse ──────────────────────────────────────────

def test_ra_gemination_parayaya():
    # पर्य्याय (geminated) and पर्याय (single) must canonicalize identically.
    a = normalize("पर्य्याय").normalized
    b = normalize("पर्याय").normalized
    assert a == b == "पर्याय"


def test_ra_gemination_dharma():
    assert normalize("धर्म्म").normalized == normalize("धर्म").normalized


def test_ra_gemination_karma():
    assert normalize("कर्म्म").normalized == normalize("कर्म").normalized


def test_ra_gemination_does_not_touch_unrelated_double():
    # मक्का has क्क but no preceding र् — must not be collapsed.
    r = normalize("मक्का")
    assert r.normalized == "मक्का"


def test_ra_gemination_does_not_touch_abhyupagamya():
    # अभ्युपगम्य has a real म्य conjunct (not after र्) — must stay intact.
    assert normalize("अभ्युपगम्य").normalized == "अभ्युपगम्य"


def test_ra_gemination_in_full_extract():
    src = "षड्ढानिवृद्धिरूपाः सूक्ष्माः परमागमप्रामाण्यादभ्युपगमाः अर्थपर्य्यायाः"
    tgt = "षड्ढानिवृद्धिरूपाः सूक्ष्माः परमागमप्रामाण्यादभ्युपगम्याः अर्थपर्यायाः षण्णां द्रव्याणां साधारणाः"
    s = normalize(src).normalized
    t = normalize(tgt).normalized
    # After collapse, अर्थपर्याय appears identically in both sides.
    assert "अर्थपर्याय" in s
    assert "अर्थपर्याय" in t
