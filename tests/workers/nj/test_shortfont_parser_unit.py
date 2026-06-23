"""Unit tests for the shortFont glossary extractor."""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from workers.ingestion.nj.shortfont_parser import extract_shortfont


def _nodes(html: str) -> list:
    """Parse an HTML fragment and return children of the wrapper div."""
    soup = BeautifulSoup(f"<div id='_w'>{html}</div>", "lxml")
    return list(soup.select_one("div#_w").children)


# ---------------------------------------------------------------------------
# Case 1: 161-style fixture — 4 markers, all definitions
# ---------------------------------------------------------------------------

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "workers/ingestion/nj/tests/fixtures/shortfont/161_excerpt.html"
)


def test_four_definition_markers_fixture():
    """Four =‑definition markers from the 161_excerpt fixture."""
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    teeka0 = soup.select_one("div#teeka0")
    assert teeka0 is not None
    # The content div is the last <div> child (not steeka0)
    all_divs = teeka0.select(":scope > div")
    content_div = all_divs[-1]  # steeka0 is first; content div is last
    assert content_div is not None
    nodes = [content_div]

    cleaned_md, entries = extract_shortfont(nodes)

    assert len(entries) == 4
    markers = {e.marker_number for e in entries}
    assert markers == {1, 2, 3, 4}

    for entry in entries:
        assert entry.is_definition is True
        assert len(entry.occurrences) == 1

    # Cleaned text must NOT contain bare Devanagari digits adjacent to anchors
    import re
    for entry in entries:
        anchor = entry.anchor_text
        # Check that digits don't appear immediately before the anchor in the text
        assert not re.search(r"[०-९\d]" + re.escape(anchor), cleaned_md), (
            f"Digit found adjacent to anchor {anchor!r} in cleaned_md"
        )


def test_four_definition_markers_inline():
    """Same golden path but with an inline HTML fixture (no file I/O)."""
    html = """
    <div>
      अब <sup>१</sup>उत्तर-कर्मसंतति का क्षय होता है
      और <sup>२</sup>पूर्व संचित कर्म का फल भोगा जाता है ।
      <span class="shortFont">
        <sup>१</sup>उत्तर-कर्मसंतति = बाद का कर्म प्रवाह ।<br/>
        <sup>२</sup>पूर्व = पहले की ।
      </span>
    </div>
    """
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert len(entries) == 2
    by_num = {e.marker_number: e for e in entries}

    assert by_num[1].is_definition is True
    assert by_num[1].anchor_text == "उत्तर-कर्मसंतति"
    assert by_num[1].meaning == "बाद का कर्म प्रवाह"
    assert len(by_num[1].occurrences) == 1

    assert by_num[2].is_definition is True
    assert by_num[2].anchor_text == "पूर्व"
    assert len(by_num[2].occurrences) == 1

    # Cleaned markdown has no superscript digits
    assert "१" not in cleaned_md
    assert "२" not in cleaned_md
    assert "उत्तर-कर्मसंतति" in cleaned_md
    assert "पूर्व" in cleaned_md


# ---------------------------------------------------------------------------
# Case 2: Bare narrative footnote (no = separator)
# ---------------------------------------------------------------------------

def test_bare_narrative_footnote():
    """Bare footnote: anchor_text filled from body token; is_definition=False."""
    html = """
    <div>
      यहाँ <sup>३</sup>केवली-भगवान का वर्णन है ।
      <span class="shortFont">
        <sup>३</sup>केवली-भगवान को वेदनीय, नाम और गोत्र कर्म की स्थिति होती है ।
      </span>
    </div>
    """
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.marker_number == 3
    assert entry.marker_devanagari == "३"
    assert entry.is_definition is False
    assert entry.anchor_text == "केवली-भगवान"
    assert "केवली-भगवान को वेदनीय" in entry.meaning
    assert len(entry.occurrences) == 1
    # Offset round-trip
    occ = entry.occurrences[0]
    assert cleaned_md[occ.start_offset:occ.end_offset] == entry.anchor_text


# ---------------------------------------------------------------------------
# Case 3: Marker repeats twice in body
# ---------------------------------------------------------------------------

def test_repeated_marker_two_occurrences():
    """A marker that appears twice in the body → occurrences length 2, offsets increasing."""
    html = """
    <div>
      <sup>१</sup>उत्तर-कर्मसंतति पहले और
      फिर <sup>१</sup>उत्तर-कर्मसंतति दूसरे ।
      <span class="shortFont">
        <sup>१</sup>उत्तर-कर्मसंतति = बाद का कर्म प्रवाह ।
      </span>
    </div>
    """
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert len(entries) == 1
    entry = entries[0]
    assert len(entry.occurrences) == 2

    occ0, occ1 = entry.occurrences
    assert occ0.start_offset < occ1.start_offset, "Offsets must be monotonically increasing"

    # Both offsets round-trip correctly
    for occ in entry.occurrences:
        assert cleaned_md[occ.start_offset:occ.end_offset] == entry.anchor_text


