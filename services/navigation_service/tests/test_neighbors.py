"""Integration tests for topic neighbor and keyword↔topic traversal endpoints.

Neo4j is mocked via the conftest `client_with_neo4j` fixture which lets us
inject fake records. Postgres is a real test database.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


_NEIGHBOR_RECORDS = [
    {
        "natural_key": "आत्मा:अंतरात्मा",
        "display_text_hi": "अंतरात्मा",
        "label": "Topic",
        "edge_type": "IS_A",
        "edge_direction": "outbound",
        "weight": 1.0,
        "is_stub": False,
    },
    {
        "natural_key": "आत्मा:परमात्मा",
        "display_text_hi": "परमात्मा",
        "label": "Topic",
        "edge_type": "IS_A",
        "edge_direction": "outbound",
        "weight": 1.0,
        "is_stub": False,
    },
]

_TOPIC_RECORDS = [
    {
        "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
        "display_text_hi": "आत्मा के बहिरात्मादि 3 भेद",
        "edge_type": "HAS_TOPIC",
        "is_stub": False,
    }
]

_KEYWORD_RECORDS = [
    {
        "natural_key": "बहिरात्मा",
        "display_text": "बहिरात्मा",
        "edge_type": "MENTIONS_KEYWORD",
        "is_stub": False,
    }
]


@pytest.mark.parametrize("client_with_neo4j", [_NEIGHBOR_RECORDS], indirect=True)
class TestTopicNeighbors:
    async def test_returns_neighbors(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["topic_natural_key"] == "आत्मा:बहिरात्मादि-3-भेद"
        assert len(data["neighbors"]) == 2

    async def test_neighbor_fields(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors"
        )
        n = r.json()["neighbors"][0]
        assert "natural_key" in n
        assert "edge_type" in n
        assert "edge_direction" in n
        assert "weight" in n
        assert "is_stub" in n

    async def test_depth_param_accepted(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors?depth=2"
        )
        assert r.status_code == 200

    async def test_depth_over_max_rejected(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors?depth=4"
        )
        assert r.status_code == 422


@pytest.mark.parametrize("client_with_neo4j", [[]], indirect=True)
class TestTopicNeighborsEmpty:
    async def test_empty_neighbors(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/topics/noexist/neighbors")
        assert r.status_code == 200
        assert r.json()["neighbors"] == []


@pytest.mark.parametrize("client_with_neo4j", [_TOPIC_RECORDS], indirect=True)
class TestKeywordTopics:
    async def test_returns_topics(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/keywords/आत्मा/topics")
        assert r.status_code == 200
        data = r.json()
        assert data["keyword_natural_key"] == "आत्मा"
        assert len(data["topics"]) == 1
        assert data["topics"][0]["edge_type"] == "HAS_TOPIC"

    async def test_depth_max_2(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/keywords/आत्मा/topics?depth=3")
        assert r.status_code == 422


@pytest.mark.parametrize("client_with_neo4j", [_KEYWORD_RECORDS], indirect=True)
class TestTopicKeywords:
    async def test_returns_keywords(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/topics/आत्मा:बहिरात्मादि-3-भेद/keywords")
        assert r.status_code == 200
        data = r.json()
        assert data["topic_natural_key"] == "आत्मा:बहिरात्मादि-3-भेद"
        assert len(data["keywords"]) == 1
        assert data["keywords"][0]["edge_type"] == "MENTIONS_KEYWORD"
