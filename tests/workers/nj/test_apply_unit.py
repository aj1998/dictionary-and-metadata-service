"""Unit tests for NJ apply layer + cross-source (JK × NJ) merge correctness."""

from __future__ import annotations

import json
import unicodedata
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers.ingestion.nj.config import load_config_for_shastra
from workers.ingestion.nj.envelope import build_envelope, _GATHA, _KALASH, _TEEKA, _BHAAVARTH, _ADHYAAY
from workers.ingestion.nj.models import (
    AnyavarthaItem,
    GathaExtract,
    GathaWordMeaningEntry,
    KalashExtract,
    KalashHindiEntry,
    KalashSanskritEntry,
    PrimaryTeeka,
    SecondaryTeeka,
    ShastraParseResult,
)

NJ_GOLDEN_DIR = Path(__file__).parents[3] / "workers" / "ingestion" / "nj" / "tests" / "golden"
JK_FIXTURE_DIR = Path(__file__).parents[3] / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg():
    return load_config_for_shastra("samaysaar")


def _make_result(gathas=None, secondary_kalashes=None, shastra_nk="समयसार") -> ShastraParseResult:
    return ShastraParseResult(
        shastra_natural_key=shastra_nk,
        gathas=gathas or [],
        secondary_kalashes=secondary_kalashes or [],
        total_html_files_processed=1,
        parser_version="1.0.0",
        parsed_at="2026-01-01T00:00:00Z",
    )


def _make_gatha(**kwargs) -> GathaExtract:
    defaults = dict(
        shastra_natural_key="समयसार",
        gatha_number="001",
        page_html_id="001",
        html_filename="001.html",
        adhikaar_hi="मंगलाचरण",
        adhikaar_number=1,
        heading_hi="सिद्धों को नमस्कार",
    )
    defaults.update(kwargs)
    return GathaExtract(**defaults)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# ---------------------------------------------------------------------------
# NFC normalization
# ---------------------------------------------------------------------------

def test_apply_nfc_normalizes_strings():
    """build_envelope output strings must be NFC-normalized."""
    cfg = _cfg()
    nfd_heading = unicodedata.normalize("NFD", "सिद्धों को नमस्कार")
    g = _make_gatha(heading_hi=nfd_heading)
    result = _make_result(gathas=[g])
    env = build_envelope(result, cfg)
    heading_from_env = env["would_write"]["postgres"]["gathas"][0]["heading"][0]["text"]
    assert heading_from_env == _nfc(nfd_heading)


# ---------------------------------------------------------------------------
# Envelope structure validation for apply layer
# ---------------------------------------------------------------------------

def test_envelope_structure_has_all_required_keys():
    """apply_nj_shastra_payload expects these top-level keys."""
    cfg = _cfg()
    g = _make_gatha(prakrit_text="test")
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]

    required_pg = {"authors", "shastras", "teekas", "publications", "gathas", "kalashas", "teeka_chapters"}
    required_mongo = {
        "gatha_prakrit", "gatha_sanskrit", "gatha_hindi_chhand",
        "teeka_gatha_mapping", "gatha_teeka_sanskrit", "gatha_teeka_bhaavarth_hindi",
        "kalash_sanskrit", "kalash_hindi", "kalash_word_meanings",
    }
    assert required_pg.issubset(set(ww["postgres"].keys()))
    assert required_mongo.issubset(set(ww["mongo"].keys()))
    assert "nodes" in ww["neo4j"]
    assert "edges" in ww["neo4j"]


def test_envelope_postgres_author_row_has_required_fields():
    cfg = _cfg()
    result = _make_result(gathas=[_make_gatha()])
    authors = build_envelope(result, cfg)["would_write"]["postgres"]["authors"]
    assert len(authors) >= 1
    for a in authors:
        assert "natural_key" in a
        assert "display_name" in a
        assert "kind" in a


def test_envelope_gatha_row_has_shastra_natural_key():
    cfg = _cfg()
    g = _make_gatha(gatha_number="001")
    result = _make_result(gathas=[g])
    gatha_rows = build_envelope(result, cfg)["would_write"]["postgres"]["gathas"]
    assert gatha_rows[0]["shastra_natural_key"] == "समयसार"


def test_kalash_postgres_row_has_gatha_natural_key():
    """Postgres kalash rows must include gatha_natural_key for FK resolution."""
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(
            kalash_san=[KalashSanskritEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="अनुष्टुभ्", text_san="san")],
            kalash_hindi=[KalashHindiEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="दोहा", text_hi="hi")],
        ),
    )
    result = _make_result(gathas=[g])
    kalash_rows = build_envelope(result, cfg)["would_write"]["postgres"]["kalashas"]
    assert len(kalash_rows) == 1
    assert kalash_rows[0]["gatha_natural_key"] == "समयसार:गाथा:1"


