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


def make_mock_neo4j(
    traverse_rows: list[dict] | None = None,
    neighbor_rows: list[dict] | None = None,
) -> object:
    """Return a mock Neo4j async driver that returns preset rows."""
    traverse_rows = traverse_rows or []
    neighbor_rows = neighbor_rows or []

    class FakeResult:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        async def data(self) -> list[dict]:
            return list(self._rows)

        def __aiter__(self) -> "FakeResult":
            self._iter = iter(self._rows)
            return self

        async def __anext__(self) -> dict:
            try:
                return next(self._iter)  # type: ignore[attr-defined]
            except StopIteration:
                raise StopAsyncIteration

    class FakeSession:
        def __init__(self, t_rows: list[dict], n_rows: list[dict]) -> None:
            self._t_rows = t_rows
            self._n_rows = n_rows

        async def run(self, cypher: str, **kwargs: object) -> FakeResult:
            # Distinguish traverse (uses MATCH p =) vs neighbors
            if "MATCH p =" in cypher:
                return FakeResult(self._t_rows)
            return FakeResult(self._n_rows)

        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakeDriver:
        def __init__(self, t_rows: list[dict], n_rows: list[dict]) -> None:
            self._t_rows = t_rows
            self._n_rows = n_rows

        def session(self, database: str | None = None) -> FakeSession:
            return FakeSession(self._t_rows, self._n_rows)

    return FakeDriver(traverse_rows, neighbor_rows)


def make_mock_neo4j_subworkflow(
    topics_in_shastra_rows: list[dict] | None = None,
    shastras_for_topic_rows: list[dict] | None = None,
) -> object:
    """Mock Neo4j driver for subworkflow endpoints (topics_in_shastra, shastras_for_topic).

    Dispatches by inspecting the Cypher string:
      - queries containing 'MENTIONS_TOPIC]->(t:Topic)'  → topics_in_shastra_rows
      - queries containing 'MENTIONS_TOPIC]-(g:Gatha)'   → shastras_for_topic_rows
    """
    topics_rows = topics_in_shastra_rows or []
    shastras_rows = shastras_for_topic_rows or []

    class FakeResult:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        async def data(self) -> list[dict]:
            return list(self._rows)

        def __aiter__(self) -> "FakeResult":
            self._iter = iter(self._rows)
            return self

        async def __anext__(self) -> dict:
            try:
                return next(self._iter)  # type: ignore[attr-defined]
            except StopIteration:
                raise StopAsyncIteration

    class FakeSession:
        def __init__(self, t_rows: list[dict], s_rows: list[dict]) -> None:
            self._t_rows = t_rows
            self._s_rows = s_rows

        async def run(self, cypher: str, **kwargs: object) -> FakeResult:
            if "MENTIONS_TOPIC]->(t:Topic)" in cypher:
                return FakeResult(self._t_rows)
            return FakeResult(self._s_rows)

        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    class FakeDriver:
        def __init__(self, t_rows: list[dict], s_rows: list[dict]) -> None:
            self._t_rows = t_rows
            self._s_rows = s_rows

        def session(self, database: str | None = None) -> FakeSession:
            return FakeSession(self._t_rows, self._s_rows)

    return FakeDriver(topics_rows, shastras_rows)


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


@pytest_asyncio.fixture
async def client_with_neo4j(request):  # type: ignore[return]
    """Client with injected Postgres + Mongo + Neo4j mocks.

    Pass (mongo_docs, traverse_rows, neighbor_rows) via request.param.
    """
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    params = getattr(request, "param", ([], [], []))
    mongo_docs: list[dict] = params[0] if len(params) > 0 else []
    traverse_rows: list[dict] = params[1] if len(params) > 1 else []
    neighbor_rows: list[dict] = params[2] if len(params) > 2 else []

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_mongo = make_mock_mongo(mongo_docs)
    mock_neo4j = make_mock_neo4j(traverse_rows, neighbor_rows)

    from services.query_service.main import app
    from services.query_service import deps

    async def _override_pg() -> AsyncSession:  # type: ignore[return]
        async with factory() as s:
            yield s  # type: ignore[misc]

    async def _override_mongo() -> object:
        return mock_mongo

    def _override_neo4j() -> object:
        return mock_neo4j

    app.dependency_overrides[deps.get_session] = _override_pg
    app.dependency_overrides[deps.get_mongo_db] = _override_mongo
    app.dependency_overrides[deps.get_neo4j_driver] = _override_neo4j

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
async def client_with_neo4j_subworkflow(request):  # type: ignore[return]
    """Client for subworkflow endpoints (topics_in_shastra, shastras_for_topic).

    Pass (topics_in_shastra_rows, shastras_for_topic_rows) via request.param.
    """
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    params = getattr(request, "param", ([], []))
    topics_rows: list[dict] = params[0] if len(params) > 0 else []
    shastras_rows: list[dict] = params[1] if len(params) > 1 else []

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_mongo = make_mock_mongo()
    mock_neo4j = make_mock_neo4j_subworkflow(topics_rows, shastras_rows)

    from services.query_service.main import app
    from services.query_service import deps

    async def _override_pg() -> AsyncSession:  # type: ignore[return]
        async with factory() as s:
            yield s  # type: ignore[misc]

    async def _override_mongo() -> object:
        return mock_mongo

    def _override_neo4j() -> object:
        return mock_neo4j

    app.dependency_overrides[deps.get_session] = _override_pg
    app.dependency_overrides[deps.get_mongo_db] = _override_mongo
    app.dependency_overrides[deps.get_neo4j_driver] = _override_neo4j

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.state = factory  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()
