from pathlib import Path

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def _env(name):
    html = Path(__file__).parents[1].joinpath("fixtures", f"{name}.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, f"https://example.org/wiki/{name}", load_config())
    return build_envelope(res).would_write


def test_no_keyword_edge_to_redlink_target_dravya():
    edges = _env("द्रव्य")["neo4j"]["edges"]
    bad = [e for e in edges if e.get("to", {}).get("key") == "वह वह नाम"]
    assert bad == [], bad


def test_redlink_edge_absent_for_index_relations():
    edges = _env("द्रव्य")["neo4j"]["edges"]
    for e in edges:
        if e.get("type") == "RELATED_TO":
            assert e.get("props", {}).get("target_exists", True) is not False


def test_redlink_see_also_block_still_present():
    html = Path(__file__).parents[1].joinpath("fixtures", "आत्मा.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, "https://example.org/wiki/आत्मा", load_config())

    def _walk(s):
        for x in s:
            yield x
            yield from _walk(x.children)

    found = False
    for sec in res.page_sections:
        for sub in _walk(sec.subsections):
            for b in sub.blocks:
                if b.kind == "see_also" and b.target_exists is False:
                    found = True
    assert found, "redlink see_also block was lost — only the edge should be suppressed"