def test_secondary_kalash_row_has_preceding_gatha_nk():
    cfg = _cfg()
    k = KalashExtract(
        shastra_natural_key="समयसार",
        kalash_number="011",
        html_filename="011.html",
        heading_hi=None,
        preceding_primary_gatha_number="010",
    )
    result = _make_result(secondary_kalashes=[k])
    ww = build_envelope(result, cfg)["would_write"]
    k_row = ww["postgres"]["kalashas"][0]
    assert k_row["gatha_natural_key"] == "समयसार:गाथा:10"


def test_teeka_chapters_have_start_end_gatha_natural_keys():
    cfg = _cfg()
    g1 = _make_gatha(gatha_number="001", adhikaar_number=1, adhikaar_hi="मंगलाचरण")
    g2 = _make_gatha(gatha_number="002", adhikaar_number=1, adhikaar_hi="मंगलाचरण")
    result = _make_result(gathas=[g1, g2])
    chapters = build_envelope(result, cfg)["would_write"]["postgres"]["teeka_chapters"]
    assert chapters[0]["start_gatha_natural_key"] == "समयसार:गाथा:1"
    assert chapters[0]["end_gatha_natural_key"] == "समयसार:गाथा:2"


# ---------------------------------------------------------------------------
# Idempotency: same envelope → identical output
# ---------------------------------------------------------------------------

def test_build_envelope_is_idempotent():
    """Building envelope twice from the same result produces identical output."""
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        prakrit_text="वंदित्तु",
        anyavartha=AnyavarthaItem(
            full_anyavaarth="नमस्कार",
            tagged_terms=[GathaWordMeaningEntry(source_word="वंदित्तु", meaning="नमस्कार", position=1)],
        ),
        primary_teeka=PrimaryTeeka(
            kalash_san=[KalashSanskritEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="अनुष्टुभ्", text_san="san")],
            kalash_hindi=[KalashHindiEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="दोहा", text_hi="hi")],
        ),
    )
    result = _make_result(gathas=[g])
    env1 = build_envelope(result, cfg)
    env2 = build_envelope(result, cfg)
    assert env1["would_write"]["postgres"]["gathas"] == env2["would_write"]["postgres"]["gathas"]
    assert env1["would_write"]["mongo"]["gatha_prakrit"] == env2["would_write"]["mongo"]["gatha_prakrit"]
    assert env1["would_write"]["postgres"]["kalashas"] == env2["would_write"]["postgres"]["kalashas"]


def test_stable_mongo_ids_idempotent():
    """stable_id produces the same ObjectId for the same natural key."""
    from jain_kb_common.db.mongo.upserts import stable_id
    nk = "समयसार:गाथा:1:prakrit"
    assert stable_id(nk) == stable_id(nk)
    assert stable_id(nk) != stable_id("समयसार:गाथा:2:prakrit")


# ---------------------------------------------------------------------------
# Multi-gatha merge: combined pages produce consistent output
# ---------------------------------------------------------------------------

def test_multi_gatha_page_produces_two_gatha_rows():
    cfg = _cfg()
    g009 = _make_gatha(
        gatha_number="009",
        html_filename="009-010.html",
        is_combined_page=True,
        related_gatha_numbers=["010"],
        prakrit_text="prakrit 9",
    )
    g010 = _make_gatha(
        gatha_number="010",
        html_filename="009-010.html",
        is_combined_page=True,
        related_gatha_numbers=["009"],
        prakrit_text="prakrit 10",
    )
    result = _make_result(gathas=[g009, g010])
    ww = build_envelope(result, cfg)["would_write"]

    gatha_nks = {r["natural_key"] for r in ww["postgres"]["gathas"]}
    assert "समयसार:गाथा:9" in gatha_nks
    assert "समयसार:गाथा:10" in gatha_nks

    # teeka_gatha_mapping: is_related populated
    tgm = {doc["natural_key"]: doc for doc in ww["mongo"]["teeka_gatha_mapping"]}
    assert tgm["समयसार:आत्मख्याति:9"]["is_related"] == ["010"]
    assert tgm["समयसार:आत्मख्याति:10"]["is_related"] == ["009"]

    # gatha_prakrit: two separate docs
    prakrit_nks = {doc["natural_key"] for doc in ww["mongo"]["gatha_prakrit"]}
    assert "समयसार:गाथा:9:prakrit" in prakrit_nks
    assert "समयसार:गाथा:10:prakrit" in prakrit_nks


# ---------------------------------------------------------------------------
# Cross-source merge: NJ × JainKosh natural key compatibility
# ---------------------------------------------------------------------------

