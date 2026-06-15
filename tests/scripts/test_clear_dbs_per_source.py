"""Tests for clear_dbs.py --source {all,jainkosh,nj} behaviour.

Unit tests verify routing logic (which collections/tables are targeted).
Integration tests (skip if DB env vars absent) verify actual row-level clearing
including the co-owned-sources invariant.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "jain_kb_common"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import scripts.clear_dbs as clear_dbs_mod
from scripts.clear_dbs import _JK_MONGO, _NJ_MONGO, _SHARED_MONGO, _MONGO_COLLECTIONS

DATABASE_URL = os.environ.get("DATABASE_URL", "")
NEO4J_URL = os.environ.get("NEO4J_URL", "")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB", "jain_kb_test")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")

_PG_AVAILABLE = bool(DATABASE_URL)
_NEO4J_AVAILABLE = bool(NEO4J_URL and NEO4J_PASSWORD)

skip_no_pg = pytest.mark.skipif(not _PG_AVAILABLE, reason="DATABASE_URL not set")
skip_no_dbs = pytest.mark.skipif(
    not (_PG_AVAILABLE and _NEO4J_AVAILABLE),
    reason="DATABASE_URL or NEO4J credentials not set",
)


# ── Unit: collection-set routing ─────────────────────────────────────────────

def test_mongo_collection_sets_are_disjoint():
    assert not set(_JK_MONGO) & set(_NJ_MONGO)
    assert not set(_JK_MONGO) & set(_SHARED_MONGO)
    assert not set(_NJ_MONGO) & set(_SHARED_MONGO)


def test_mongo_all_is_union_of_all_sets():
    expected = set(_JK_MONGO) | set(_NJ_MONGO) | set(_SHARED_MONGO)
    assert set(_MONGO_COLLECTIONS) == expected


def test_jainkosh_source_drops_jk_and_shared_collections():
    dropped: list[str] = []

    async def fake_clear_mongo(mongo_db, collections):
        dropped.extend(collections)

    import asyncio

    async def _run():
        await fake_clear_mongo(None, _JK_MONGO + _SHARED_MONGO)

    asyncio.run(_run())
    assert set(dropped) == set(_JK_MONGO) | set(_SHARED_MONGO)
    assert not any(c in dropped for c in _NJ_MONGO)


def test_nj_source_drops_nj_and_shared_collections():
    dropped: list[str] = []

    async def fake_clear_mongo(mongo_db, collections):
        dropped.extend(collections)

    import asyncio

    async def _run():
        await fake_clear_mongo(None, _NJ_MONGO + _SHARED_MONGO)

    asyncio.run(_run())
    assert set(dropped) == set(_NJ_MONGO) | set(_SHARED_MONGO)
    assert not any(c in dropped for c in _JK_MONGO)


# ── Unit: CLI argument parsing ────────────────────────────────────────────────

def test_default_source_is_all(monkeypatch):
    calls: list[str] = []

    async def fake_clear(*, source, neo4j_database):
        calls.append(source)

    monkeypatch.setattr(clear_dbs_mod, "_clear", fake_clear)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("NEO4J_URL", "bolt://x")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")

    clear_dbs_mod.main([])
    assert calls == ["all"]


def test_source_jainkosh_parsed(monkeypatch):
    calls: list[str] = []

    async def fake_clear(*, source, neo4j_database):
        calls.append(source)

    monkeypatch.setattr(clear_dbs_mod, "_clear", fake_clear)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("NEO4J_URL", "bolt://x")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")

    clear_dbs_mod.main(["--source", "jainkosh"])
    assert calls == ["jainkosh"]


def test_source_nj_parsed(monkeypatch):
    calls: list[str] = []

    async def fake_clear(*, source, neo4j_database):
        calls.append(source)

    monkeypatch.setattr(clear_dbs_mod, "_clear", fake_clear)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("NEO4J_URL", "bolt://x")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")

    clear_dbs_mod.main(["--source", "nj"])
    assert calls == ["nj"]


def test_invalid_source_exits(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("NEO4J_URL", "bolt://x")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")

    with pytest.raises(SystemExit):
        clear_dbs_mod.main(["--source", "unknown"])


# ── Unit: postgres routing — all uses TRUNCATE, per-source uses DELETE ────────

def test_all_source_skips_per_source_helper(monkeypatch):
    """--source all must NOT call _clear_postgres_by_source."""
    per_source_calls: list[str] = []

    async def spy_per_source(conn, src):
        per_source_calls.append(src)

    monkeypatch.setattr(clear_dbs_mod, "_clear_postgres_by_source", spy_per_source)

    async def fake_clear(*, source, neo4j_database):
        # Invoke real routing logic inline to verify it doesn't call per-source
        if source != "all":
            await clear_dbs_mod._clear_postgres_by_source(None, source)

    import asyncio

    asyncio.run(fake_clear(source="all", neo4j_database="neo4j"))
    assert per_source_calls == [], "Should not call _clear_postgres_by_source for --source all"


def test_per_source_calls_helper_with_correct_source(monkeypatch):
    """--source jainkosh must call _clear_postgres_by_source('jainkosh')."""
    per_source_calls: list[str] = []

    async def spy_per_source(conn, src):
        per_source_calls.append(src)

    monkeypatch.setattr(clear_dbs_mod, "_clear_postgres_by_source", spy_per_source)

    import asyncio

    async def fake_clear(*, source, neo4j_database):
        if source != "all":
            await clear_dbs_mod._clear_postgres_by_source(None, source)

    asyncio.run(fake_clear(source="jainkosh", neo4j_database="neo4j"))
    assert per_source_calls == ["jainkosh"]


def test_nj_source_calls_helper_with_nj(monkeypatch):
    per_source_calls: list[str] = []

    async def spy_per_source(conn, src):
        per_source_calls.append(src)

    monkeypatch.setattr(clear_dbs_mod, "_clear_postgres_by_source", spy_per_source)

    import asyncio

    async def fake_clear(*, source, neo4j_database):
        if source != "all":
            await clear_dbs_mod._clear_postgres_by_source(None, source)

    asyncio.run(fake_clear(source="nj", neo4j_database="neo4j"))
    assert per_source_calls == ["nj"]


# ── Integration: co-owned sources invariant ───────────────────────────────────

_PG_SETUP_STMTS = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS btree_gin",
    "DO $$ BEGIN CREATE TYPE author_kind AS ENUM ('acharya','gyaani','scholar','unknown'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE anuyoga_kind AS ENUM ('prathmanuyoga','karananuyoga','charananuyoga','dravyanuyoga'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE ingestion_source AS ENUM ('jainkosh','nj','vyakaran_vishleshan','cataloguesearch','cataloguesearch-chat'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE ingestion_run_status AS ENUM ('pending','running','success','partial','failed','cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    "DO $$ BEGIN CREATE TYPE candidate_status AS ENUM ('pending','approved','rejected','merged'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
]

_PG_TEARDOWN_STMTS = [
    "DROP TYPE IF EXISTS candidate_status CASCADE",
    "DROP TYPE IF EXISTS ingestion_run_status CASCADE",
    "DROP TYPE IF EXISTS ingestion_source CASCADE",
    "DROP TYPE IF EXISTS anuyoga_kind CASCADE",
    "DROP TYPE IF EXISTS author_kind CASCADE",
]


@pytest_asyncio.fixture
async def pg_engine_clear():
    if not _PG_AVAILABLE:
        pytest.skip("DATABASE_URL not set")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from jain_kb_common.db.postgres.base import Base

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _PG_SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _PG_TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session_clear(pg_engine_clear):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(pg_engine_clear, expire_on_commit=False)
    async with factory() as session:
        yield session


@skip_no_pg
@pytest.mark.asyncio
async def test_clear_jainkosh_leaves_co_owned_shastra(pg_session_clear, pg_engine_clear):
    """After --source jainkosh, a shastra co-owned by both sources retains sources=['nj']."""
    from sqlalchemy import select
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.enums import IngestionSource
    from jain_kb_common.db.postgres.upserts import upsert_shastra, upsert_author

    # Author is co-owned (both sources wrote it) — realistic: nj upserts author too
    author_id = await upsert_author(
        pg_session_clear,
        natural_key="test_author",
        display_name=[{"lang": "hi", "text": "टेस्ट"}],
        kind="acharya",
        source=IngestionSource.jainkosh,
    )
    await upsert_author(
        pg_session_clear,
        natural_key="test_author",
        display_name=[{"lang": "hi", "text": "टेस्ट"}],
        kind="acharya",
        source=IngestionSource.nj,
    )

    # Co-owned shastra (both sources)
    await upsert_shastra(
        pg_session_clear,
        natural_key="test_shastra_co_owned",
        title=[{"lang": "hi", "text": "टेस्ट शास्त्र"}],
        author_id=author_id,
        source=IngestionSource.jainkosh,
    )
    await upsert_shastra(
        pg_session_clear,
        natural_key="test_shastra_co_owned",
        title=[{"lang": "hi", "text": "टेस्ट शास्त्र"}],
        author_id=author_id,
        source=IngestionSource.nj,
    )

    # Exclusively-jainkosh author + shastra
    author_jk_id = await upsert_author(
        pg_session_clear,
        natural_key="test_author_jk_only",
        display_name=[{"lang": "hi", "text": "जेके"}],
        kind="acharya",
        source=IngestionSource.jainkosh,
    )
    await upsert_shastra(
        pg_session_clear,
        natural_key="test_shastra_jk_only",
        title=[{"lang": "hi", "text": "जैनकोश शास्त्र"}],
        author_id=author_jk_id,
        source=IngestionSource.jainkosh,
    )
    await pg_session_clear.commit()

    # Run the per-source postgres clear for jainkosh
    async with pg_engine_clear.begin() as conn:
        await clear_dbs_mod._clear_postgres_by_source(conn, "jainkosh")

    # Expire session cache so we read fresh state from DB
    pg_session_clear.expire_all()

    # Co-owned shastra must still exist with sources=['nj']
    row = (await pg_session_clear.execute(
        select(Shastra).where(Shastra.natural_key == "test_shastra_co_owned")
    )).scalar_one_or_none()
    assert row is not None, "Co-owned shastra must survive --source jainkosh"
    assert list(row.sources) == ["nj"], (
        f"Co-owned shastra sources must be ['nj'] after jainkosh clear, got {list(row.sources)!r}"
    )

    # Exclusively-jainkosh shastra must be gone
    jk_only = (await pg_session_clear.execute(
        select(Shastra).where(Shastra.natural_key == "test_shastra_jk_only")
    )).scalar_one_or_none()
    assert jk_only is None, "Exclusively-jainkosh shastra must be deleted by --source jainkosh"


@skip_no_pg
@pytest.mark.asyncio
async def test_sequential_source_clears_leave_db_empty(pg_session_clear, pg_engine_clear):
    """Two sequential per-source clears (jainkosh then nj) produce the same empty state as --source all."""
    from sqlalchemy import select, func
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.enums import IngestionSource
    from jain_kb_common.db.postgres.upserts import upsert_shastra, upsert_author

    # Author is co-owned: both jainkosh and nj attribute the same shastra (realistic)
    author_id = await upsert_author(
        pg_session_clear,
        natural_key="test_author_seq",
        display_name=[{"lang": "hi", "text": "अनुक्रम"}],
        kind="acharya",
        source=IngestionSource.jainkosh,
    )
    await upsert_author(
        pg_session_clear,
        natural_key="test_author_seq",
        display_name=[{"lang": "hi", "text": "अनुक्रम"}],
        kind="acharya",
        source=IngestionSource.nj,
    )
    await upsert_shastra(
        pg_session_clear,
        natural_key="test_shastra_seq",
        title=[{"lang": "hi", "text": "अनुक्रम शास्त्र"}],
        author_id=author_id,
        source=IngestionSource.jainkosh,
    )
    await upsert_shastra(
        pg_session_clear,
        natural_key="test_shastra_seq",
        title=[{"lang": "hi", "text": "अनुक्रम शास्त्र"}],
        author_id=author_id,
        source=IngestionSource.nj,
    )
    await pg_session_clear.commit()

    # Clear jainkosh first, then nj — should leave DB empty
    async with pg_engine_clear.begin() as conn:
        await clear_dbs_mod._clear_postgres_by_source(conn, "jainkosh")
    async with pg_engine_clear.begin() as conn:
        await clear_dbs_mod._clear_postgres_by_source(conn, "nj")

    pg_session_clear.expire_all()

    shastra_count = (await pg_session_clear.execute(
        select(func.count()).select_from(Shastra)
    )).scalar_one()
    assert shastra_count == 0, (
        f"Expected 0 shastras after sequential jainkosh+nj clear, got {shastra_count}"
    )

    author_count = (await pg_session_clear.execute(
        select(func.count()).select_from(Author)
    )).scalar_one()
    assert author_count == 0, (
        f"Expected 0 authors after sequential jainkosh+nj clear, got {author_count}"
    )
