from __future__ import annotations

import pytest
from httpx import AsyncClient

from services.core_service.domains.navigation.routers.graph import _label_to_kind, _build_payload

pytestmark = pytest.mark.asyncio


# ─── Unit: _label_to_kind ─────────────────────────────────────────────────────

class TestLabelToKind:
    def test_topic_label(self):
        assert _label_to_kind("Topic") == "topic"

    def test_keyword_label(self):
        assert _label_to_kind("Keyword") == "keyword"

    def test_shastra_label(self):
        assert _label_to_kind("Shastra") == "shastra"

    def test_gatha_label(self):
        assert _label_to_kind("Gatha") == "gatha"

    def test_none_defaults_to_topic(self):
        assert _label_to_kind(None) == "topic"

    def test_unknown_label_defaults_to_topic(self):
        assert _label_to_kind("GathaTeeka") == "topic"

    def test_lowercase_label(self):
        assert _label_to_kind("gatha") == "gatha"
        assert _label_to_kind("shastra") == "shastra"


# ─── Unit: _build_payload ─────────────────────────────────────────────────────

class TestBuildPayload:
    def _gatha_record(self, gatha_nk: str, topic_nk: str) -> dict:
        return {
            "src_nk": gatha_nk,
            "src_label": "Gatha",
            "src_hi": f"गाथा {gatha_nk}",
            "dst_nk": topic_nk,
            "dst_label": "Topic",
            "dst_hi": topic_nk,
            "rel_type": "MENTIONS_TOPIC",
            "weight": 1.0,
        }

    def _shastra_record(self, gatha_nk: str, shastra_nk: str) -> dict:
        return {
            "src_nk": gatha_nk,
            "src_label": "Gatha",
            "src_hi": f"गाथा {gatha_nk}",
            "dst_nk": shastra_nk,
            "dst_label": "Shastra",
            "dst_hi": shastra_nk,
            "rel_type": "IN_SHASTRA",
            "weight": 1.0,
        }

    def test_gatha_node_kind_from_mentions_topic_record(self):
        records = [self._gatha_record("samayasaar:1", "आत्मा")]
        payload = _build_payload(records, focus_nk="samayasaar:1", depth=1)
        gatha_node = next(n for n in payload.nodes if n.nk == "samayasaar:1")
        assert gatha_node.kind == "gatha"

    def test_shastra_node_kind_from_in_shastra_record(self):
        records = [self._shastra_record("samayasaar:1", "samayasaar")]
        payload = _build_payload(records, focus_nk="samayasaar:1", depth=1)
        shastra_node = next(n for n in payload.nodes if n.nk == "samayasaar")
        assert shastra_node.kind == "shastra"

    def test_focus_node_kind_uses_focus_label_when_isolated(self):
        # No edges — focus node must use the focus_label parameter
        payload = _build_payload([], focus_nk="samayasaar:1", depth=1, focus_label="Gatha")
        focus = next(n for n in payload.nodes if n.nk == "samayasaar:1")
        assert focus.kind == "gatha"

    def test_focus_node_kind_shastra_label_isolated(self):
        payload = _build_payload([], focus_nk="samayasaar", depth=1, focus_label="Shastra")
        focus = next(n for n in payload.nodes if n.nk == "samayasaar")
        assert focus.kind == "shastra"

    def test_focus_node_kind_defaults_to_topic_when_no_label(self):
        payload = _build_payload([], focus_nk="some-nk", depth=1, focus_label=None)
        focus = next(n for n in payload.nodes if n.nk == "some-nk")
        assert focus.kind == "topic"

    def test_payload_includes_all_node_kinds(self):
        records = [
            self._gatha_record("samayasaar:1", "आत्मा"),
            self._shastra_record("samayasaar:1", "samayasaar"),
        ]
        payload = _build_payload(records, focus_nk="samayasaar:1", depth=1)
        kinds = {n.kind for n in payload.nodes}
        assert "gatha" in kinds
        assert "shastra" in kinds
        assert "topic" in kinds

    def test_mentions_topic_edge_is_included(self):
        records = [self._gatha_record("samayasaar:1", "आत्मा")]
        payload = _build_payload(records, focus_nk="samayasaar:1", depth=1)
        assert any(e.kind == "MENTIONS_TOPIC" for e in payload.edges)

    def test_in_shastra_edge_is_included(self):
        records = [self._shastra_record("samayasaar:1", "samayasaar")]
        payload = _build_payload(records, focus_nk="samayasaar:1", depth=1)
        assert any(e.kind == "IN_SHASTRA" for e in payload.edges)


# ─── Integration: gatha/shastra nodes via new edge types ──────────────────────

_GATHA_RECORDS = [
    {
        "src_nk": "samayasaar:1",
        "src_label": "Gatha",
        "src_hi": "गाथा १",
        "dst_nk": "आत्मा",
        "dst_label": "Topic",
        "dst_hi": "आत्मा",
        "rel_type": "MENTIONS_TOPIC",
        "weight": 1.0,
        "focus_label": "Topic",
    }
]

_SHASTRA_RECORDS = [
    {
        "src_nk": "samayasaar:1",
        "src_label": "Gatha",
        "src_hi": "गाथा १",
        "dst_nk": "samayasaar",
        "dst_label": "Shastra",
        "dst_hi": "समयसार",
        "rel_type": "IN_SHASTRA",
        "weight": 1.0,
        "focus_label": "Topic",
    }
]


@pytest.mark.parametrize("client_with_neo4j", [_GATHA_RECORDS], indirect=True)
class TestGathaNodesViaExpandEndpoint:
    async def test_expand_returns_gatha_node_from_mentions_topic(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/आत्मा?depth=1")
        assert r.status_code == 200
        data = r.json()
        kinds = {n["kind"] for n in data["nodes"]}
        assert "gatha" in kinds, f"Expected gatha nodes but got kinds: {kinds}"

    async def test_expand_gatha_node_has_correct_title(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/आत्मा?depth=1")
        assert r.status_code == 200
        data = r.json()
        gatha_nodes = [n for n in data["nodes"] if n["kind"] == "gatha"]
        assert len(gatha_nodes) >= 1
        assert gatha_nodes[0]["nk"] == "samayasaar:1"

    async def test_expand_includes_mentions_topic_edge(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/आत्मा?depth=1")
        assert r.status_code == 200
        data = r.json()
        edge_kinds = {e["kind"] for e in data["edges"]}
        assert "MENTIONS_TOPIC" in edge_kinds


@pytest.mark.parametrize("client_with_neo4j", [_SHASTRA_RECORDS], indirect=True)
class TestShastraNodesViaExpandEndpoint:
    async def test_expand_returns_shastra_node_from_in_shastra(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/samayasaar:1?depth=1")
        assert r.status_code == 200
        data = r.json()
        kinds = {n["kind"] for n in data["nodes"]}
        assert "shastra" in kinds, f"Expected shastra nodes but got kinds: {kinds}"

    async def test_expand_shastra_node_has_correct_nk(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/samayasaar:1?depth=1")
        assert r.status_code == 200
        data = r.json()
        shastra_nodes = [n for n in data["nodes"] if n["kind"] == "shastra"]
        assert len(shastra_nodes) >= 1
        assert shastra_nodes[0]["nk"] == "samayasaar"

    async def test_expand_includes_in_shastra_edge(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/samayasaar:1?depth=1")
        assert r.status_code == 200
        data = r.json()
        edge_kinds = {e["kind"] for e in data["edges"]}
        assert "IN_SHASTRA" in edge_kinds


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