# ---------------------------------------------------------------------------
# Case 4: Glossary present, body marker missing (orphan glossary)
# ---------------------------------------------------------------------------

def test_orphan_glossary_entry():
    """Glossary has marker not found in body → warning, entry kept with occurrences=[]."""
    html = """
    <div>
      कोई पाठ बिना मार्कर ।
      <span class="shortFont">
        <sup>१</sup>शब्द = अर्थ ।
      </span>
    </div>
    """
    warnings: list[str] = []
    cleaned_md, entries = extract_shortfont(_nodes(html), warnings=warnings)

    assert any("shortfont_orphan_glossary" in w and "1" in w for w in warnings)
    assert len(entries) == 1
    assert entries[0].occurrences == []
    # Cleaned markdown should still be intact
    assert "कोई पाठ बिना मार्कर" in cleaned_md


# ---------------------------------------------------------------------------
# Case 5: Body marker present, glossary line missing
# ---------------------------------------------------------------------------

def test_body_marker_without_glossary():
    """Body has <sup>N</sup> but no shortFont span → warning, digit stripped, no entry."""
    html = """
    <div>
      <sup>१</sup>शब्द का उपयोग ।
    </div>
    """
    warnings: list[str] = []
    cleaned_md, entries = extract_shortfont(_nodes(html), warnings=warnings)

    assert any("shortfont_missing_glossary" in w and "1" in w for w in warnings)
    assert entries == []
    # Digit is stripped from cleaned markdown
    assert "१" not in cleaned_md
    assert "शब्द" in cleaned_md


# ---------------------------------------------------------------------------
# Case 6: Offset round-trip for all entries
# ---------------------------------------------------------------------------

def test_offset_roundtrip():
    """cleaned_md[start:end] == anchor_text for every occurrence in multi-marker HTML."""
    html = """
    <div>
      <sup>१</sup>धर्म का अर्थ जानना चाहिए ।
      <sup>२</sup>मोक्ष-मार्ग की चर्चा है ।
      <span class="shortFont">
        <sup>१</sup>धर्म = सम्यग्दर्शन-ज्ञान-चारित्र ।<br/>
        <sup>२</sup>मोक्ष-मार्ग = मुक्ति का मार्ग ।
      </span>
    </div>
    """
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert len(entries) == 2
    for entry in entries:
        for occ in entry.occurrences:
            extracted = cleaned_md[occ.start_offset:occ.end_offset]
            assert extracted == entry.anchor_text, (
                f"Round-trip failed for marker {entry.marker_number}: "
                f"got {extracted!r}, expected {entry.anchor_text!r}"
            )


# ---------------------------------------------------------------------------
# Case 7: <span class=notes> parentheticals untouched
# ---------------------------------------------------------------------------

def test_notes_span_not_treated_as_glossary():
    """<span class=notes>(…)</span> is preserved in cleaned_md; not parsed as glossary."""
    html = """
    <div>
      कुछ पाठ <span class="notes">(मोक्ष)</span> और अधिक ।
    </div>
    """
    cleaned_md, entries = extract_shortfont(_nodes(html))

    # notes span rendered as *(मोक्ष)* by node_to_markdown
    assert "मोक्ष" in cleaned_md
    assert entries == []


# ---------------------------------------------------------------------------
# Additional: Devanagari marker_devanagari field
# ---------------------------------------------------------------------------

def test_marker_devanagari_field():
    """marker_devanagari stores Devanagari digit string."""
    html = """
    <div>
      <sup>२</sup>पूर्व का उपयोग ।
      <span class="shortFont">
        <sup>२</sup>पूर्व = पहले की ।
      </span>
    </div>
    """
    _, entries = extract_shortfont(_nodes(html))

    assert len(entries) == 1
    assert entries[0].marker_devanagari == "२"
    assert entries[0].marker_number == 2


# ---------------------------------------------------------------------------
# Additional: No shortFont span — pass-through, no mutation
# ---------------------------------------------------------------------------

def test_no_shortfont_span_passthrough():
    """When there is no shortFont span, cleaned_md equals normal markdown conversion."""
    html = """
    <div>सामान्य भावार्थ है ।</div>
    """
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert entries == []
    assert "सामान्य भावार्थ" in cleaned_md


