from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

# ─── Fixtures ─────────────────────────────────────────────────────────────────

_SEED_RECORDS = [
    {
        "src_nk": "द्रव्य",
        "src_label": "Keyword",
        "src_hi": "द्रव्य",
        "dst_nk": "द्रव्य:द्रव्य-के-भेद-व-लक्षण",
        "dst_label": "Topic",
        "dst_hi": "द्रव्य के भेद व लक्षण",
        "rel_type": "HAS_TOPIC",
        "weight": 1.0,
    }
]


def _make_neo4j_by_nk(records_by_nk: dict[str, list[dict]]) -> MagicMock:
    """Mock Neo4j driver that returns different records depending on the nk kwarg."""
    driver = MagicMock()

    def _make_session(*args, **kwargs):
        session_cm = MagicMock()

        async def __aenter__(*a, **kw):
            session = MagicMock()

            async def _run(*a, **kw):
                result = MagicMock()
                nk_param = kw.get("nk", "")

                async def _data():
                    for nk, records in records_by_nk.items():
                        if nk_param == nk:
                            return records
                    # default: return first value
                    return next(iter(records_by_nk.values()), [])

                result.data = _data
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
async def client_with_fallback_neo4j(request):
    """Client where only the second seed has neighbors; the first seed returns empty."""
    DATABASE_URL = os.environ.get("TEST_DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from jain_kb_common.db.postgres.base import Base  # noqa: E402

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

    from services.navigation_service.config import LANDING_SEED_KEYWORDS

    # First seed has no neighbors; only the second seed returns records.
    records_by_nk: dict[str, list[dict]] = {LANDING_SEED_KEYWORDS[0]: [], LANDING_SEED_KEYWORDS[1]: _SEED_RECORDS}
    mock_driver = _make_neo4j_by_nk(records_by_nk)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in _SETUP_STMTS:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    from services.navigation_service.main import app
    from services.navigation_service import deps
    from unittest.mock import patch

    async def _override_pg() -> AsyncSession:  # type: ignore[return]
        async with factory() as s:
            yield s

    def _override_neo4j():
        return mock_driver

    app.dependency_overrides[deps.get_session] = _override_pg
    app.dependency_overrides[deps.get_neo4j_driver] = _override_neo4j

    with patch("services.navigation_service.main.get_neo4j_driver", return_value=mock_driver):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for stmt in _TEARDOWN_STMTS:
            await conn.execute(text(stmt))
    await engine.dispose()


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("client_with_neo4j", [_SEED_RECORDS], indirect=True)
class TestLandingRandom:
    async def test_returns_focus_nk_in_seed_keywords(self, client_with_neo4j: AsyncClient):
        from services.navigation_service.config import LANDING_SEED_KEYWORDS

        r = await client_with_neo4j.get("/v1/landing/random")
        assert r.status_code == 200
        data = r.json()
        assert data["focus_nk"] in LANDING_SEED_KEYWORDS

    async def test_respects_depth_param(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing/random?depth=3")
        assert r.status_code == 200
        data = r.json()
        assert data["depth"] == 3

    async def test_default_depth_is_2(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing/random")
        assert r.status_code == 200
        data = r.json()
        assert data["depth"] == 2

    async def test_rejects_depth_5(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing/random?depth=5")
        assert r.status_code == 422

    async def test_returns_nodes_and_edges(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing/random")
        assert r.status_code == 200
        data = r.json()
        assert len(data["nodes"]) >= 1
        assert len(data["edges"]) >= 1


class TestLandingRandomFallback:
    async def test_falls_back_to_next_seed_when_first_is_empty(
        self, client_with_fallback_neo4j: AsyncClient
    ):
        from services.navigation_service.config import LANDING_SEED_KEYWORDS

        r = await client_with_fallback_neo4j.get("/v1/landing/random")
        assert r.status_code == 200
        data = r.json()
        # The first seed returns empty; the endpoint should fall back to the second
        assert data["focus_nk"] in LANDING_SEED_KEYWORDS
        assert len(data["edges"]) >= 1
