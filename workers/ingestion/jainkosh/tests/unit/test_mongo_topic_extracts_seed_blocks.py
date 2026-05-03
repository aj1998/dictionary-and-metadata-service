"""Tests that mongo topic_extracts correctly assign see_also blocks to seed nodes."""

from pathlib import Path

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def _env_aatma():
    html = Path(__file__).parents[1].joinpath("fixtures", "आत्मा.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, "https://example.org/wiki/आत्मा", load_config())
    return build_envelope(res).would_write


def test_parent_extract_has_no_row_see_also():
    """Parent topic extract should have no see_also blocks from row-style entries."""
    env = _env_aatma()
    topic_extracts = env["mongo"]["topic_extracts"]

    parent_key = "आत्मा:एक-आत्मा-के-तीन-भेद-करने-का-प्रयोजन"
    parent_extract = next(
        (t for t in topic_extracts if t["natural_key"] == parent_key), None
    )
    assert parent_extract is not None, f"Parent extract '{parent_key}' not found"

    see_also_blocks = [b for b in parent_extract["blocks"] if b.get("kind") == "see_also"]
    assert see_also_blocks == [], (
        f"Parent extract should have NO see_also blocks, got: {see_also_blocks}"
    )


def test_seed_extract_has_see_also():
    """Child seed extract should have a see_also block with correct target."""
    env = _env_aatma()
    topic_extracts = env["mongo"]["topic_extracts"]

    seed_key = "आत्मा:एक-आत्मा-के-तीन-भेद-करने-का-प्रयोजन:जीवको-आत्मा-कहनेकी-विवक्षा"
    seed_extract = next(
        (t for t in topic_extracts if t["natural_key"] == seed_key), None
    )
    assert seed_extract is not None, f"Seed extract '{seed_key}' not found"

    see_also_blocks = [b for b in seed_extract["blocks"] if b.get("kind") == "see_also"]
    assert len(see_also_blocks) == 1, (
        f"Seed extract should have exactly 1 see_also block, got: {see_also_blocks}"
    )
    assert see_also_blocks[0].get("target_keyword") == "जीव", (
        f"Expected target_keyword='जीव', got: {see_also_blocks[0].get('target_keyword')}"
    )
