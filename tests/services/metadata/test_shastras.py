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
            "natural_key": "kundkund",
            "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
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
            "natural_key": "pravachansaar",
            "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
            "author_id": author["id"],
            "anuyoga_ids": [],
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


class TestListShastras:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/shastras")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_shastra(self, client: AsyncClient, shastra):
        r = await client.get("/v1/shastras")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_author(self, client: AsyncClient, shastra, author):
        r = await client.get(f"/v1/shastras?author_id={author['id']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1


class TestGetShastra:
    async def test_by_natural_key(self, client: AsyncClient, shastra):
        r = await client.get("/v1/shastras/pravachansaar")
        assert r.status_code == 200
        data = r.json()
        assert data["natural_key"] == "pravachansaar"
        assert data["stats"]["total_gathas"] == 0
        assert data["stats"]["total_teekas"] == 0

    async def test_author_embedded(self, client: AsyncClient, shastra):
        r = await client.get("/v1/shastras/pravachansaar")
        assert r.json()["author"]["natural_key"] == "kundkund"

    async def test_by_uuid(self, client: AsyncClient, shastra):
        r = await client.get(f"/v1/shastras/{shastra['id']}")
        assert r.status_code == 200

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/shastras/nonexistent")
        assert r.status_code == 404


class TestCreateShastra:
    async def test_create(self, client: AsyncClient, author):
        body = {
            "natural_key": "samaysaar",
            "title": [{"lang": "hin", "script": "Deva", "text": "समयसार"}],
            "author_id": author["id"],
            "anuyoga_ids": [],
        }
        r = await client.post("/v1/admin/shastras", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 201
        assert r.json()["natural_key"] == "samaysaar"

    async def test_conflict(self, client: AsyncClient, shastra, author):
        body = {
            "natural_key": "pravachansaar",
            "title": [{"lang": "hin", "script": "Deva", "text": "x"}],
            "author_id": author["id"],
            "anuyoga_ids": [],
        }
        r = await client.post("/v1/admin/shastras", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 409

    async def test_missing_field(self, client: AsyncClient):
        r = await client.post("/v1/admin/shastras", json={"natural_key": "x"}, auth=ADMIN_AUTH)
        assert r.status_code == 422

    async def test_wrong_credentials(self, client: AsyncClient, author):
        body = {
            "natural_key": "test-s",
            "title": [{"lang": "hin", "script": "Deva", "text": "x"}],
            "author_id": author["id"],
        }
        r = await client.post("/v1/admin/shastras", json=body, auth=("bad", "creds"))
        assert r.status_code == 401
