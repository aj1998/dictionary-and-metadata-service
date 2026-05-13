from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def browse_data(client: AsyncClient):
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.gathas import Gatha
    from jain_kb_common.db.postgres.kalashas import Kalash
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.teekas import Teeka

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="kundkund",
            display_name=[{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
            kind="acharya",
        )
        teekakar = Author(
            natural_key="amritchandra",
            display_name=[{"lang": "hin", "script": "Deva", "text": "अमृतचंद्राचार्य"}],
            kind="acharya",
        )
        session.add_all([author, teekakar])
        await session.flush()

        shastra = Shastra(
            natural_key="pravachansaar",
            title=[{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        teeka = Teeka(
            natural_key="pravachansaar:amritchandra",
            shastra_id=shastra.id,
            teekakar_id=teekakar.id,
        )
        session.add(teeka)
        await session.flush()

        gatha = Gatha(
            natural_key="pravachansaar:039",
            shastra_id=shastra.id,
            gatha_number="039",
            adhikaar=[{"lang": "hin", "script": "Deva", "text": "ज्ञान-अधिकार"}],
            heading=[{"lang": "hin", "script": "Deva", "text": "heading text"}],
        )
        session.add(gatha)
        await session.flush()

        kalash = Kalash(
            natural_key="pravachansaar:amritchandra:kalash:001",
            teeka_id=teeka.id,
            kalash_number="001",
        )
        session.add(kalash)
        await session.commit()
        return {
            "shastra_nk": shastra.natural_key,
            "teeka_nk": teeka.natural_key,
        }


class TestBrowseShastras:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/browse/shastras")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_shastras(self, client: AsyncClient, browse_data):
        r = await client.get("/v1/browse/shastras")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["natural_key"] == "pravachansaar"
        assert data[0]["total_gathas"] == 1
        assert data[0]["total_teekas"] == 1

    async def test_cache_control(self, client: AsyncClient):
        r = await client.get("/v1/browse/shastras")
        assert "Cache-Control" in r.headers


class TestShastraIndex:
    async def test_basic(self, client: AsyncClient, browse_data):
        r = await client.get(f"/v1/browse/shastras/{browse_data['shastra_nk']}/index")
        assert r.status_code == 200
        data = r.json()
        assert data["shastra"]["natural_key"] == "pravachansaar"
        assert len(data["adhikaars"]) == 1
        assert len(data["adhikaars"][0]["gathas"]) == 1

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/browse/shastras/nonexistent/index")
        assert r.status_code == 404


class TestTeekaIndex:
    async def test_basic(self, client: AsyncClient, browse_data):
        r = await client.get(f"/v1/browse/teekas/{browse_data['teeka_nk']}/index")
        assert r.status_code == 200
        data = r.json()
        assert data["teeka"]["natural_key"] == "pravachansaar:amritchandra"
        entries = data["entries"]
        kinds = [e["kind"] for e in entries]
        assert "gatha" in kinds
        assert "kalash" in kinds

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/browse/teekas/nonexistent/index")
        assert r.status_code == 404
