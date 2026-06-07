"""Tests that Table nodes and CONTAINS_TABLE/MENTIONS_TABLE edges appear in graph traversal."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from services.core_service.domains.navigation.routers.graph import _label_to_kind, _build_payload

pytestmark = pytest.mark.asyncio

_TABLE_RECORDS = [
    {
        "src_nk": "द्रव्य:षट्द्रव्य",
        "src_label": "Topic",
        "src_hi": "षट् द्रव्य",
        "dst_nk": "table:jainkosh:द्रव्य:षट्द्रव्य:01",
        "dst_label": "Table",
        "dst_hi": "table:jainkosh:द्रव्य:षट्द्रव्य:01",
        "rel_type": "CONTAINS_TABLE",
        "weight": 1.0,
        "focus_label": "Topic",
    }
]

_MENTIONS_TABLE_RECORDS = [
    {
        "src_nk": "कषायपाहुड़:टीका:publisher_to_be_added:पृष्ठ:211",
        "src_label": "Page",
        "src_hi": "कषायपाहुड़:टीका:publisher_to_be_added:पृष्ठ:211",
        "dst_nk": "table:jainkosh:द्रव्य:षट्द्रव्य:01",
        "dst_label": "Table",
        "dst_hi": "table:jainkosh:द्रव्य:षट्द्रव्य:01",
        "rel_type": "MENTIONS_TABLE",
        "weight": 1.0,
        "focus_label": "Table",
    }
]


class TestLabelToKindTable:
    def test_table_label_maps_to_table_kind(self):
        assert _label_to_kind("Table") == "table"

    def test_table_lowercase(self):
        assert _label_to_kind("table") == "table"


class TestBuildPayloadIncludesTable:
    def test_table_node_kind_in_payload(self):
        payload = _build_payload(_TABLE_RECORDS, focus_nk="द्रव्य:षट्द्रव्य", depth=1)
        kinds = {n.kind for n in payload.nodes}
        assert "table" in kinds

    def test_contains_table_edge_in_payload(self):
        payload = _build_payload(_TABLE_RECORDS, focus_nk="द्रव्य:षट्द्रव्य", depth=1)
        assert any(e.kind == "CONTAINS_TABLE" for e in payload.edges)

    def test_table_node_nk_correct(self):
        payload = _build_payload(_TABLE_RECORDS, focus_nk="द्रव्य:षट्द्रव्य", depth=1)
        table_nodes = [n for n in payload.nodes if n.kind == "table"]
        assert len(table_nodes) == 1
        assert table_nodes[0].nk == "table:jainkosh:द्रव्य:षट्द्रव्य:01"


@pytest.mark.parametrize("client_with_neo4j", [_TABLE_RECORDS], indirect=True)
class TestExpandIncludesTableNodes:
    async def test_expand_returns_table_kind(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/द्रव्य:षट्द्रव्य?depth=1")
        assert r.status_code == 200
        data = r.json()
        kinds = {n["kind"] for n in data["nodes"]}
        assert "table" in kinds, f"Expected 'table' kind in nodes but got: {kinds}"

    async def test_expand_contains_table_edge(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/expand/द्रव्य:षट्द्रव्य?depth=1")
        assert r.status_code == 200
        data = r.json()
        edge_kinds = {e["kind"] for e in data["edges"]}
        assert "CONTAINS_TABLE" in edge_kinds

    async def test_exclude_stubs_true_still_returns_non_stub_tables(
        self, client_with_neo4j: AsyncClient
    ):
        r = await client_with_neo4j.get("/v1/expand/द्रव्य:षट्द्रव्य?depth=1&exclude_stubs=true")
        assert r.status_code == 200
        data = r.json()
        kinds = {n["kind"] for n in data["nodes"]}
        assert "table" in kinds


@pytest.mark.parametrize("client_with_neo4j", [_TABLE_RECORDS], indirect=True)
class TestLandingIncludesTableNodes:
    async def test_landing_returns_table_node(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get("/v1/landing")
        assert r.status_code == 200
        data = r.json()
        kinds = {n["kind"] for n in data["nodes"]}
        assert "table" in kinds, f"Expected 'table' in landing nodes but got: {kinds}"


class TestBuildPayloadMentionsTable:
    def test_mentions_table_edge_in_payload(self):
        payload = _build_payload(
            _MENTIONS_TABLE_RECORDS,
            focus_nk="table:jainkosh:द्रव्य:षट्द्रव्य:01",
            depth=1,
        )
        assert any(e.kind == "MENTIONS_TABLE" for e in payload.edges)

    def test_page_node_kind_in_payload_for_mentions_table(self):
        payload = _build_payload(
            _MENTIONS_TABLE_RECORDS,
            focus_nk="table:jainkosh:द्रव्य:षट्द्रव्य:01",
            depth=1,
        )
        kinds = {n.kind for n in payload.nodes}
        assert "page" in kinds
        assert "table" in kinds


@pytest.mark.parametrize("client_with_neo4j", [_MENTIONS_TABLE_RECORDS], indirect=True)
class TestExpandIncludesMentionsTableEdges:
    async def test_expand_table_returns_mentions_table_edge(self, client_with_neo4j: AsyncClient):
        r = await client_with_neo4j.get(
            "/v1/expand/table%3Ajainkosh%3A%E0%A4%A6%E0%A5%8D%E0%A4%B0%E0%A4%B5%E0%A5%8D%E0%A4%AF%3A%E0%A4%B7%E0%A4%9F%E0%A5%8D%E0%A4%A6%E0%A5%8D%E0%A4%B0%E0%A4%B5%E0%A5%8D%E0%A4%AF%3A01?depth=1"
        )
        assert r.status_code == 200
        data = r.json()
        edge_kinds = {e["kind"] for e in data["edges"]}
        assert "MENTIONS_TABLE" in edge_kinds, (
            f"Expected MENTIONS_TABLE in edge kinds but got: {edge_kinds}"
        )
