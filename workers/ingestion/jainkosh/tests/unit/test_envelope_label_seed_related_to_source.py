"""Tests that RELATED_TO edges originate from child seeds, not parent topics."""

from pathlib import Path

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def _env_aatma():
    html = Path(__file__).parents[1].joinpath("fixtures", "आत्मा.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, "https://example.org/wiki/आत्मा", load_config())
    return build_envelope(res).would_write


def test_related_to_from_child_seed_not_parent():
    """RELATED_TO should come from the child seed key, not the parent topic key."""
    env = _env_aatma()
    edges = env["neo4j"]["edges"]

    parent_key = "आत्मा:एक-आत्मा-के-तीन-भेद-करने-का-प्रयोजन"
    bad_edges = [
        e for e in edges
        if e.get("type") == "RELATED_TO"
        and e.get("from", {}).get("key") == parent_key
    ]
    assert bad_edges == [], (
        f"RELATED_TO edges should NOT originate from parent key '{parent_key}', "
        f"but found: {bad_edges}"
    )

    child_key = "आत्मा:एक-आत्मा-के-तीन-भेद-करने-का-प्रयोजन:जीवको-आत्मा-कहनेकी-विवक्षा"
    child_edges = [
        e for e in edges
        if e.get("type") == "RELATED_TO"
        and e.get("from", {}).get("key") == child_key
        and e.get("to", {}).get("label") == "Keyword"
        and e.get("to", {}).get("key") == "जीव"
    ]
    assert len(child_edges) >= 1, (
        f"Expected at least one RELATED_TO edge from child key '{child_key}' to Keyword 'जीव', "
        f"but found none. All RELATED_TO edges: {[e for e in edges if e.get('type') == 'RELATED_TO']}"
    )