# ---------------------------------------------------------------------------
# Top-level (sibling) <sup> markers — panchaastikaya 005.html style
# ---------------------------------------------------------------------------

def test_top_level_sup_siblings_are_stripped_and_matched():
    """When <sup> tags are top-level siblings (not nested in another tag),
    they must still be detected as anchors and stripped from cleaned_md.
    Regression: panchaastikaya 005.html structure.
    """
    html = (
        "वस्तु के <sup>१</sup>व्यतिरेकी विशेष पर्यायें हैं "
        "और <sup>२</sup>अन्वयी विशेष गुण हैं ।"
        "<span class=shortFont>"
        "<sup>१</sup>व्यतिरेक : भेद ।<br>"
        "<sup>२</sup>अन्वय : एकरूपता ।"
        "</span>"
    )
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert "१" not in cleaned_md
    assert "२" not in cleaned_md
    assert len(entries) == 2
    assert entries[0].anchor_text == "व्यतिरेकी"
    assert entries[0].occurrences and cleaned_md[
        entries[0].occurrences[0].start_offset:entries[0].occurrences[0].end_offset
    ] == "व्यतिरेकी"
    assert entries[1].anchor_text == "अन्वयी"


# ---------------------------------------------------------------------------
# Asterisk marker — panchaastikaya 006.html style
# ---------------------------------------------------------------------------

def test_asterisk_marker_round_trip():
    """A <sup>*</sup> marker matches a <sup>*</sup> glossary line."""
    html = (
        "उसे <sup>*</sup>परिवर्तन-लिंग कहा है ।"
        "<span class=shortFont>"
        "<sup>*</sup>परिवर्तन-लिंग=पुद्गलादि का परिवर्तन ।"
        "</span>"
    )
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert "*" not in cleaned_md.replace("*((", "").replace("))*", "")  # only notes-italic remain
    assert len(entries) == 1
    e = entries[0]
    assert e.marker_devanagari == "*"
    assert e.marker_number == -1
    assert e.anchor_text == "परिवर्तन-लिंग"
    assert e.is_definition is True
    assert e.occurrences and cleaned_md[
        e.occurrences[0].start_offset:e.occurrences[0].end_offset
    ] == "परिवर्तन-लिंग"


def test_inline_bracket_headers_split_onto_own_lines():
    """Multiple inline `<b>[word]</b> meaning` patterns within one paragraph
    must be split onto separate lines so the UI shabdaarth-segments parser
    detects each as a compact `[word] meaning` block.

    Source pattern (e.g. samaysaar gatha 9 jayasenacharya teeka):
        <b>[word1]</b> meaning1 <b>[word2]</b> meaning2 ...
    """
    html = (
        "<b>[<font color=maroon>जो हि</font>]</b> जो जीव ... है "
        "<b>[<font color=maroon>केवलं</font>]</b> सहाय रहित, "
        "<b>[<font color=maroon>सुद्धं</font>]</b> रागादि से रहित ।"
    )
    cleaned_md, _ = extract_shortfont(_nodes(html))
    lines = [ln for ln in cleaned_md.split("\n") if ln.strip()]
    assert len(lines) >= 3, f"expected 3+ lines, got {lines!r}"
    assert lines[0].startswith("**[") and "जो हि" in lines[0]
    assert lines[1].startswith("**[") and "केवलं" in lines[1]
    assert lines[2].startswith("**[") and "सुद्धं" in lines[2]


def test_leading_dash_in_definition_anchor_stripped():
    """A glossary line like `<sup>3</sup> – आग्रह = …` has a leading dash before the
    headword; the body word is just `आग्रह`. The dash must be stripped so the anchor
    matches the body and the offset round-trips. Regression: nikkyjain 097.html."""
    html = (
        "जहाँ <sup>३</sup>आग्रह नहीं है ।"
        "<span class=shortFont>"
        "<sup>३</sup>  – आग्रह = पकड़; ग्रहण; लगे रहना वह ।"
        "</span>"
    )
    cleaned_md, entries = extract_shortfont(_nodes(html))

    assert len(entries) == 1
    e = entries[0]
    assert e.anchor_text == "आग्रह"
    assert e.is_definition is True
    assert e.occurrences and cleaned_md[
        e.occurrences[0].start_offset:e.occurrences[0].end_offset
    ] == "आग्रह"


