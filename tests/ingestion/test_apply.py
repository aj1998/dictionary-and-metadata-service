"""Integration tests for apply_approved_keyword_payload.

Requires DATABASE_URL, NEO4J_URL, and NEO4J_PASSWORD env vars to be set.
Parses each golden HTML fixture to build envelopes.
All assertions are derived from the envelope itself — no hardcoded counts.
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

from sqlalchemy import text, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from motor.motor_asyncio import AsyncIOMotorClient

from jain_kb_common.db.neo4j import get_driver, close_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints
from jain_kb_common.db.postgres.base import Base
from jain_kb_common.db.postgres.keywords import Keyword, KeywordAlias
from jain_kb_common.db.postgres.topics import Topic
from jain_kb_common.db.postgres.tables import Table

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
import jain_kb_common.db.postgres.tables  # noqa: F401

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

TEST_DB = "neo4j"  # Community Edition uses the single "neo4j" database

FIXTURE_DIR = Path(__file__).parent.parent.parent / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures"

# All golden keywords with their canonical URLs
GOLDENS = [
    ("आत्मा", "https://jainkosh.org/wiki/आत्मा"),
    ("द्रव्य", "https://jainkosh.org/wiki/द्रव्य"),
    ("पर्याय", "https://jainkosh.org/wiki/पर्याय"),
    ("वस्तु",  "https://jainkosh.org/wiki/वस्तु"),
]

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
# Envelope cache
# ---------------------------------------------------------------------------

_ENVELOPE_CACHE: dict[str, dict] = {}


def _build_envelope(keyword: str, url: str) -> dict:
    from workers.ingestion.jainkosh.config import load_config
    config = load_config()
    html_path = FIXTURE_DIR / f"{keyword}.html"
    html = html_path.read_text(encoding="utf-8")
    result = parse_keyword_html(html, url, config)
    return build_envelope(result).model_dump()


def get_envelope(keyword: str, url: str) -> dict:
    if keyword not in _ENVELOPE_CACHE:
        _ENVELOPE_CACHE[keyword] = _build_envelope(keyword, url)
    return _ENVELOPE_CACHE[keyword]


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
    for coll in ["keyword_definitions", "topic_extracts", "raw_html_snapshots", "tables"]:
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
# Helper
# ---------------------------------------------------------------------------

async def _apply(pg_session, mongo_db, neo4j_driver, envelope: dict, run_id=None):
    await apply_approved_keyword_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        ingestion_run_id=run_id,
        neo4j_database=TEST_DB,
    )


# ---------------------------------------------------------------------------
# Test 1: idempotent apply — applying twice does not grow row counts
# ---------------------------------------------------------------------------

@skip_no_dbs
@pytest.mark.parametrize("keyword,url", GOLDENS)
async def test_apply_idempotent_full_envelope(keyword, url, pg_session, mongo_db, neo4j_driver):
    envelope = get_envelope(keyword, url)
    ww = envelope["would_write"]
    run_id = uuid.uuid4()

    await _apply(pg_session, mongo_db, neo4j_driver, envelope, run_id)

    kw_count_1 = (await pg_session.execute(select(sqlfunc.count()).select_from(Keyword))).scalar()
    topic_count_1 = (await pg_session.execute(select(sqlfunc.count()).select_from(Topic))).scalar()
    alias_count_1 = (await pg_session.execute(select(sqlfunc.count()).select_from(KeywordAlias))).scalar()
    mongo_kdef_count_1 = await mongo_db.keyword_definitions.count_documents({})
    mongo_te_count_1 = await mongo_db.topic_extracts.count_documents({})

    await _apply(pg_session, mongo_db, neo4j_driver, envelope, run_id)

    kw_count_2 = (await pg_session.execute(select(sqlfunc.count()).select_from(Keyword))).scalar()
    topic_count_2 = (await pg_session.execute(select(sqlfunc.count()).select_from(Topic))).scalar()
    alias_count_2 = (await pg_session.execute(select(sqlfunc.count()).select_from(KeywordAlias))).scalar()
    mongo_kdef_count_2 = await mongo_db.keyword_definitions.count_documents({})
    mongo_te_count_2 = await mongo_db.topic_extracts.count_documents({})

    assert kw_count_2 == kw_count_1, f"[{keyword}] keywords grew on second apply"
    assert topic_count_2 == topic_count_1, f"[{keyword}] topics grew on second apply"
    assert alias_count_2 == alias_count_1, f"[{keyword}] keyword_aliases grew on second apply"
    assert mongo_kdef_count_2 == mongo_kdef_count_1, f"[{keyword}] keyword_definitions grew on second apply"
    assert mongo_te_count_2 == mongo_te_count_1, f"[{keyword}] topic_extracts grew on second apply"

    expected_topics = len(ww["postgres"]["topics"])
    assert topic_count_1 == expected_topics, (
        f"[{keyword}] expected {expected_topics} topics from envelope, got {topic_count_1}"
    )


# ---------------------------------------------------------------------------
# Test 2: parent_topic_id populated for all topics that have a parent
# ---------------------------------------------------------------------------

@skip_no_dbs
@pytest.mark.parametrize("keyword,url", GOLDENS)
async def test_apply_topics_parents_first(keyword, url, pg_session, mongo_db, neo4j_driver):
    envelope = get_envelope(keyword, url)
    ww = envelope["would_write"]

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    topics_with_parent = [
        row for row in ww["postgres"]["topics"]
        if row.get("parent_topic_natural_key")
    ]

    if not topics_with_parent:
        pytest.skip(f"[{keyword}] envelope has no topics with parent_topic_natural_key")

    for row in topics_with_parent:
        tnk = row["natural_key"]
        result = await pg_session.execute(
            select(Topic.parent_topic_id).where(Topic.natural_key == tnk)
        )
        parent_topic_id = result.scalar_one_or_none()
        assert parent_topic_id is not None, (
            f"[{keyword}] Topic {tnk!r} has parent_topic_natural_key="
            f"{row['parent_topic_natural_key']!r} but parent_topic_id is NULL in DB"
        )


# ---------------------------------------------------------------------------
# Test 3: alias dedup — applying twice does not grow alias count
# ---------------------------------------------------------------------------

@skip_no_dbs
@pytest.mark.parametrize("keyword,url", GOLDENS)
async def test_apply_alias_dedup(keyword, url, pg_session, mongo_db, neo4j_driver):
    envelope = get_envelope(keyword, url)
    ww = envelope["would_write"]
    keyword_nk = ww["postgres"]["keywords"][0]["natural_key"]
    aliases_in_envelope = [
        a for a in ww["postgres"].get("keyword_aliases", [])
        if (a.get("alias_text") or a.get("alias"))
    ]

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    kw_res = await pg_session.execute(select(Keyword.id).where(Keyword.natural_key == keyword_nk))
    keyword_id = kw_res.scalar_one()

    count_1 = (await pg_session.execute(
        select(sqlfunc.count()).select_from(KeywordAlias).where(KeywordAlias.keyword_id == keyword_id)
    )).scalar()

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    count_2 = (await pg_session.execute(
        select(sqlfunc.count()).select_from(KeywordAlias).where(KeywordAlias.keyword_id == keyword_id)
    )).scalar()

    assert count_2 == count_1, (
        f"[{keyword}] keyword_aliases grew from {count_1} to {count_2} on second apply"
    )
    assert count_1 == len(aliases_in_envelope), (
        f"[{keyword}] expected {len(aliases_in_envelope)} aliases from envelope, got {count_1}"
    )


# ---------------------------------------------------------------------------
# Table test helpers
# ---------------------------------------------------------------------------

def _minimal_envelope(keyword_nk: str, tables: list | None = None) -> dict:
    return {
        "would_write": {
            "postgres": {
                "keywords": [{"natural_key": keyword_nk, "source_url": None}],
                "topics": [],
                "keyword_aliases": [],
            },
            "mongo": {
                "keyword_definitions": [{
                    "natural_key": keyword_nk,
                    "page_sections": [],
                    "redirect_aliases": [],
                    "source_url": None,
                }],
                "topic_extracts": [],
            },
            "neo4j": {
                "nodes": [{"label": "Keyword", "key": keyword_nk, "props": {"display_text": keyword_nk}}],
                "edges": [],
            },
        },
        "tables": tables or [],
    }


def _make_table(parent_nk: str, parent_kind: str, seq: int = 1, **kwargs) -> dict:
    base: dict = {
        "natural_key": f"table:jainkosh:{parent_nk}:{seq:02d}",
        "seq": seq,
        "parent_natural_key": parent_nk,
        "parent_kind": parent_kind,
        "source_url": None,
        "caption": [],
        "raw_html": "<table><tr><td>X</td></tr></table>",
        "cells": [["X"]],
        "header_rows": 0,
        "plaintext": "X",
        "mentioned_keyword_natural_keys": [],
        "mentioned_topic_natural_keys": [],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Test 4: table persisted to Postgres
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_apply_persists_table_to_postgres(pg_session, mongo_db, neo4j_driver):
    kw_nk = "test_table_pg_kw"
    table = _make_table(kw_nk, "keyword")
    table_nk = table["natural_key"]
    envelope = _minimal_envelope(kw_nk, tables=[table])

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    result = await pg_session.execute(select(Table).where(Table.natural_key == table_nk))
    row = result.scalar_one_or_none()
    assert row is not None, f"Expected Table row with natural_key={table_nk!r}"
    assert row.parent_natural_key == kw_nk
    assert row.raw_html_doc_id is not None and row.raw_html_doc_id != ""


# ---------------------------------------------------------------------------
# Test 5: table persisted to Mongo with table_id and cells round-trip
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_apply_persists_table_to_mongo(pg_session, mongo_db, neo4j_driver):
    kw_nk = "test_table_mongo_kw"
    cells = [["A", "B"], ["C", "D"]]
    table = _make_table(kw_nk, "keyword", cells=cells)
    table_nk = table["natural_key"]
    envelope = _minimal_envelope(kw_nk, tables=[table])

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    doc = await mongo_db.tables.find_one({"natural_key": table_nk})
    assert doc is not None, f"Expected Mongo doc with natural_key={table_nk!r}"
    assert doc.get("table_id") is not None and doc["table_id"] != ""
    assert doc.get("cells") == cells


# ---------------------------------------------------------------------------
# Test 6: Neo4j Table node + CONTAINS_TABLE edge created
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_apply_creates_table_node_and_contains_edge_in_neo4j(pg_session, mongo_db, neo4j_driver):
    kw_nk = "test_table_neo4j_kw"
    table = _make_table(kw_nk, "keyword")
    table_nk = table["natural_key"]
    envelope = _minimal_envelope(kw_nk, tables=[table])

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    async with neo4j_driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (p:Keyword {natural_key: $pnk})-[:CONTAINS_TABLE]->(t:Table {natural_key: $tnk}) RETURN t",
            pnk=kw_nk, tnk=table_nk,
        )
        records = [r async for r in result]
    assert len(records) == 1, "Expected exactly 1 CONTAINS_TABLE edge from Keyword to Table"


# ---------------------------------------------------------------------------
# Test 7: MENTIONS_KEYWORD + MENTIONS_TOPIC stub edges created
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_apply_table_mention_edges(pg_session, mongo_db, neo4j_driver):
    kw_nk = "test_table_mentions_kw"
    table = _make_table(
        kw_nk, "keyword",
        mentioned_keyword_natural_keys=["other_kw_stub"],
        mentioned_topic_natural_keys=["some_topic_stub"],
    )
    table_nk = table["natural_key"]
    envelope = _minimal_envelope(kw_nk, tables=[table])

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    async with neo4j_driver.session(database=TEST_DB) as session:
        r1 = await session.run(
            "MATCH (t:Table {natural_key: $tnk})-[:MENTIONS_KEYWORD]->(k:Keyword {natural_key: $kw}) RETURN k",
            tnk=table_nk, kw="other_kw_stub",
        )
        kw_records = [r async for r in r1]

        r2 = await session.run(
            "MATCH (t:Table {natural_key: $tnk})-[:MENTIONS_TOPIC]->(tp:Topic {natural_key: $tp}) RETURN tp",
            tnk=table_nk, tp="some_topic_stub",
        )
        tp_records = [r async for r in r2]

    assert len(kw_records) == 1, "Expected MENTIONS_KEYWORD edge from Table to Keyword stub"
    assert len(tp_records) == 1, "Expected MENTIONS_TOPIC edge from Table to Topic stub"


# ---------------------------------------------------------------------------
# Test 8: table apply is idempotent (double apply → no growth)
# ---------------------------------------------------------------------------

@skip_no_dbs
async def test_apply_table_idempotent(pg_session, mongo_db, neo4j_driver):
    kw_nk = "test_table_idem_kw"
    table = _make_table(kw_nk, "keyword")
    envelope = _minimal_envelope(kw_nk, tables=[table])

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    pg_count_1 = (await pg_session.execute(select(sqlfunc.count()).select_from(Table))).scalar()
    mongo_count_1 = await mongo_db.tables.count_documents({})

    await _apply(pg_session, mongo_db, neo4j_driver, envelope)

    pg_count_2 = (await pg_session.execute(select(sqlfunc.count()).select_from(Table))).scalar()
    mongo_count_2 = await mongo_db.tables.count_documents({})

    assert pg_count_2 == pg_count_1, f"Table PG rows grew from {pg_count_1} to {pg_count_2} on second apply"
    assert mongo_count_2 == mongo_count_1, f"Mongo tables grew from {mongo_count_1} to {mongo_count_2} on second apply"
