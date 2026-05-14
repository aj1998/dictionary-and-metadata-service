from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_GRAPH_RECORDS = [
    {
        "src_nk": "आत्मा:बहिरात्मादि-3-भेद",
        "src_label": "Topic",
        "src_hi": "आत्मा के बहिरात्मादि 3 भेद",
        "dst_nk": "आत्मा:अंतरात्मा",
        "dst_label": "Topic",
        "dst_hi": "अंतरात्मा",
        "rel_type": "IS_A",
        "weight": 1.0,
    }
]


@pytest.mark.parametrize("client_with_neo4j", [_GRAPH_RECORDS], indirect=True)
class TestGraphPayloadRoutes:
    async def test_landing_returns_graph_payload(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing")
        assert r.status_code == 200
        data = r.json()
        assert data["focus_nk"] == "आत्मा:बहिरात्मादि-3-भेद"
        assert data["depth"] == 1
        assert len(data["nodes"]) >= 1
        assert len(data["edges"]) >= 1

    async def test_expand_returns_graph_payload(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/आत्मा:बहिरात्मादि-3-भेद?depth=2")
        assert r.status_code == 200
        data = r.json()
        assert data["focus_nk"] == "आत्मा:बहिरात्मादि-3-भेद"
        assert data["depth"] == 2

    async def test_preview_returns_graph_payload(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/preview/आत्मा:बहिरात्मादि-3-भेद?hops=2")
        assert r.status_code == 200
        data = r.json()
        assert data["focus_nk"] == "आत्मा:बहिरात्मादि-3-भेद"
        assert data["depth"] == 2
