"""Integration tests for NJ table apply (Phase 3).

Tests that apply_nj_shastra_payload correctly persists ParsedTable data to
Postgres, Mongo, and Neo4j, and creates the CONTAINS_TABLE edge.

Requires DATABASE_URL, NEO4J_URL/NEO4J_PASSWORD, and MONGO_URL env vars.
"""

from __future__ import annotations

import os
import sys
import uuid

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

from workers.ingestion.nj.apply import apply_nj_shastra_payload

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

# ---------------------------------------------------------------------------
# Minimal NJ envelope builder
# ---------------------------------------------------------------------------

_SHASTRA_NK = "पञ्चास्तिकाय"
_TEEKA_NK = f"{_SHASTRA_NK}:टीका:nj"
_PUB_NK = f"{_TEEKA_NK}:pub"
_GATHA_NK = f"{_SHASTRA_NK}:गाथा:1"
_BHAAVARTH_NK = f"{_PUB_NK}:गाथा:टीका:भावार्थ:1"
_KALASH_NK = f"{_TEEKA_NK}:कलश:1"
_KALASH_BHAAVARTH_NK = f"{_PUB_NK}:कलश:भावार्थ:1"


def _make_table(
    natural_key: str,
    parent_natural_key: str,
    parent_kind: str,
    table_type: str = "index",
    seq: int = 0,
) -> dict:
    return {
        "natural_key": natural_key,
        "seq": seq,
        "parent_natural_key": parent_natural_key,
        "parent_kind": parent_kind,
        "table_type": table_type,
        "source_url": None,
        "caption": [],
        "raw_html": "<table><tr><td>test</td></tr></table>",
        "cells": [["test"]],
        "cell_refs": [[[]]],
        "header_rows": 0,
        "plaintext": "test",
        "mentioned_keyword_natural_keys": [],
        "mentioned_topic_natural_keys": [],
    }


def _make_minimal_envelope(tables: list[dict]) -> dict:
    """Build a minimal NJ would_write envelope containing only the given tables."""
    return {
        "would_write": {
            "postgres": {
                "authors": [],
                "shastras": [],
                "teekas": [],
                "publications": [],
                "gathas": [],
                "kalashas": [],
                "teeka_chapters": [],
            },
            "mongo": {
                "gatha_prakrit": [],
                "gatha_sanskrit": [],
                "gatha_hindi_chhand": [],
                "teeka_gatha_mapping": [],
                "gatha_teeka_sanskrit": [],
                "gatha_teeka_bhaavarth_hindi": [],
                "gatha_teeka_bhaavarth_shortfont": [],
                "kalash_sanskrit": [],
                "kalash_hindi": [],
                "kalash_word_meanings": [],
                "kalash_bhaavarth_shortfont": [],
            },
            "neo4j": {"nodes": [], "edges": []},
            "tables": tables,
        }
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
    await db["tables"].drop()
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
# Tests
# ---------------------------------------------------------------------------

@skip_no_dbs
@pytest.mark.asyncio
async def test_apply_persists_nj_table_to_postgres(pg_session, mongo_db, neo4j_driver):
    """NJ table is written to Postgres with source='nj', table_type='index', parent_kind='gatha_teeka_bhaavarth'."""
    table_nk = f"{_BHAAVARTH_NK}:table:0"
    envelope = _make_minimal_envelope([
        _make_table(table_nk, _BHAAVARTH_NK, "gatha_teeka_bhaavarth", table_type="index"),
    ])

    await apply_nj_shastra_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        neo4j_database=TEST_DB,
    )

    row = (await pg_session.execute(
        select(Table).where(Table.natural_key == table_nk)
    )).scalar_one()

    assert row.source.value == "nj"
    assert row.table_type == "index"
    assert row.parent_kind == "gatha_teeka_bhaavarth"
    assert row.parent_natural_key == _BHAAVARTH_NK


