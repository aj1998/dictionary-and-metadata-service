from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def author(client: AsyncClient):
    r = await client.post(
        "/v1/admin/authors",
        json={
            "natural_key": "amritchandra",
            "display_name": [{"lang": "hin", "script": "Deva", "text": "अमृतचन्द्र"}],
            "kind": "acharya",
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


@pytest_asyncio.fixture
async def shastra(client: AsyncClient, author):
    r = await client.post(
        "/v1/admin/shastras",
        json={
            "natural_key": "pravachansaar-t",
            "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
            "author_id": author["id"],
            "anuyoga_ids": [],
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


@pytest_asyncio.fixture
async def teeka(client: AsyncClient, shastra, author):
    r = await client.post(
        "/v1/admin/teekas",
        json={
            "natural_key": "pravachansaar:amritchandra",
            "shastra_id": shastra["id"],
            "teekakar_id": author["id"],
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


class TestListTeekas:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/teekas")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_teeka(self, client: AsyncClient, teeka):
        r = await client.get("/v1/teekas")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_shastra(self, client: AsyncClient, teeka, shastra):
        r = await client.get(f"/v1/teekas?shastra_id={shastra['id']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1


class TestGetTeeka:
    async def test_by_natural_key(self, client: AsyncClient, teeka):
        r = await client.get(f"/v1/teekas/{teeka['natural_key']}")
        assert r.status_code == 200
        assert r.json()["stats"]["total_publications"] == 0

    async def test_by_uuid(self, client: AsyncClient, teeka):
        r = await client.get(f"/v1/teekas/{teeka['id']}")
        assert r.status_code == 200

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/teekas/nonexistent-teeka")
        assert r.status_code == 404


class TestCreateTeeka:
    async def test_create(self, client: AsyncClient, shastra):
        body = {"natural_key": "new-teeka-x1", "shastra_id": shastra["id"]}
        r = await client.post("/v1/admin/teekas", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 201
        assert r.json()["natural_key"] == "new-teeka-x1"

    async def test_conflict(self, client: AsyncClient, teeka, shastra):
        body = {"natural_key": teeka["natural_key"], "shastra_id": shastra["id"]}
        r = await client.post("/v1/admin/teekas", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 409

    async def test_missing_field(self, client: AsyncClient):
        r = await client.post("/v1/admin/teekas", json={"natural_key": "x"}, auth=ADMIN_AUTH)
        assert r.status_code == 422

    async def test_wrong_credentials(self, client: AsyncClient, shastra):
        body = {"natural_key": "x", "shastra_id": shastra["id"]}
        r = await client.post("/v1/admin/teekas", json=body, auth=("bad", "x"))
        assert r.status_code == 401
