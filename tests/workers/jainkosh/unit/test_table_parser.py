"""Unit tests for Phase 2 ParsedTable parser."""

from __future__ import annotations

from pathlib import Path

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.tables import parse_table_block, parse_table_block_from_html

FIXTURE_DIR = Path("workers/ingestion/jainkosh/tests/fixtures")


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def load_fixture():
    def _load(name: str):
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")
    return _load


# ---------------------------------------------------------------------------
# Test 1: parse cell matrix from inline HTML fixture
# ---------------------------------------------------------------------------

_SIMPLE_TABLE_HTML = """
<table>
  <tbody>
    <tr><th>स्तम्भ १</th><th>स्तम्भ २</th></tr>
    <tr><td>मूल्य अ</td><td>मूल्य ब</td></tr>
    <tr><td>मूल्य स</td><td>मूल्य द</td></tr>
  </tbody>
</table>
"""

_CAPTION_TABLE_HTML = """
<table>
  <caption>तालिका शीर्षक</caption>
  <tbody>
    <tr><th>हेडर</th></tr>
    <tr><td>डेटा</td></tr>
  </tbody>
</table>
"""


def test_parses_cell_matrix_from_fixture(config):
    tree = HTMLParser(_SIMPLE_TABLE_HTML)
    table_node = tree.css_first("table")
    assert table_node is not None

    block, parsed = parse_table_block(
        table_node,
        config,
        parent_natural_key="द्रव्य:षट्द्रव्य",
        parent_kind="topic",
        seq=1,
        source_url="https://jainkosh.org/wiki/द्रव्य#3",
        preceding_heading="षट्द्रव्य विभाजन",
    )

    assert block.kind == "table"
    assert block.raw_html is not None

    # cells: 3 rows × 2 cols
    assert len(parsed.cells) == 3
    assert parsed.cells[0] == ["स्तम्भ १", "स्तम्भ २"]
    assert parsed.cells[1] == ["मूल्य अ", "मूल्य ब"]
    assert parsed.cells[2] == ["मूल्य स", "मूल्य द"]

    # header_rows: first row is all <th>
    assert parsed.header_rows == 1

    # caption: falls back to preceding_heading since no <caption> element
    assert len(parsed.caption) == 1
    assert parsed.caption[0].text == "षट्द्रव्य विभाजन"
    assert parsed.caption[0].lang == "hin"
    assert parsed.caption[0].script == "Deva"

    # natural_key
    assert parsed.natural_key == "table:jainkosh:द्रव्य:षट्द्रव्य:01"
    assert parsed.seq == 1
    assert parsed.parent_natural_key == "द्रव्य:षट्द्रव्य"
    assert parsed.parent_kind == "topic"

    # plaintext should be non-empty
    assert parsed.plaintext != ""


def test_inline_caption_preferred_over_heading(config):
    tree = HTMLParser(_CAPTION_TABLE_HTML)
    table_node = tree.css_first("table")

    _, parsed = parse_table_block(
        table_node,
        config,
        parent_natural_key="जीव",
        parent_kind="keyword",
        seq=1,
        preceding_heading="कोई शीर्षक",
    )

    # Inline <caption> should win over preceding_heading
    assert len(parsed.caption) == 1
    assert parsed.caption[0].text == "तालिका शीर्षक"


# ---------------------------------------------------------------------------
# Test 2: mention extraction from <a> hrefs
# ---------------------------------------------------------------------------

_MENTIONS_TABLE_HTML = """
<table>
  <tbody>
    <tr>
      <td><a href="/wiki/जीव">जीव</a></td>
      <td><a href="#बहिरात्मादि_3_भेद">बहिरात्मा</a></td>
      <td>सामान्य</td>
    </tr>
  </tbody>
</table>
"""


def test_collects_mentioned_keywords_and_topics(config):
    tree = HTMLParser(_MENTIONS_TABLE_HTML)
    table_node = tree.css_first("table")

    _, parsed = parse_table_block(
        table_node,
        config,
        parent_natural_key="आत्मा",
        parent_kind="topic",
        seq=1,
    )

    assert parsed.mentioned_keyword_natural_keys == ["जीव"]
    assert parsed.mentioned_topic_natural_keys == ["बहिरात्मादि_3_भेद"]


def test_no_mentions_when_disabled(config):
    config.table.parse_mentions = False
    tree = HTMLParser(_MENTIONS_TABLE_HTML)
    table_node = tree.css_first("table")

    _, parsed = parse_table_block(
        table_node,
        config,
        parent_natural_key="आत्मा",
        parent_kind="topic",
        seq=1,
    )

    assert parsed.mentioned_keyword_natural_keys == []
    assert parsed.mentioned_topic_natural_keys == []


