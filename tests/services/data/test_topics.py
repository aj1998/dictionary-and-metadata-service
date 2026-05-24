from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def topic_data(client: AsyncClient):
    from jain_kb_common.db.postgres.keywords import Keyword
    from jain_kb_common.db.postgres.topics import Topic

    async with client.state() as session:  # type: ignore[attr-defined]
        kw = Keyword(natural_key="आत्मा", display_text="आत्मा")
        session.add(kw)
        await session.flush()

        parent = Topic(
            natural_key="आत्मा:आत्मा-के-भेद",
            display_text=[{"lang": "hin", "script": "Deva", "text": "आत्मा के भेद"}],
            source="jainkosh",
            parent_keyword_id=kw.id,
            is_leaf=False,
            topic_path="आत्मा-के-भेद",
        )
        session.add(parent)
        await session.flush()

        child = Topic(
            natural_key="आत्मा:बहिरात्मादि-3-भेद",
            display_text=[{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
            source="jainkosh",
            parent_keyword_id=kw.id,
            parent_topic_id=parent.id,
            is_leaf=True,
            topic_path="बहिरात्मादि-3-भेद",
        )
        session.add(child)
        await session.commit()
        await session.refresh(kw)
        await session.refresh(parent)
        await session.refresh(child)
        return {
            "keyword_id": str(kw.id),
            "parent_id": str(parent.id),
            "child_id": str(child.id),
            "parent_nk": parent.natural_key,
            "child_nk": child.natural_key,
        }


class TestListTopics:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/topics")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_topics(self, client: AsyncClient, topic_data):
        r = await client.get("/v1/topics")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    async def test_filter_is_leaf(self, client: AsyncClient, topic_data):
        r = await client.get("/v1/topics?is_leaf=true")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(i["is_leaf"] for i in items)

    async def test_filter_parent_keyword(self, client: AsyncClient, topic_data):
        r = await client.get(f"/v1/topics?parent_keyword_id={topic_data['keyword_id']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    async def test_cache_control(self, client: AsyncClient):
        r = await client.get("/v1/topics")
        assert "Cache-Control" in r.headers


class TestTopicDetail:
    async def test_child_has_parent_topic(self, client: AsyncClient, topic_data):
        r = await client.get(f"/v1/topics/{topic_data['child_nk']}")
        assert r.status_code == 200
        data = r.json()
        assert data["parent_topic"] is not None
        assert data["parent_topic"]["natural_key"] == topic_data["parent_nk"]
        assert data["extracts"] == []

    async def test_root_topic_no_parent_topic(self, client: AsyncClient, topic_data):
        r = await client.get(f"/v1/topics/{topic_data['parent_nk']}")
        assert r.status_code == 200
        data = r.json()
        assert data["parent_topic"] is None
        assert data["parent_keyword"] is not None

    async def test_by_uuid(self, client: AsyncClient, topic_data):
        r = await client.get(f"/v1/topics/{topic_data['child_id']}")
        assert r.status_code == 200

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/topics/nonexistent")
        assert r.status_code == 404
