from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio

_AUTHOR_BODY = {
    "natural_key": "kundkundacharya",
    "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्दाचार्य"}],
    "kind": "acharya",
}


@pytest_asyncio.fixture
async def author(client: AsyncClient):
    r = await client.post("/v1/admin/authors", json=_AUTHOR_BODY, auth=ADMIN_AUTH)
    assert r.status_code == 201
    return r.json()


class TestListAuthors:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/authors")
        assert r.status_code == 200
        assert r.json()["items"] == []
        assert r.json()["pagination"]["total"] == 0

    async def test_returns_author(self, client: AsyncClient, author):
        r = await client.get("/v1/authors")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["natural_key"] == "kundkundacharya"

    async def test_pagination_params(self, client: AsyncClient, author):
        r = await client.get("/v1/authors?limit=1&offset=0")
        assert r.status_code == 200
        assert r.json()["pagination"]["limit"] == 1


class TestGetAuthor:
    async def test_by_natural_key(self, client: AsyncClient, author):
        r = await client.get("/v1/authors/kundkundacharya")
        assert r.status_code == 200
        assert r.json()["kind"] == "acharya"

    async def test_by_uuid(self, client: AsyncClient, author):
        r = await client.get(f"/v1/authors/{author['id']}")
        assert r.status_code == 200

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/authors/nonexistent")
        assert r.status_code == 404


class TestCreateAuthor:
    async def test_create(self, client: AsyncClient):
        body = {
            "natural_key": "new-author",
            "display_name": [{"lang": "hin", "script": "Deva", "text": "नया"}],
            "kind": "scholar",
        }
        r = await client.post("/v1/admin/authors", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 201
        assert r.json()["natural_key"] == "new-author"

    async def test_conflict(self, client: AsyncClient, author):
        r = await client.post("/v1/admin/authors", json=_AUTHOR_BODY, auth=ADMIN_AUTH)
        assert r.status_code == 409

    async def test_missing_field(self, client: AsyncClient):
        r = await client.post("/v1/admin/authors", json={"natural_key": "x"}, auth=ADMIN_AUTH)
        assert r.status_code == 422

    async def test_wrong_credentials(self, client: AsyncClient):
        r = await client.post("/v1/admin/authors", json=_AUTHOR_BODY, auth=("wrong", "creds"))
        assert r.status_code == 401


class TestUpdateAuthor:
    async def test_patch(self, client: AsyncClient, author):
        r = await client.patch(
            f"/v1/admin/authors/{author['id']}",
            json={"kind": "gyaani"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 200
        assert r.json()["kind"] == "gyaani"

    async def test_404(self, client: AsyncClient):
        r = await client.patch(
            f"/v1/admin/authors/{uuid.uuid4()}",
            json={"kind": "gyaani"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 404
