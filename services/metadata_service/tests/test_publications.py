from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def teeka(client: AsyncClient):
    a = await client.post(
        "/v1/admin/authors",
        json={
            "natural_key": "pub-author",
            "display_name": [{"lang": "hin", "script": "Deva", "text": "लेखक"}],
            "kind": "acharya",
        },
        auth=ADMIN_AUTH,
    )
    assert a.status_code == 201
    s = await client.post(
        "/v1/admin/shastras",
        json={
            "natural_key": "pub-shastra",
            "title": [{"lang": "hin", "script": "Deva", "text": "शास्त्र"}],
            "author_id": a.json()["id"],
            "anuyoga_ids": [],
        },
        auth=ADMIN_AUTH,
    )
    assert s.status_code == 201
    t = await client.post(
        "/v1/admin/teekas",
        json={"natural_key": "pub-teeka", "shastra_id": s.json()["id"]},
        auth=ADMIN_AUTH,
    )
    assert t.status_code == 201
    return t.json()


@pytest_asyncio.fixture
async def publication(client: AsyncClient, teeka):
    r = await client.post(
        "/v1/admin/publications",
        json={
            "natural_key": "pub-teeka:17",
            "teeka_id": teeka["id"],
            "publisher_id": "17",
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


class TestListPublications:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/publications")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_publication(self, client: AsyncClient, publication):
        r = await client.get("/v1/publications")
        assert r.status_code == 200
        assert any(i["natural_key"] == "pub-teeka:17" for i in r.json()["items"])

    async def test_filter_by_teeka(self, client: AsyncClient, publication, teeka):
        r = await client.get(f"/v1/publications?teeka_id={teeka['id']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1


class TestGetPublication:
    async def test_by_natural_key(self, client: AsyncClient, publication):
        r = await client.get(f"/v1/publications/{publication['natural_key']}")
        assert r.status_code == 200
        assert r.json()["publisher_id"] == "17"

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/publications/nonexistent")
        assert r.status_code == 404


class TestCreatePublication:
    async def test_create(self, client: AsyncClient, teeka):
        body = {"natural_key": "pub-teeka:18", "teeka_id": teeka["id"], "publisher_id": "18"}
        r = await client.post("/v1/admin/publications", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 201

    async def test_conflict(self, client: AsyncClient, publication, teeka):
        body = {"natural_key": publication["natural_key"], "teeka_id": teeka["id"], "publisher_id": "17"}
        r = await client.post("/v1/admin/publications", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 409

    async def test_missing_field(self, client: AsyncClient):
        r = await client.post("/v1/admin/publications", json={"natural_key": "x"}, auth=ADMIN_AUTH)
        assert r.status_code == 422

    async def test_wrong_credentials(self, client: AsyncClient, teeka):
        body = {"natural_key": "x", "teeka_id": teeka["id"], "publisher_id": "1"}
        r = await client.post("/v1/admin/publications", json=body, auth=("bad", "x"))
        assert r.status_code == 401
