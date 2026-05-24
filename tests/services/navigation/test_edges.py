"""Integration tests for topic edge admin endpoints.

Neo4j is mocked; edge type validation uses the real schema_check module.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio


class TestAddTopicEdge:
    async def test_add_valid_edge(self, client: AsyncClient):
        r = await client.post(
            "/v1/admin/topics/आत्मा:अंतरात्मा/edges",
            json={
                "target_topic_natural_key": "द्रव्य:षट्-द्रव्य",
                "edge_type": "RELATED_TO",
                "weight": 1.0,
            },
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["source_topic_natural_key"] == "आत्मा:अंतरात्मा"
        assert data["target_topic_natural_key"] == "द्रव्य:षट्-द्रव्य"
        assert data["edge_type"] == "RELATED_TO"
        assert data["source"] == "admin"

    async def test_add_is_a_edge(self, client: AsyncClient):
        r = await client.post(
            "/v1/admin/topics/child/edges",
            json={"target_topic_natural_key": "parent", "edge_type": "IS_A"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 200

    async def test_add_part_of_edge(self, client: AsyncClient):
        r = await client.post(
            "/v1/admin/topics/child/edges",
            json={"target_topic_natural_key": "parent", "edge_type": "PART_OF"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 200

    async def test_structural_edge_rejected(self, client: AsyncClient):
        r = await client.post(
            "/v1/admin/topics/some-topic/edges",
            json={
                "target_topic_natural_key": "other",
                "edge_type": "IN_SHASTRA",
            },
            auth=ADMIN_AUTH,
        )
        # Pydantic rejects non-Literal values before the handler runs
        assert r.status_code == 422

    async def test_unknown_edge_type_rejected(self, client: AsyncClient):
        r = await client.post(
            "/v1/admin/topics/some-topic/edges",
            json={
                "target_topic_natural_key": "other",
                "edge_type": "FAKE_TYPE",
            },
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 422

    async def test_wrong_creds(self, client: AsyncClient):
        r = await client.post(
            "/v1/admin/topics/a/edges",
            json={"target_topic_natural_key": "b", "edge_type": "IS_A"},
            auth=("bad", "creds"),
        )
        assert r.status_code == 401


class TestRemoveTopicEdge:
    async def test_remove_valid_edge(self, client: AsyncClient):
        r = await client.request(
            "DELETE",
            "/v1/admin/topics/आत्मा:अंतरात्मा/edges",
            json={
                "target_topic_natural_key": "द्रव्य:षट्-द्रव्य",
                "edge_type": "RELATED_TO",
            },
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 204

    async def test_remove_structural_type_rejected(self, client: AsyncClient):
        r = await client.request(
            "DELETE",
            "/v1/admin/topics/a/edges",
            json={"target_topic_natural_key": "b", "edge_type": "IN_SHASTRA"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 422


class TestGraphResync:
    async def test_resync_keyword_scope(self, client: AsyncClient):
        r = await client.post("/v1/admin/graph/resync?scope=keyword", auth=ADMIN_AUTH)
        assert r.status_code == 200
        data = r.json()
        assert data["scope"] == "keyword"
        assert data["status"] == "completed"
        assert "task_id" in data

    async def test_resync_full_requires_confirm(self, client: AsyncClient):
        r = await client.post("/v1/admin/graph/resync?scope=full", auth=ADMIN_AUTH)
        assert r.status_code == 400

    async def test_resync_full_with_confirm(self, client: AsyncClient):
        r = await client.post(
            "/v1/admin/graph/resync?scope=full",
            headers={"X-Confirm": "resync-full"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 200
        assert r.json()["scope"] == "full"


class TestStubAudit:
    async def test_stub_audit_empty(self, client: AsyncClient):
        r = await client.get("/v1/admin/graph/stubs", auth=ADMIN_AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "pagination" in data
        assert "items" in data

    async def test_stub_audit_label_filter(self, client: AsyncClient):
        r = await client.get("/v1/admin/graph/stubs?label=Topic", auth=ADMIN_AUTH)
        assert r.status_code == 200
