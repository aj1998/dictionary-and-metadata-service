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


_STUB_RECORDS = [
    {
        "src_nk": "द्रव्य:भेद",
        "src_label": "Topic",
        "src_hi": "द्रव्य के भेद",
        "dst_nk": "द्रव्य:stub-topic",
        "dst_label": "Topic",
        "dst_hi": "Stub Topic",
        "rel_type": "RELATED_TO",
        "weight": 1.0,
    }
]


@pytest.mark.parametrize("client_with_neo4j", [_STUB_RECORDS], indirect=True)
class TestExcludeStubs:
    async def test_landing_exclude_stubs_true_returns_200(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing?exclude_stubs=true")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    async def test_landing_exclude_stubs_false_returns_200(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing?exclude_stubs=false")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    async def test_expand_exclude_stubs_true_returns_200(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/द्रव्य:भेद?depth=1&exclude_stubs=true")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    async def test_expand_exclude_stubs_false_returns_200(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/द्रव्य:भेद?depth=1&exclude_stubs=false")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    async def test_preview_exclude_stubs_true_returns_200(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/preview/द्रव्य:भेद?hops=1&exclude_stubs=true")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    async def test_preview_exclude_stubs_false_returns_200(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/preview/द्रव्य:भेद?hops=1&exclude_stubs=false")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
