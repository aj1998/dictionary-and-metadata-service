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