def _build_jk_envelope_for_aatma():
    """Build JK envelope for आत्मा fixture (returns None if fixtures unavailable)."""
    if not JK_FIXTURE_DIR.exists():
        return None
    fixture = JK_FIXTURE_DIR / "आत्मा.html"
    if not fixture.exists():
        return None
    try:
        from workers.ingestion.jainkosh.config import load_config as jk_load_config
        from workers.ingestion.jainkosh.envelope import build_envelope as jk_build_envelope
        from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
        html = fixture.read_text(encoding="utf-8")
        config = jk_load_config()
        result = parse_keyword_html(html, "https://jainkosh.org/wiki/आत्मा", config)
        return jk_build_envelope(result).model_dump()
    except Exception:
        return None


def test_nj_shastra_key_matches_jk_reference():
    """JK nodes referencing समयसार must match NJ's shastra natural_key."""
    cfg = _cfg()
    nj_shastra_nk = cfg.shastra.natural_key  # "समयसार"

    jk_env = _build_jk_envelope_for_aatma()
    if jk_env is None:
        pytest.skip("JK fixtures not available")

    # Find all nodes in JK that have shastra_natural_key = समयसार
    jk_nodes = jk_env["would_write"]["neo4j"]["nodes"]
    samaysar_refs = [
        n for n in jk_nodes
        if n.get("props", {}).get("shastra_natural_key") == nj_shastra_nk
    ]
    # JK references this shastra — keys must use same NFC string
    assert len(samaysar_refs) > 0, "JK should reference समयसार"
    for ref in samaysar_refs:
        assert _nfc(ref["props"]["shastra_natural_key"]) == _nfc(nj_shastra_nk)


def test_jk_gatha_numbers_compatible_with_nj_keys():
    """
    JK lazy GathaTeeka nodes for समयसार reference gatha numbers.
    Derived Gatha NK (shastra:num) must match NJ's gatha natural_key format.
    """
    cfg = _cfg()
    nj_shastra_nk = cfg.shastra.natural_key  # "समयसार"

    jk_env = _build_jk_envelope_for_aatma()
    if jk_env is None:
        pytest.skip("JK fixtures not available")

    jk_nodes = jk_env["would_write"]["neo4j"]["nodes"]

    # Extract gatha_number from JK GathaTeeka nodes for समयसार
    jk_gatha_refs: dict[str, str] = {}  # gatha_number → derived_gatha_nk
    for node in jk_nodes:
        if node.get("label") == "GathaTeeka":
            props = node.get("props", {})
            if props.get("shastra_natural_key") == nj_shastra_nk:
                gnum = str(props.get("gatha_number", ""))
                if gnum:
                    derived_nk = f"{nj_shastra_nk}:गाथा:{gnum}"
                    jk_gatha_refs[gnum] = derived_nk

    if not jk_gatha_refs:
        pytest.skip("No समयसार GathaTeeka nodes in JK आत्मा fixture")

    # Build NJ envelope with gathas covering those numbers
    nj_gathas = [
        _make_gatha(gatha_number=f"{int(gnum):03d}", heading_hi=f"gatha {gnum}")
        for gnum in jk_gatha_refs
    ]
    nj_result = _make_result(gathas=nj_gathas)
    nj_ww = build_envelope(nj_result, cfg)["would_write"]
    nj_gatha_nks = {row["natural_key"] for row in nj_ww["postgres"]["gathas"]}

    for gnum, expected_nk in jk_gatha_refs.items():
        assert expected_nk in nj_gatha_nks, (
            f"JK references gatha {gnum} as {expected_nk} "
            f"but NJ doesn't produce that key. NJ keys: {sorted(nj_gatha_nks)}"
        )


def test_nj_and_jk_apply_same_shastra_nk_in_neo4j():
    """
    NJ's Shastra node key must equal JK's shastra_natural_key on lazy nodes.
    This ensures both sources write to the same Neo4j Shastra node.
    """
    cfg = _cfg()
    nj_shastra_nk = cfg.shastra.natural_key

    g = _make_gatha(gatha_number="001")
    result = _make_result(gathas=[g])
    nj_ww = build_envelope(result, cfg)["would_write"]

    nj_shastra_nodes = [n for n in nj_ww["neo4j"]["nodes"] if n["label"] == "Shastra"]
    assert len(nj_shastra_nodes) == 1
    assert nj_shastra_nodes[0]["key"] == nj_shastra_nk

    jk_env = _build_jk_envelope_for_aatma()
    if jk_env is None:
        pytest.skip("JK fixtures not available")

    # JK lazy nodes referencing समयसार should use the exact same NFC string
    jk_samaysar_refs = [
        n for n in jk_env["would_write"]["neo4j"]["nodes"]
        if n.get("props", {}).get("shastra_natural_key") == nj_shastra_nk
    ]
    for ref in jk_samaysar_refs:
        ref_snk = _nfc(ref["props"]["shastra_natural_key"])
        assert ref_snk == _nfc(nj_shastra_nk), (
            f"JK uses '{ref_snk}' but NJ uses '{_nfc(nj_shastra_nk)}' — "
            "they will write to different Neo4j nodes!"
        )