@skip_no_dbs
@pytest.mark.asyncio
async def test_apply_persists_nj_table_to_mongo(pg_session, mongo_db, neo4j_driver):
    """NJ table is written to Mongo with cells, raw_html, and table_type fields."""
    table_nk = f"{_BHAAVARTH_NK}:table:0"
    envelope = _make_minimal_envelope([
        _make_table(table_nk, _BHAAVARTH_NK, "gatha_teeka_bhaavarth", table_type="index"),
    ])

    await apply_nj_shastra_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        neo4j_database=TEST_DB,
    )

    doc = await mongo_db["tables"].find_one({"natural_key": table_nk})
    assert doc is not None
    assert doc["table_type"] == "index"
    assert doc["raw_html"] == "<table><tr><td>test</td></tr></table>"
    assert doc["cells"] == [["test"]]


@skip_no_dbs
@pytest.mark.asyncio
async def test_apply_creates_contains_table_edge_from_bhaavarth_node(pg_session, mongo_db, neo4j_driver):
    """CONTAINS_TABLE edge is created from GathaTeekaBhaavarth to Table node."""
    table_nk = f"{_BHAAVARTH_NK}:table:0"
    envelope = _make_minimal_envelope([
        _make_table(table_nk, _BHAAVARTH_NK, "gatha_teeka_bhaavarth", table_type="index"),
    ])

    await apply_nj_shastra_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        neo4j_database=TEST_DB,
    )

    async with neo4j_driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (b:GathaTeekaBhaavarth {natural_key: $nk})-[:CONTAINS_TABLE]->(t:Table) "
            "RETURN t.natural_key AS tnk, t.table_type AS ttype",
            nk=_BHAAVARTH_NK,
        )
        records = [r async for r in result]

    assert len(records) == 1
    assert records[0]["tnk"] == table_nk
    assert records[0]["ttype"] == "index"


@skip_no_dbs
@pytest.mark.asyncio
async def test_apply_nj_table_idempotent(pg_session, mongo_db, neo4j_driver):
    """Applying the same NJ envelope twice produces exactly one PG row and one Neo4j edge."""
    table_nk = f"{_BHAAVARTH_NK}:table:0"
    envelope = _make_minimal_envelope([
        _make_table(table_nk, _BHAAVARTH_NK, "gatha_teeka_bhaavarth", table_type="index"),
    ])

    await apply_nj_shastra_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        neo4j_database=TEST_DB,
    )
    await apply_nj_shastra_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        neo4j_database=TEST_DB,
    )

    pg_count = (await pg_session.execute(
        select(sqlfunc.count()).select_from(Table).where(Table.natural_key == table_nk)
    )).scalar()
    assert pg_count == 1

    async with neo4j_driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (b:GathaTeekaBhaavarth {natural_key: $nk})-[r:CONTAINS_TABLE]->(:Table) "
            "RETURN count(r) AS cnt",
            nk=_BHAAVARTH_NK,
        )
        edge_count = (await result.single())["cnt"]

    assert edge_count == 1


@skip_no_dbs
@pytest.mark.asyncio
async def test_kalash_bhaavarth_parent(pg_session, mongo_db, neo4j_driver):
    """NJ table with KalashBhaavarth parent creates CONTAINS_TABLE edge from KalashBhaavarth node."""
    table_nk = f"{_KALASH_BHAAVARTH_NK}:table:0"
    envelope = _make_minimal_envelope([
        _make_table(table_nk, _KALASH_BHAAVARTH_NK, "kalash_bhaavarth", table_type="index"),
    ])

    await apply_nj_shastra_payload(
        envelope=envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        neo4j_database=TEST_DB,
    )

    row = (await pg_session.execute(
        select(Table).where(Table.natural_key == table_nk)
    )).scalar_one()
    assert row.source.value == "nj"
    assert row.parent_kind == "kalash_bhaavarth"

    async with neo4j_driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (b:KalashBhaavarth {natural_key: $nk})-[:CONTAINS_TABLE]->(t:Table) "
            "RETURN t.natural_key AS tnk",
            nk=_KALASH_BHAAVARTH_NK,
        )
        records = [r async for r in result]

    assert len(records) == 1
    assert records[0]["tnk"] == table_nk
