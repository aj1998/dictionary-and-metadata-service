"""Integration tests for mentioned-topics / mentioned-keywords endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


_MENTIONED_TOPIC_RECORDS = [
    {
        "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
        "display_text_hi": "आत्मा के बहिरात्मादि 3 भेद",
        "is_stub": False,
        "is_leaf": True,
        "parent_keyword_natural_key": "आत्मा",
    },
    {
        "natural_key": "व्यवहार:परमार्थ",
        "display_text_hi": "परमार्थ",
        "is_stub": False,
        "is_leaf": False,
        "parent_keyword_natural_key": "व्यवहार",
    },
]

_MENTIONED_KEYWORD_RECORDS = [
    {
        "natural_key": "अनार्य",
        "display_text": "अनार्य",
        "is_stub": False,
    }
]


@pytest.mark.parametrize("client_with_neo4j", [_MENTIONED_TOPIC_RECORDS], indirect=True)
class TestNodeMentionedTopics:
    async def test_returns_topics(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/nodes/समयसार:गाथा:8/mentioned-topics"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["source_natural_key"] == "समयसार:गाथा:8"
        assert len(data["topics"]) == 2
        t = data["topics"][0]
        assert t["natural_key"] == "आत्मा:बहिरात्मादि-3-भेद"
        assert t["is_leaf"] is True
        assert t["parent_keyword_natural_key"] == "आत्मा"

    async def test_exclude_stubs_param_accepted(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/nodes/समयसार:गाथा:8/mentioned-topics?exclude_stubs=true"
        )
        assert r.status_code == 200


@pytest.mark.parametrize("client_with_neo4j", [_MENTIONED_KEYWORD_RECORDS], indirect=True)
class TestNodeMentionedKeywords:
    async def test_returns_keywords(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/nodes/समयसार:गाथा:8/mentioned-keywords"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["source_natural_key"] == "समयसार:गाथा:8"
        assert len(data["keywords"]) == 1
        assert data["keywords"][0]["natural_key"] == "अनार्य"


@pytest.mark.parametrize("client_with_neo4j", [[]], indirect=True)
class TestEmptyResults:
    async def test_topics_empty(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/nodes/somekey/mentioned-topics"
        )
        assert r.status_code == 200
        assert r.json()["topics"] == []

    async def test_keywords_empty(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/nodes/somekey/mentioned-keywords"
        )
        assert r.status_code == 200
        assert r.json()["keywords"] == []