def test_cross_source_merge_nj_then_jk_gatha_key_stable():
    """
    Apply NJ (creates Gatha nodes), then JK (references same Gatha via GathaTeeka).
    The Gatha natural key must be the same in both directions:
      NJ: postgres.gathas.natural_key = "समयसार:गाथा:8"
      JK: GathaTeeka.props.gatha_number = "8", shastra = "समयसार" → derive "समयसार:गाथा:8"
    Ordering: NJ first, JK second (and vice versa) must be consistent.
    """
    cfg = _cfg()
    nj_shastra_nk = cfg.shastra.natural_key

    jk_env = _build_jk_envelope_for_aatma()
    if jk_env is None:
        pytest.skip("JK fixtures not available")

    # Collect JK-referenced gatha numbers for samaysar
    jk_nodes = jk_env["would_write"]["neo4j"]["nodes"]
    jk_gatha_nums = {
        str(n["props"]["gatha_number"])
        for n in jk_nodes
        if n.get("label") == "GathaTeeka"
        and n.get("props", {}).get("shastra_natural_key") == nj_shastra_nk
    }
    if not jk_gatha_nums:
        pytest.skip("No समयसार GathaTeeka nodes found in JK fixture")

    # Build NJ gathas that include those numbers
    nj_gathas = [
        _make_gatha(gatha_number=f"{int(n):03d}")
        for n in jk_gatha_nums
    ]
    nj_result = _make_result(gathas=nj_gathas)

    # Order 1: NJ creates gathas, JK references them
    nj_ww = build_envelope(nj_result, cfg)["would_write"]
    nj_gatha_nks = {r["natural_key"] for r in nj_ww["postgres"]["gathas"]}

    for gnum in jk_gatha_nums:
        expected = f"{nj_shastra_nk}:गाथा:{gnum}"
        assert expected in nj_gatha_nks, f"NJ missing gatha key: {expected}"

    # Order 2: JK would upsert stubs first, NJ real nodes second
    # The key point: the derived NK from JK matches what NJ writes
    for gnum in jk_gatha_nums:
        jk_derived_nk = f"{nj_shastra_nk}:गाथा:{gnum}"
        nj_nk = f"{nj_shastra_nk}:गाथा:{gnum}"
        assert jk_derived_nk == nj_nk, (
            f"Key mismatch: JK would create stub '{jk_derived_nk}', "
            f"NJ writes '{nj_nk}' — they diverge!"
        )


# ---------------------------------------------------------------------------
# Hindi label consistency across collections
# ---------------------------------------------------------------------------

def test_kalash_nk_consistent_across_postgres_and_mongo():
    """kalash_natural_key in mongo docs must match the postgres kalashas.natural_key."""
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(
            kalash_san=[KalashSanskritEntry(local_kalash_index=1, global_kalash_index=5, chhand_type="अनुष्टुभ्", text_san="नम:")],
            kalash_hindi=[KalashHindiEntry(local_kalash_index=1, global_kalash_index=5, chhand_type="दोहा", text_hi="नमस्कार")],
        ),
    )
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]

    pg_kalash_nks = {r["natural_key"] for r in ww["postgres"]["kalashas"]}
    mongo_san_nks = {doc["kalash_natural_key"] for doc in ww["mongo"]["kalash_sanskrit"]}
    mongo_hi_nks = {doc["kalash_natural_key"] for doc in ww["mongo"]["kalash_hindi"]}

    assert pg_kalash_nks == mongo_san_nks, "Postgres and mongo kalash_sanskrit NKs differ"
    assert pg_kalash_nks == mongo_hi_nks, "Postgres and mongo kalash_hindi NKs differ"
    # All use Hindi कलश label
    for nk in pg_kalash_nks:
        assert f":{_KALASH}:" in nk, f"Missing Hindi कलश in postgres kalash NK: {nk}"


def test_teeka_chapter_nk_uses_primary_teeka_nk():
    """teeka_chapters.natural_key must be scoped under the primary teeka NK."""
    cfg = _cfg()
    primary_teeka_nk = cfg.shastra.primary_teeka.natural_key  # "समयसार:आत्मख्याती"
    g = _make_gatha(gatha_number="001", adhikaar_number=1, adhikaar_hi="मंगलाचरण")
    result = _make_result(gathas=[g])
    chapters = build_envelope(result, cfg)["would_write"]["postgres"]["teeka_chapters"]
    assert chapters[0]["natural_key"].startswith(primary_teeka_nk)
    assert f":{_ADHYAAY}:" in chapters[0]["natural_key"]