# ---------------------------------------------------------------------------
# Test 3: natural_key and seq assignment
# ---------------------------------------------------------------------------

_TWO_TABLES_HTML = """
<div class="mw-parser-output">
  <h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
  <span class="HindiText" id="1"><strong>प्रथम</strong></span>
  <table><tbody><tr><td>तालिका १</td></tr></tbody></table>
  <table><tbody><tr><td>तालिका २</td></tr></tbody></table>
</div>
"""


def test_natural_key_and_seq(config):
    result = parse_keyword_html(_TWO_TABLES_HTML, "https://jainkosh.org/wiki/द्रव्य", config)
    envelope = build_envelope(result, config)

    assert len(envelope.tables) == 2

    t1, t2 = envelope.tables
    assert t1.seq == 1
    assert t1.natural_key.endswith(":01")
    assert t2.seq == 2
    assert t2.natural_key.endswith(":02")

    # Same parent
    assert t1.parent_natural_key == t2.parent_natural_key


# ---------------------------------------------------------------------------
# Test 4: full fixture round-trip → envelope.tables populated
# ---------------------------------------------------------------------------


def test_envelope_includes_tables(load_fixture, config):
    result = parse_keyword_html(
        load_fixture("द्रव्य.html"),
        "https://jainkosh.org/wiki/द्रव्य",
        config,
    )
    envelope = build_envelope(result, config)

    assert len(envelope.tables) >= 1, "expected at least one table in द्रव्य envelope"

    # Check the first table's structure
    tbl = envelope.tables[0]
    assert tbl.natural_key.startswith("table:jainkosh:")
    assert tbl.parent_kind == "topic"
    assert tbl.raw_html.lstrip().startswith("<table")
    assert len(tbl.cells) >= 1
    assert tbl.plaintext != ""
    assert tbl.seq >= 1


# ---------------------------------------------------------------------------
# Test 5: GRef spans in table cells are extracted as cell_refs and stripped
# ---------------------------------------------------------------------------

_GREF_TABLE_HTML = """
<table>
  <tbody>
    <tr>
      <th>स्तम्भ <span class="GRef">( कषायपाहुड़ 1/1-14/177/211-215 )</span></th>
      <th>अन्य</th>
    </tr>
    <tr>
      <td>मूल्य</td>
      <td>बिना संदर्भ</td>
    </tr>
  </tbody>
</table>
"""


def test_cell_refs_extracted_from_gref_spans(config):
    """GRef spans inside cells produce Reference objects in cell_refs and are stripped from text."""
    tree = HTMLParser(_GREF_TABLE_HTML)
    table_node = tree.css_first("table")

    _, parsed = parse_table_block(
        table_node,
        config,
        parent_natural_key="द्रव्य:षट्द्रव्य",
        parent_kind="topic",
        seq=1,
    )

    # cell_refs shape: rows × cols × refs
    assert len(parsed.cell_refs) == 2, "should have same row count as cells"
    assert len(parsed.cell_refs[0]) == 2, "should have same col count as cells"

    # Header cell with GRef should have one ref extracted
    header_cell_refs = parsed.cell_refs[0][0]
    assert len(header_cell_refs) >= 1, "expected at least one ref from GRef span"
    assert header_cell_refs[0].text != "", "ref text should be non-empty"

    # Cell without GRef should have empty ref list
    assert parsed.cell_refs[0][1] == []
    assert parsed.cell_refs[1][0] == []


def test_cell_text_stripped_of_gref_content(config):
    """GRef text should be removed from the cell text string when cell_refs are extracted."""
    tree = HTMLParser(_GREF_TABLE_HTML)
    table_node = tree.css_first("table")

    _, parsed = parse_table_block(
        table_node,
        config,
        parent_natural_key="द्रव्य:षट्द्रव्य",
        parent_kind="topic",
        seq=1,
    )

    # GRef text must not appear in the cell text
    header_text = parsed.cells[0][0]
    assert "कषायपाहुड़" not in header_text, "GRef text leaked into cell text"
    assert "स्तम्भ" in header_text, "prose text should remain"


def test_dravya_fixture_cell_refs_and_clean_text(load_fixture, config):
    """Integration: द्रव्य table header cells have GRef refs extracted and clean cell text."""
    result = parse_keyword_html(
        load_fixture("द्रव्य.html"),
        "https://jainkosh.org/wiki/द्रव्य",
        config,
    )
    envelope = build_envelope(result, config)

    tbl = envelope.tables[0]

    # The first row header cells (col 1 and col 2) had embedded GRef spans
    assert len(tbl.cell_refs) == len(tbl.cells), "cell_refs row count must match cells"

    # Row 0 col 1: "द्रव्य की अपेक्षा( कषायपाहुड़ … )" — GRef text should be stripped
    header_col1_text = tbl.cells[0][1]
    assert "कषायपाहुड़" not in header_col1_text, "GRef leaked into cell text (col 1)"

    # Row 0 col 1 refs should include the resolved कषायपाहुड़ reference
    col1_refs = tbl.cell_refs[0][1]
    assert len(col1_refs) >= 1, "expected ref from GRef in col 1 header"
    ref_texts = [r.text for r in col1_refs]
    assert any("कषायपाहुड़" in t for t in ref_texts), f"कषायपाहुड़ ref not found in {ref_texts}"


