"""Integration tests for phase-1b stub node behaviour.

Requires DATABASE_URL, NEO4J_URL, and NEO4J_PASSWORD env vars to be set.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "jain_kb_common"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from motor.motor_asyncio import AsyncIOMotorClient

from jain_kb_common.db.neo4j import get_driver, close_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints
from jain_kb_common.db.postgres.base import Base

import jain_kb_common.db.postgres.authors  # noqa: F401
import jain_kb_common.db.postgres.shastras  # noqa: F401
import jain_kb_common.db.postgres.anuyogas  # noqa: F401
import jain_kb_common.db.postgres.teekas  # noqa: F401
import jain_kb_common.db.postgres.books  # noqa: F401
import jain_kb_common.db.postgres.pravachans  # noqa: F401
import jain_kb_common.db.postgres.keywords  # noqa: F401
import jain_kb_common.db.postgres.gathas  # noqa: F401
import jain_kb_common.db.postgres.topics  # noqa: F401
import jain_kb_common.db.postgres.publications  # noqa: F401
import jain_kb_common.db.postgres.kalashas  # noqa: F401
import jain_kb_common.db.postgres.ingestion  # noqa: F401
import jain_kb_common.db.postgres.enrichment  # noqa: F401
import jain_kb_common.db.postgres.query_logs  # noqa: F401

from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.apply import apply_approved_keyword_payload

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")
NEO4J_URL = os.environ.get("NEO4J_URL", "")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB", "jain_kb_test")

_PG_AVAILABLE = bool(DATABASE_URL)
_NEO4J_AVAILABLE = bool(NEO4J_URL and NEO4J_PASSWORD)

skip_no_dbs = pytest.mark.skipif(
    not (_PG_AVAILABLE and _NEO4J_AVAILABLE),
    reason="DATABASE_URL or NEO4J_URL/NEO4J_PASSWORD not set",
)

TEST_DB = "neo4j"

FIXTURE_DIR = Path(__file__).parent.parent.parent / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures"

GOLDENS = {
    "आत्मा": "https://jainkosh.org/wiki/आत्मा",
    "द्रव्य": "https://jainkosh.org/wiki/द्रव्य",
    "पर्याय": "https://jainkosh.org/wiki/पर्याय",
    "वस्तु": "https://jainkosh.org/wiki/वस्तु",
}

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

_SETUP_STMTS = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS btree_gin",
    "DO $$ BEGIN CREATE TYPE author_kind AS ENUM ('acharya','gyaani','scholar','unknown'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE anuyoga_kind AS ENUM ('prathmanuyoga','karananuyoga','charananuyoga','dravyanuyoga'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE ingestion_source AS ENUM ('jainkosh','nj','vyakaran_vishleshan','cataloguesearch','cataloguesearch-chat'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE ingestion_run_status AS ENUM ('pending','running','success','partial','failed','cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE candidate_status AS ENUM ('pending','approved','rejected','merged'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
]

_TEARDOWN_STMTS = [
    "DROP TYPE IF EXISTS candidate_status CASCADE",
    "DROP TYPE IF EXISTS ingestion_run_status CASCADE",
    "DROP TYPE IF EXISTS ingestion_source CASCADE",
    "DROP TYPE IF EXISTS anuyoga_kind CASCADE",
    "DROP TYPE IF EXISTS author_kind CASCADE",
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def pg_engine():
    if not _PG_AVAILABLE:
        pytest.skip("DATABASE_URL not set")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def mongo_db():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB_NAME]
    yield db
    for coll in ["keyword_definitions", "topic_extracts", "raw_html_snapshots"]:
        await db[coll].drop()
    client.close()


@pytest_asyncio.fixture
async def neo4j_driver():
    if not _NEO4J_AVAILABLE:
        pytest.skip("NEO4J_URL/NEO4J_PASSWORD not set")
    drv = get_driver(url=NEO4J_URL, user=NEO4J_USER, password=NEO4J_PASSWORD)
    await ensure_constraints(drv, database=TEST_DB)
    yield drv
    async with drv.session(database=TEST_DB) as session:
        await session.run("MATCH (n) DETACH DELETE n")
    await close_driver()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_envelope(keyword: str) -> dict:
    from workers.ingestion.jainkosh.config import load_config
    config = load_config()
    html = (FIXTURE_DIR / f"{keyword}.html").read_text(encoding="utf-8")
    result = parse_keyword_html(html, GOLDENS[keyword], config)
    return build_envelope(result).model_dump()


async def _apply(pg_session, mongo_db, neo4j_driver, envelope: dict, run_id=None):
    await apply_approved_keyword_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        ingestion_run_id=run_id,
        neo4j_database=TEST_DB,
    )


async def _neo4j_node(drv, label: str, natural_key: str) -> dict | None:
    async with drv.session(database=TEST_DB) as session:
        result = await session.run(
            f"MATCH (n:{label} {{natural_key: $nk}}) RETURN properties(n) AS props",
            nk=natural_key,
        )
        record = await result.single()
        return dict(record["props"]) if record else None


async def _neo4j_edge_exists(drv, edge_type: str, src_nk: str, tgt_nk: str) -> bool:
    async with drv.session(database=TEST_DB) as session:
        result = await session.run(
            f"MATCH (s {{natural_key: $s}})-[r:{edge_type}]->(t {{natural_key: $t}}) "
            "RETURN count(r) AS cnt",
            s=src_nk, t=tgt_nk,
        )
        record = await result.single()
        return bool(record and record["cnt"] > 0)


async def _count_stub_nodes(drv) -> int:
    async with drv.session(database=TEST_DB) as session:
        result = await session.run("MATCH (n {is_stub: true}) RETURN count(n) AS cnt")
        record = await result.single()
        return int(record["cnt"]) if record else 0


# ---------------------------------------------------------------------------
# Test 1: resolve_by → stub Topic + edge lands
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_resolve_by_creates_topic_stub(pg_session, mongo_db, neo4j_driver):
    """
    पर्याय has an index_relation → द्रव्य at path 4.
    After applying पर्याय, a stub Topic द्रव्य:4 exists and the RELATED_TO edge lands.
    """
    env = _build_envelope("पर्याय")
    neo = env["would_write"]["neo4j"]

    # Find the stub seed for द्रव्य:4 produced by the envelope
    stub_seeds = [
        n for n in neo["nodes"]
        if n.get("is_stub_seed") and n["label"] == "Topic" and "द्रव्य" in (n.get("key") or n.get("resolve_key", ""))
    ]
    assert stub_seeds, "Expected stub seed for a द्रव्य topic cross-reference"
    stub_nk = next((n.get("key") or n.get("resolve_key")) for n in stub_seeds if (n.get("key") or n.get("resolve_key", "")).startswith("द्रव्य:4"))

    await _apply(pg_session, mongo_db, neo4j_driver, env)

    # Stub node exists with is_stub = true
    node = await _neo4j_node(neo4j_driver, "Topic", stub_nk)
    assert node is not None, f"Stub Topic {stub_nk!r} not found in Neo4j"
    assert node.get("is_stub") is True, f"Expected is_stub=true on {stub_nk!r}"

    # display_text_hi equals last segment of topic_path with hyphens → spaces
    # path "4" → last segment "4" → no hyphens → "4"
    assert node.get("display_text_hi") == "4"

    # RELATED_TO edge from the index-relation topic to the stub exists
    # Stub references use resolve_key instead of key in the edge "to" dict
    related_to_edges = [
        e for e in neo["edges"]
        if e["type"] == "RELATED_TO" and (
            e["to"].get("key") == stub_nk or e["to"].get("resolve_key") == stub_nk
        )
    ]
    assert related_to_edges, f"No RELATED_TO edge pointing to stub {stub_nk!r}"
    src_nk = related_to_edges[0]["from"]["key"]
    edge_exists = await _neo4j_edge_exists(neo4j_driver, "RELATED_TO", src_nk, stub_nk)
    assert edge_exists, f"RELATED_TO edge {src_nk!r} → {stub_nk!r} not found in Neo4j"


# ---------------------------------------------------------------------------
# Test 2: real ingestion upgrades a stub Keyword
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_real_ingestion_upgrades_stub(pg_session, mongo_db, neo4j_driver):
    """
    द्रव्य has a RELATED_TO → Keyword वस्तु.
    After applying द्रव्य, वस्तु exists as a stub.
    After applying वस्तु, is_stub flips to false.
    """
    env_dravya = _build_envelope("द्रव्य")
    neo_dravya = env_dravya["would_write"]["neo4j"]

    # Confirm वस्तु stub seed is in द्रव्य envelope
    kw_stubs = [
        n for n in neo_dravya["nodes"]
        if n.get("is_stub_seed") and n["label"] == "Keyword" and n["key"] == "वस्तु"
    ]
    assert kw_stubs, "Expected Keyword stub seed for वस्तु in द्रव्य envelope"

    await _apply(pg_session, mongo_db, neo4j_driver, env_dravya)

    # वस्तु should be a stub after द्रव्य ingestion
    vastu_before = await _neo4j_node(neo4j_driver, "Keyword", "वस्तु")
    assert vastu_before is not None, "वस्तु Keyword not found after applying द्रव्य"
    assert vastu_before.get("is_stub") is True, "Expected वस्तु to be a stub after द्रव्य"

    # Remember created_at before upgrade
    created_at_before = vastu_before.get("created_at")

    env_vastu = _build_envelope("वस्तु")
    await _apply(pg_session, mongo_db, neo4j_driver, env_vastu)

    # After applying वस्तु, is_stub should flip to false
    vastu_after = await _neo4j_node(neo4j_driver, "Keyword", "वस्तु")
    assert vastu_after is not None
    assert vastu_after.get("is_stub") is False, "Expected is_stub=false after real ingestion"
    assert vastu_after.get("stub_source") is None, "Expected stub_source=null after real ingestion"
    assert vastu_after.get("display_text") == "वस्तु", "display_text should be set by real sync"

    # created_at should be unchanged (stub creation set it, real sync keeps it)
    assert vastu_after.get("created_at") == created_at_before, "created_at should be stable"


# ---------------------------------------------------------------------------
# Test 3: stub idempotency
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_stub_idempotent(pg_session, mongo_db, neo4j_driver):
    """Applying the same keyword twice does not increase the stub node count."""
    env = _build_envelope("पर्याय")
    await _apply(pg_session, mongo_db, neo4j_driver, env)
    count_1 = await _count_stub_nodes(neo4j_driver)

    await _apply(pg_session, mongo_db, neo4j_driver, env)
    count_2 = await _count_stub_nodes(neo4j_driver)

    assert count_2 == count_1, f"Stub count grew from {count_1} to {count_2} on second apply"


# ---------------------------------------------------------------------------
# Test 4: lazy nodes (GathaTeeka etc.) get written
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_lazy_nodes_get_written(pg_session, mongo_db, neo4j_driver):
    """
    आत्मा has GathaTeeka lazy nodes and MENTIONS_TOPIC / CONTAINS_DEFINITION edges.
    After apply, those stubs exist and the edges land.
    """
    env = _build_envelope("आत्मा")
    neo = env["would_write"]["neo4j"]

    lazy_nodes = [n for n in neo["nodes"] if n.get("lazy")]
    assert lazy_nodes, "आत्मा envelope should have lazy nodes"

    mentions_edges = [e for e in neo["edges"] if e["type"] in ("MENTIONS_TOPIC", "CONTAINS_DEFINITION")]
    assert mentions_edges, "आत्मा envelope should have MENTIONS_TOPIC or CONTAINS_DEFINITION edges"

    await _apply(pg_session, mongo_db, neo4j_driver, env)

    # Each lazy node should exist in Neo4j with is_stub = true
    for node in lazy_nodes[:3]:  # spot-check first 3
        props = await _neo4j_node(neo4j_driver, node["label"], node["key"])
        assert props is not None, f"Lazy node {node['label']}:{node['key']!r} not found"
        assert props.get("is_stub") is True, f"Expected is_stub=true on lazy node {node['key']!r}"

    # At least one MENTIONS/CONTAINS edge should land
    for edge in mentions_edges[:3]:
        frm = edge["from"]
        to = edge["to"]
        exists = await _neo4j_edge_exists(neo4j_driver, edge["type"], frm["key"], to["key"])
        assert exists, (
            f"{edge['type']} edge {frm['key']!r} → {to['key']!r} not found in Neo4j"
        )


# ---------------------------------------------------------------------------
# Test 5: redlink edges are still skipped
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_redlink_still_skipped(pg_session, mongo_db, neo4j_driver):
    """
    Edges with target_exists=false (redlinks) produce no stub and no edge.
    """
    env = _build_envelope("द्रव्य")
    neo = env["would_write"]["neo4j"]

    # Ensure no edge in the envelope points to "वह वह नाम" (known redlink in द्रव्य)
    redlink_edges = [
        e for e in neo["edges"]
        if e.get("to", {}).get("key") == "वह वह नाम"
    ]
    assert redlink_edges == [], "Redlink edge to 'वह वह नाम' should not be in the envelope"

    await _apply(pg_session, mongo_db, neo4j_driver, env)

    # The redlink target node should not exist in Neo4j
    node = await _neo4j_node(neo4j_driver, "Keyword", "वह वह नाम")
    assert node is None, "Redlink target 'वह वह नाम' should not exist in Neo4j"


# ---------------------------------------------------------------------------
# Test 6: in-envelope PART_OF has is_stub=false on real topics
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_part_of_parent_present(pg_session, mongo_db, neo4j_driver):
    """
    After applying पर्याय, Topics that are in the envelope have is_stub=false
    and PART_OF edges land correctly.
    """
    env = _build_envelope("पर्याय")
    neo = env["would_write"]["neo4j"]

    part_of_edges = [e for e in neo["edges"] if e["type"] == "PART_OF"]
    assert part_of_edges, "पर्याय should have PART_OF edges"

    await _apply(pg_session, mongo_db, neo4j_driver, env)

    # Real topic nodes should have is_stub=false
    real_topic_keys = [
        n["key"] for n in neo["nodes"]
        if n["label"] == "Topic" and not n.get("is_stub_seed") and not n.get("lazy")
    ]
    assert real_topic_keys, "Expected real topic nodes in पर्याय envelope"

    for nk in real_topic_keys[:5]:  # spot-check
        props = await _neo4j_node(neo4j_driver, "Topic", nk)
        assert props is not None, f"Real Topic {nk!r} not found"
        assert props.get("is_stub") is False, f"Real Topic {nk!r} should have is_stub=false"

    # A sample PART_OF edge should exist
    sample = part_of_edges[0]
    exists = await _neo4j_edge_exists(
        neo4j_driver, "PART_OF",
        sample["from"]["key"], sample["to"]["key"],
    )
    assert exists, f"PART_OF edge not found for {sample}"
