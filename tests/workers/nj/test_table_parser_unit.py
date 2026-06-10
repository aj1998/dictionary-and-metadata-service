"""Unit tests for workers/ingestion/nj/tables.py (Phase 2)."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from workers.ingestion.nj.shortfont_parser import extract_shortfont
from workers.ingestion.nj.tables import extract_tables_from_bhaavarth

_FIXTURES = Path(__file__).parent / "fixtures"
_PARENT_NK = "पञ्चास्तिकाय:अमृतचंद्र:नि:गाथा:टीका:भावार्थ:7"
_EXPECTED_TABLE_NK = f"table:nj:{_PARENT_NK}:01"


def _fragment_nodes() -> list[NavigableString | Tag]:
    """Load bhaavarth nodes from the 007 fixture."""
    html = (_FIXTURES / "panchaastikaay_007_fragment.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    wrapper = soup.find("div", id="fragment")
    assert wrapper is not None
    return list(wrapper.children)


def _make_simple_table_html(caption: str | None = None, header_rows: int = 1) -> str:
    rows = ""
    if caption:
        rows += f'<tr><td class="empty"></td><th colspan="2">{caption}</th></tr>'
    rows += "<tr><th>कॉलम १</th><th>कॉलम २</th></tr>"
    rows += "<tr><td>मान १</td><td>मान २</td></tr>"
    rows += "<tr><td>मान ३</td><td>मान ४</td></tr>"
    return f"<table>{rows}</table>"


def test_rowspan_expands_into_each_spanned_row():
    """A rowspan=N cell duplicates its text into each of the N rows so columns stay aligned."""
    html = (
        '<div id="w">'
        "<table>"
        "<tr><th>group</th><th>k</th><th>v</th></tr>"
        '<tr><td rowspan="3">A</td><td>1</td><td>x</td></tr>'
        "<tr><td>2</td><td>y</td></tr>"
        "<tr><td>3</td><td>z</td></tr>"
        '<tr><td rowspan="2">B</td><td>1</td><td>p</td></tr>'
        "<tr><td>2</td><td>q</td></tr>"
        "</table>"
        "</div>"
    )
    soup = BeautifulSoup(html, "lxml")
    nodes = list(soup.find("div", id="w").children)
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key=_PARENT_NK,
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert len(tables) == 1
    cells = tables[0].cells
    assert all(len(r) == 3 for r in cells), cells
    assert cells[1] == ["A", "1", "x"]
    assert cells[2] == ["A", "2", "y"]
    assert cells[3] == ["A", "3", "z"]
    assert cells[4] == ["B", "1", "p"]
    assert cells[5] == ["B", "2", "q"]


def test_extracts_single_table_from_bhaavarth_nodes():
    nodes = _fragment_nodes()
    mutated, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key=_PARENT_NK,
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert len(tables) == 1


def test_table_replaced_by_md_link():
    nodes = _fragment_nodes()
    mutated, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key=_PARENT_NK,
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    cleaned_md, _ = extract_shortfont(mutated)
    assert f"[तालिका देखें](table://{_EXPECTED_TABLE_NK})" in cleaned_md
    assert "<table" not in cleaned_md
    assert "सत्ता-लक्षण परक" not in cleaned_md


def test_natural_key_format_and_seq_per_parent():
    nodes = _fragment_nodes()
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key=_PARENT_NK,
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert tables[0].natural_key == _EXPECTED_TABLE_NK
    assert tables[0].seq == 1
    assert tables[0].parent_natural_key == _PARENT_NK


def test_caption_detected_from_single_th_first_row():
    """First row with one non-empty <th> alongside empty <td> → caption."""
    nodes = _fragment_nodes()
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key=_PARENT_NK,
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert len(tables[0].caption) == 1
    assert "सारिणी" in tables[0].caption[0].text


def test_header_rows_count():
    """After extracting the caption row, the next all-<th> row is header_rows=1."""
    nodes = _fragment_nodes()
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key=_PARENT_NK,
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert tables[0].header_rows == 1


def test_table_type_is_index():
    nodes = _fragment_nodes()
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key=_PARENT_NK,
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert tables[0].table_type == "index"


def test_no_table_when_only_layout_wrapper():
    """A myAltColTable with a single <td> and no inner table is skipped."""
    html = """
    <div>
      Some text.
      <table class="myAltColTable"><tr><td>only cell</td></tr></table>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    wrapper = soup.find("div")
    nodes = list(wrapper.children)
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key="test:parent",
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert tables == []


def test_shortfont_offsets_remain_valid_after_table_replacement():
    """Shortfont markers in the same bhaavarth as the table get correct offsets."""
    html = """
    <div>
      <table><tr><th>head</th></tr><tr><td>cell</td></tr></table>
      वह <sup>*</sup>मोक्ष-मार्ग है
      <span class="shortFont"><sup>*</sup>मोक्ष-मार्ग = मोक्ष का रास्ता</span>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    nodes = list(soup.find("div").children)
    mutated, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key="test:parent",
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert len(tables) == 1
    cleaned_md, sf_entries = extract_shortfont(mutated)
    assert "मोक्ष-मार्ग" in cleaned_md
    # shortfont entries should be resolved
    if sf_entries:
        for entry in sf_entries:
            for occ in entry.occurrences:
                assert 0 <= occ.start_offset < occ.end_offset <= len(cleaned_md)


def test_two_tables_get_sequential_seq():
    """Two structural tables in the same bhaavarth get seq 1 and 2."""
    html = """
    <div>
      <table><tr><th>T1 head</th></tr><tr><td>r1</td></tr></table>
      <br/>
      <table><tr><th>T2 head</th></tr><tr><td>r2</td></tr></table>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    nodes = list(soup.find("div").children)
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key="test:parent",
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert len(tables) == 2
    assert tables[0].seq == 1
    assert tables[1].seq == 2
    assert tables[0].natural_key.endswith(":01")
    assert tables[1].natural_key.endswith(":02")


def test_single_tr_table_skipped():
    """Table with only one <tr> is not structural and should be skipped."""
    html = "<div><table><tr><td>just one row</td></tr></table></div>"
    soup = BeautifulSoup(html, "lxml")
    nodes = list(soup.find("div").children)
    _, tables = extract_tables_from_bhaavarth(
        nodes,
        parent_natural_key="test:parent",
        parent_kind="gatha_teeka_bhaavarth",
        source_url=None,
    )
    assert tables == []
