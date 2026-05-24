from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def search_data(client: AsyncClient):
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.gathas import Gatha
    from jain_kb_common.db.postgres.keywords import Keyword
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.topics import Topic

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="kundkund",
            display_name=[{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
            kind="acharya",
        )
        session.add(author)
        await session.flush()

        kw = Keyword(natural_key="आत्मा", display_text="आत्मा")
        shastra = Shastra(
            natural_key="pravachansaar",
            title=[{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
            author_id=author.id,
        )
        session.add_all([kw, shastra])
        await session.flush()

        topic = Topic(
            natural_key="आत्मा:भेद",
            display_text=[{"lang": "hin", "script": "Deva", "text": "आत्मा के भेद"}],
            source="jainkosh",
            parent_keyword_id=kw.id,
            is_leaf=True,
        )
        gatha = Gatha(
            natural_key="pravachansaar:001",
            shastra_id=shastra.id,
            gatha_number="001",
        )
        session.add_all([topic, gatha])
        await session.commit()


class TestSearch:
    async def test_requires_q(self, client: AsyncClient):
        r = await client.get("/v1/search")
        assert r.status_code == 422

    async def test_q_too_short(self, client: AsyncClient):
        r = await client.get("/v1/search?q=अ")
        assert r.status_code == 422

    async def test_finds_keyword(self, client: AsyncClient, search_data):
        r = await client.get("/v1/search?q=आत्मा")
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "आत्मा"
        entity_types = [i["entity_type"] for i in data["items"]]
        assert "keyword" in entity_types

    async def test_type_filter(self, client: AsyncClient, search_data):
        r = await client.get("/v1/search?q=आत्मा&types=keyword")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["entity_type"] == "keyword"

    async def test_invalid_type(self, client: AsyncClient):
        r = await client.get("/v1/search?q=आत्मा&types=invalid")
        assert r.status_code == 422

    async def test_limit(self, client: AsyncClient, search_data):
        r = await client.get("/v1/search?q=आत्मा&limit=1")
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 1

    async def test_cache_control(self, client: AsyncClient):
        r = await client.get("/v1/search?q=test")
        assert "Cache-Control" in r.headers
