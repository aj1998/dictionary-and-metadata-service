"""Assert that apply_nj_shastra_payload stamps sources=['nj'] on every row it creates."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from motor.motor_asyncio import AsyncIOMotorClient

from jain_kb_common.db.neo4j import get_driver, close_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints
from jain_kb_common.db.postgres.base import Base
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.postgres.kalashas import Kalash
from jain_kb_common.db.postgres.publications import Publication
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.teeka_chapters import TeekaChapter
from jain_kb_common.db.postgres.teekas import Teeka

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
import jain_kb_common.db.postgres.teeka_chapters  # noqa: F401

from workers.ingestion.nj.apply import apply_nj_shastra_payload

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

GOLDEN_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "workers" / "ingestion" / "nj" / "tests" / "golden"
    / "समयसार_golden_o0_l10.json"
)

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
    for coll in [
        "gatha_prakrit", "gatha_sanskrit", "gatha_hindi_chhand",
        "teeka_gatha_mapping", "gatha_teeka_sanskrit",
        "gatha_teeka_bhaavarth_hindi", "gatha_teeka_bhaavarth_shortfont",
        "kalash_sanskrit", "kalash_hindi", "kalash_word_meanings",
        "kalash_bhaavarth_shortfont", "tables",
    ]:
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


@pytest_asyncio.fixture
async def nj_envelope():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@skip_no_dbs
@pytest.mark.asyncio
async def test_nj_entities_have_nj_source(pg_session, mongo_db, neo4j_driver, nj_envelope):
    """gathas, kalashas, teeka_chapters, publications must have sources=['nj'];
    shastras, teekas, authors must have sources containing 'nj'."""

    await apply_nj_shastra_payload(
        envelope=nj_envelope,
        pg_session=pg_session,
        mongo_db=mongo_db,
        neo4j_driver=neo4j_driver,
        neo4j_database=TEST_DB,
    )

    pg = nj_envelope["would_write"]["postgres"]

    # Tables that must have exactly ['nj'] in a fresh DB
    for model, label, expected_nks in [
        (Gatha, "gathas", [r["natural_key"] for r in pg.get("gathas", [])]),
        (Kalash, "kalashas", [r["natural_key"] for r in pg.get("kalashas", [])]),
        (TeekaChapter, "teeka_chapters", [r["natural_key"] for r in pg.get("teeka_chapters", [])]),
        (Publication, "publications", [r["natural_key"] for r in pg.get("publications", [])]),
    ]:
        if not expected_nks:
            continue
        rows = (await pg_session.execute(select(model))).scalars().all()
        assert len(rows) == len(expected_nks), (
            f"{label}: expected {len(expected_nks)} rows, got {len(rows)}"
        )
        for row in rows:
            assert row.sources == ["nj"], (
                f"{label} row {row.natural_key!r}: expected sources=['nj'], got {row.sources!r}"
            )

    # Tables where sources must contain 'nj' (may have other values if pre-seeded)
    for model, label, expected_nks in [
        (Shastra, "shastras", [r["natural_key"] for r in pg.get("shastras", [])]),
        (Teeka, "teekas", [r["natural_key"] for r in pg.get("teekas", [])]),
        (Author, "authors", [r["natural_key"] for r in pg.get("authors", [])]),
    ]:
        if not expected_nks:
            continue
        rows = (await pg_session.execute(select(model))).scalars().all()
        assert len(rows) == len(expected_nks), (
            f"{label}: expected {len(expected_nks)} rows, got {len(rows)}"
        )
        for row in rows:
            assert "nj" in row.sources, (
                f"{label} row {row.natural_key!r}: 'nj' missing in sources={row.sources!r}"
            )
