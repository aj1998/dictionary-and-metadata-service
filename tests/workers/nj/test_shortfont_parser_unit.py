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
