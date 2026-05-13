from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)

from jain_kb_common.db.postgres.base import Base  # noqa: E402

import jain_kb_common.db.postgres.authors  # noqa: F401, E402
import jain_kb_common.db.postgres.shastras  # noqa: F401, E402
import jain_kb_common.db.postgres.anuyogas  # noqa: F401, E402
import jain_kb_common.db.postgres.teekas  # noqa: F401, E402
import jain_kb_common.db.postgres.books  # noqa: F401, E402
import jain_kb_common.db.postgres.pravachans  # noqa: F401, E402
import jain_kb_common.db.postgres.publications  # noqa: F401, E402
import jain_kb_common.db.postgres.gathas  # noqa: F401, E402
import jain_kb_common.db.postgres.keywords  # noqa: F401, E402
import jain_kb_common.db.postgres.topics  # noqa: F401, E402
import jain_kb_common.db.postgres.kalashas  # noqa: F401, E402
import jain_kb_common.db.postgres.ingestion  # noqa: F401, E402
import jain_kb_common.db.postgres.enrichment  # noqa: F401, E402
import jain_kb_common.db.postgres.query_logs  # noqa: F401, E402

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", os.environ.get("DATABASE_URL", ""))

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

os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "secret")
os.environ.setdefault("NEO4J_PASSWORD", "jainkb_password")

ADMIN_AUTH = ("admin", "secret")


def make_mock_neo4j(records: list[dict] | None = None) -> MagicMock:
    """Return a mock Neo4j driver that returns given records from any query."""
    records = records or []

    driver = MagicMock()

    def _make_session(*args, **kwargs):
        session_cm = MagicMock()

        async def __aenter__(*a, **kw):
            session = MagicMock()

            async def _run(*a, **kw):
                result = MagicMock()

                async def _data():
                    return records

                async def _single():
                    return records[0] if records else None

                result.data = _data
                result.single = _single
                return result

            session.run = _run
            return session

        async def __aexit__(*a, **kw):
            pass

        session_cm.__aenter__ = __aenter__
        session_cm.__aexit__ = __aexit__
        return session_cm

    driver.session = _make_session

    async def _close():
        pass

    driver.close = _close
    return driver


@pytest_asyncio.fixture
async def client():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_driver = make_mock_neo4j()

    from services.navigation_service.main import app
    from services.navigation_service import deps

    async def _override_pg() -> AsyncSession:  # type: ignore[return]
        async with factory() as s:
            yield s

    def _override_neo4j():
        return mock_driver

    app.dependency_overrides[deps.get_session] = _override_pg
    app.dependency_overrides[deps.get_neo4j_driver] = _override_neo4j

    # Patch lifespan Neo4j check
    with patch("services.navigation_service.main.get_neo4j_driver", return_value=mock_driver):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            c.state = factory  # type: ignore[attr-defined]
            c.neo4j = mock_driver  # type: ignore[attr-defined]
            yield c

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()


@pytest_asyncio.fixture
async def client_with_neo4j(request):
    """Client variant where Neo4j records can be injected via request.param."""
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    records = getattr(request, "param", [])
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_driver = make_mock_neo4j(records)

    from services.navigation_service.main import app
    from services.navigation_service import deps

    async def _override_pg() -> AsyncSession:  # type: ignore[return]
        async with factory() as s:
            yield s

    def _override_neo4j():
        return mock_driver

    app.dependency_overrides[deps.get_session] = _override_pg
    app.dependency_overrides[deps.get_neo4j_driver] = _override_neo4j

    with patch("services.navigation_service.main.get_neo4j_driver", return_value=mock_driver):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            c.state = factory  # type: ignore[attr-defined]
            c.neo4j = mock_driver  # type: ignore[attr-defined]
            yield c

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()