# ---------------------------------------------------------------------------
# Test 6: build_cell_reference_edges emits MENTIONS_TABLE edges
# ---------------------------------------------------------------------------

_KNOWN_SHASTRA_GREF_TABLE_HTML = """
<table>
  <tbody>
    <tr>
      <th>विषय <span class="GRef">( पंचास्तिकाय / 10 )</span></th>
      <th>स्पष्टीकरण</th>
    </tr>
    <tr>
      <td>सामान्य</td>
      <td>विशेष</td>
    </tr>
  </tbody>
</table>
"""


def test_build_cell_reference_edges_emits_mentions_table(config):
    """build_cell_reference_edges emits MENTIONS_TABLE edge from Gatha/etc. to Table."""
    from workers.ingestion.jainkosh.reference_edges import build_cell_reference_edges
    from selectolax.parser import HTMLParser
    from workers.ingestion.jainkosh.tables import parse_table_block

    tree = HTMLParser(_KNOWN_SHASTRA_GREF_TABLE_HTML)
    table_node = tree.css_first("table")

    _, parsed = parse_table_block(
        table_node,
        config,
        parent_natural_key="द्रव्य:षट्द्रव्य",
        parent_kind="topic",
        seq=1,
    )

    table_target = {"label": "Table", "key": parsed.natural_key}
    # Collect all refs from all cells
    all_edges = []
    for row_idx, row in enumerate(parsed.cell_refs):
        for col_idx, cell_refs in enumerate(row):
            if not cell_refs:
                continue
            edges = build_cell_reference_edges(
                cell_refs,
                target=table_target,
                edge_type="MENTIONS_TABLE",
                config=config,
                mention_path=f"{parsed.natural_key}/{row_idx}/{col_idx}",
                source_natural_key=parsed.natural_key,
            )
            all_edges.extend(edges)

    assert len(all_edges) >= 1, "expected at least one MENTIONS_TABLE edge"
    for edge in all_edges:
        assert edge["type"] == "MENTIONS_TABLE"
        assert edge["to"]["label"] == "Table"
        assert edge["to"]["key"] == parsed.natural_key
        # Source must be a reference node (Gatha/Kalash/Page)
        assert edge["from"]["label"] in {"Gatha", "GathaTeeka", "Kalash", "KalashBhaavarth", "Page"}
        assert "mention_path" in edge["props"]
        assert "source_natural_key" in edge["props"]


def test_envelope_neo4j_includes_mentions_table_edges(load_fixture, config):
    """Integration: द्रव्य envelope's would_write.neo4j contains MENTIONS_TABLE edges."""
    result = parse_keyword_html(
        load_fixture("द्रव्य.html"),
        "https://jainkosh.org/wiki/द्रव्य",
        config,
    )
    envelope = build_envelope(result, config)
    neo4j = envelope.would_write["neo4j"]
    edges = neo4j["edges"]
    nodes = neo4j["nodes"]

    mentions_table_edges = [e for e in edges if e.get("type") == "MENTIONS_TABLE"]
    assert len(mentions_table_edges) >= 1, (
        "expected MENTIONS_TABLE edges from table cell GRef citations in द्रव्य"
    )

    # Every MENTIONS_TABLE edge must point to a Table node
    for edge in mentions_table_edges:
        assert edge["to"]["label"] == "Table"
        assert edge["to"]["key"].startswith("table:jainkosh:")
        assert edge["from"]["label"] in {"Gatha", "GathaTeeka", "Kalash", "KalashBhaavarth", "Page"}

    # Lazy nodes for the reference targets must be present
    lazy_labels = {n["label"] for n in nodes if n.get("lazy")}
    ref_labels = {e["from"]["label"] for e in mentions_table_edges}
    assert ref_labels.issubset({"Gatha", "GathaTeeka", "Kalash", "KalashBhaavarth", "Page"})
    # All from-labels in MENTIONS_TABLE edges should have corresponding lazy nodes
    for edge in mentions_table_edges:
        from_key = edge["from"]["key"]
        matching_lazy = [n for n in nodes if n.get("lazy") and n.get("key") == from_key]
        assert matching_lazy, f"no lazy node found for MENTIONS_TABLE from-key {from_key}"
