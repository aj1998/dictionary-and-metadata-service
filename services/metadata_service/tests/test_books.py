from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio

_BOOK_BODY = {
    "natural_key": "test-book",
    "title": [{"lang": "hin", "script": "Deva", "text": "पुस्तक"}],
}


@pytest_asyncio.fixture
async def book(client: AsyncClient):
    r = await client.post("/v1/admin/books", json=_BOOK_BODY, auth=ADMIN_AUTH)
    assert r.status_code == 201
    return r.json()


class TestListBooks:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/books")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_book(self, client: AsyncClient, book):
        r = await client.get("/v1/books")
        assert r.status_code == 200
        assert any(i["natural_key"] == "test-book" for i in r.json()["items"])


class TestGetBook:
    async def test_by_natural_key(self, client: AsyncClient, book):
        r = await client.get("/v1/books/test-book")
        assert r.status_code == 200
        assert r.json()["natural_key"] == "test-book"

    async def test_by_uuid(self, client: AsyncClient, book):
        r = await client.get(f"/v1/books/{book['id']}")
        assert r.status_code == 200

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/books/nonexistent")
        assert r.status_code == 404


class TestCreateBook:
    async def test_create(self, client: AsyncClient):
        body = {
            "natural_key": "new-book-x1",
            "title": [{"lang": "hin", "script": "Deva", "text": "नई पुस्तक"}],
        }
        r = await client.post("/v1/admin/books", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 201

    async def test_conflict(self, client: AsyncClient, book):
        r = await client.post("/v1/admin/books", json=_BOOK_BODY, auth=ADMIN_AUTH)
        assert r.status_code == 409

    async def test_missing_field(self, client: AsyncClient):
        r = await client.post("/v1/admin/books", json={"natural_key": "x"}, auth=ADMIN_AUTH)
        assert r.status_code == 422

    async def test_wrong_credentials(self, client: AsyncClient):
        r = await client.post("/v1/admin/books", json=_BOOK_BODY, auth=("bad", "x"))
        assert r.status_code == 401
