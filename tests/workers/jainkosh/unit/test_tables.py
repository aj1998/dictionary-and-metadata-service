"""Unit tests for table block extraction/attachment behavior."""

from pathlib import Path

import pytest

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import walk_subsection_tree
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

FIXTURE_DIR = Path("workers/ingestion/jainkosh/tests/fixtures")


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def load_fixture():
    def _load(name: str):
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")
    return _load


def test_table_attaches_to_current_subsection(load_fixture, config):
    result = parse_keyword_html(
        load_fixture("द्रव्य.html"),
        "https://jainkosh.org/wiki/द्रव्य",
        config,
    )
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")

    found = []
    for sub in walk_subsection_tree(sk.subsections):
        for b in sub.blocks:
            if b.kind == "table":
                found.append((sub, b))

    assert len(found) >= 1
    _, tbl = found[0]
    assert tbl.raw_html and tbl.raw_html.lstrip().startswith("<table")

    assert all(
        b.kind != "table" or b.raw_html != tbl.raw_html
        for b in sk.extra_blocks
    )


def test_table_extra_blocks_preserved_for_orphan_tables(config):
    html = """
    <div class="mw-parser-output">
      <h2><span class="mw-headline" id="सिद्धांतकोष_से">…</span></h2>
      <table><tbody><tr><td>x</td></tr></tbody></table>
    </div>
    """
    result = parse_keyword_html(html, "https://example/d", config)
    sec = result.page_sections[0]
    assert len(sec.extra_blocks) == 1 and sec.extra_blocks[0].kind == "table"
    assert sec.subsections == []


def test_attach_to_section_root_override(load_fixture, config):
    config.table.attach_to = "section_root"
    result = parse_keyword_html(
        load_fixture("द्रव्य.html"),
        "https://jainkosh.org/wiki/द्रव्य",
        config,
    )
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    assert any(b.kind == "table" for b in sk.extra_blocks)
