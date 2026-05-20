from __future__ import annotations

import os
import sys

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


def make_mock_mongo(docs: list[dict] | None = None) -> object:
    """Return a mock motor database that serves given docs from keyword_definitions."""
    docs = docs or []

    class FakeCursor:
        def __init__(self, data: list[dict]) -> None:
            self._docs = iter(data)

        def __aiter__(self) -> FakeCursor:
            return self

        async def __anext__(self) -> dict:
            try:
                return next(self._docs)
            except StopIteration:
                raise StopAsyncIteration

    class FakeCollection:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def find(self, query: dict, projection: dict | None = None) -> FakeCursor:
            natural_keys = query.get("natural_key", {}).get("$in", [])
            filtered = [d for d in self._data if d.get("natural_key") in natural_keys]
            return FakeCursor(filtered)

    class FakeDB:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __getitem__(self, name: str) -> FakeCollection:
            return FakeCollection(self._data)

    return FakeDB(docs)


@pytest_asyncio.fixture
async def client():  # type: ignore[return]
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_mongo = make_mock_mongo()

    from services.query_service.main import app
    from services.query_service import deps

    async def _override_pg() -> AsyncSession:  # type: ignore[return]
        async with factory() as s:
            yield s  # type: ignore[misc]

    async def _override_mongo() -> object:
        return mock_mongo

    app.dependency_overrides[deps.get_session] = _override_pg
    app.dependency_overrides[deps.get_mongo_db] = _override_mongo

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.state = factory  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()


@pytest_asyncio.fixture
async def client_with_mongo(request):  # type: ignore[return]
    """Client with injected mongo docs via request.param."""
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    docs: list[dict] = getattr(request, "param", [])
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_mongo = make_mock_mongo(docs)

    from services.query_service.main import app
    from services.query_service import deps

    async def _override_pg() -> AsyncSession:  # type: ignore[return]
        async with factory() as s:
            yield s  # type: ignore[misc]

    async def _override_mongo() -> object:
        return mock_mongo

    app.dependency_overrides[deps.get_session] = _override_pg
    app.dependency_overrides[deps.get_mongo_db] = _override_mongo

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.state = factory  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()