def test_definition_headword_falls_back_to_body_word():
    """When the glossary headword is a lemma that differs from the inflected body
    word (e.g. असहायगुणवाला vs body असहायगुणात्मक), the offset falls back to the
    annotated body token so the round-trip holds. Regression: nikkyjain 136.html."""
    html = (
        "जीव <sup>२</sup>असहायगुणात्मक है ।"
        "<span class=shortFont>"
        "<sup>२</sup>असहायगुणवाला = जिसे किसी की सहायता नहीं है ऐसे गुणवाला ।"
        "</span>"
    )
    warnings: list[str] = []
    cleaned_md, entries = extract_shortfont(_nodes(html), warnings=warnings)

    assert len(entries) == 1
    e = entries[0]
    assert "असहायगुणवाला" in e.meaning or e.meaning  # meaning retained
    assert e.anchor_text == "असहायगुणात्मक"
    assert e.occurrences and cleaned_md[
        e.occurrences[0].start_offset:e.occurrences[0].end_offset
    ] == "असहायगुणात्मक"
    assert not any("anchor_not_found" in w for w in warnings)


def test_anchor_before_cursor_recovered_via_retry():
    """Glossary order can advance the cursor past a later marker's body word that
    appears earlier in the text; the retry-from-start fallback recovers it."""
    html = (
        "<sup>२</sup>द्विअणुक छोटा है और <sup>१</sup>विस्तारसामान्यसमुदाय बड़ा है ।"
        "<span class=shortFont>"
        "<sup>१</sup>विस्तारसामान्यसमुदाय = विस्तार रूप समुदाय ।<br>"
        "<sup>२</sup>द्विअणुक = दो अणु ।"
        "</span>"
    )
    warnings: list[str] = []
    cleaned_md, entries = extract_shortfont(_nodes(html), warnings=warnings)

    by = {e.marker_number: e for e in entries}
    assert by[2].occurrences and cleaned_md[
        by[2].occurrences[0].start_offset:by[2].occurrences[0].end_offset
    ] == "द्विअणुक"
    assert not any("anchor_not_found" in w for w in warnings)


def test_plain_prose_paragraphs_stay_intact():
    """A panchaastikaya-style paragraph with `<span class=notes>` and `<sup>`
    in the middle must stay on a single line (not split per inline element)."""
    html = (
        "वास्तव में अस्तिकायों को <span class=notes>(अपनापन)</span> है । "
        "वस्तु के <sup>१</sup>व्यतिरेकी पर्यायें हैं ।<br><br>"
        "अब, कायत्व किस प्रकार है ।"
        "<span class=shortFont><sup>१</sup>व्यतिरेक=भेद ।</span>"
    )
    cleaned_md, entries = extract_shortfont(_nodes(html))
    paras = [p for p in cleaned_md.split("\n\n") if p.strip()]
    assert len(paras) == 2, f"expected 2 paragraphs, got {paras!r}"
    # First paragraph stays as one line — no splits at notes or sup
    assert "\n" not in paras[0]
    assert "अपनापन" in paras[0] and "व्यतिरेकी" in paras[0]


def test_unclosed_notes_span_does_not_swallow_following_markers():
    """An unclosed `<span class=notes>` in one glossary line nests every following
    marker inside it. Splitting by `<sup>` (document order) instead of top-level
    `<br>` must still recover each marker, and the swallowed markers' digits must
    not leak into the preceding entry's meaning. Regression: nikkyjain 108.html
    (प्रवचनसार gatha 98)."""
    html = (
        "द्रव्य <sup>५</sup>युतसिद्ध है और <sup>६</sup>प्रादेशिक भी ।"
        "<span class=shortFont>"
        # marker 5 opens a notes span and never closes it -> 6 & 7 nest inside
        "<sup>५</sup>युतसिद्ध = जुड़कर सिद्ध । <span class=notes>(जैसे लाठी ।<br>"
        "<sup>६</sup>प्रादेशिक भेद नहीं है ।<br>"
        "<sup>७</sup>अताद् = तद्रूप न होना ।"
        "</span>"
    )
    warnings: list[str] = []
    cleaned_md, entries = extract_shortfont(_nodes(html), warnings=warnings)

    by = {e.marker_number: e for e in entries}
    assert set(by) >= {5, 6, 7}, f"missing markers: {set(by)}"
    # marker 5's meaning must not contain the swallowed 6/7 digits or text
    assert "६" not in by[5].meaning and "७" not in by[5].meaning
    assert "प्रादेशिक" not in by[5].meaning
    # marker 6 (bare footnote) meaning must not start with its own digit
    assert not by[6].meaning.startswith("६")
    assert by[6].meaning.startswith("प्रादेशिक")
    assert not any("missing_glossary" in w for w in warnings)
