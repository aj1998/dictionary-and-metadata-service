from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio

_PRAVACHAN_BODY = {
    "natural_key": "test-pravachan",
    "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचन"}],
}


@pytest_asyncio.fixture
async def pravachan(client: AsyncClient):
    r = await client.post("/v1/admin/pravachans", json=_PRAVACHAN_BODY, auth=ADMIN_AUTH)
    assert r.status_code == 201
    return r.json()


class TestListPravachans:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/pravachans")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_pravachan(self, client: AsyncClient, pravachan):
        r = await client.get("/v1/pravachans")
        assert r.status_code == 200
        assert any(i["natural_key"] == "test-pravachan" for i in r.json()["items"])


class TestGetPravachan:
    async def test_by_natural_key(self, client: AsyncClient, pravachan):
        r = await client.get("/v1/pravachans/test-pravachan")
        assert r.status_code == 200

    async def test_by_uuid(self, client: AsyncClient, pravachan):
        r = await client.get(f"/v1/pravachans/{pravachan['id']}")
        assert r.status_code == 200

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/pravachans/nonexistent")
        assert r.status_code == 404


class TestCreatePravachan:
    async def test_create(self, client: AsyncClient):
        body = {
            "natural_key": "new-pravachan-x1",
            "title": [{"lang": "hin", "script": "Deva", "text": "नया प्रवचन"}],
        }
        r = await client.post("/v1/admin/pravachans", json=body, auth=ADMIN_AUTH)
        assert r.status_code == 201

    async def test_conflict(self, client: AsyncClient, pravachan):
        r = await client.post("/v1/admin/pravachans", json=_PRAVACHAN_BODY, auth=ADMIN_AUTH)
        assert r.status_code == 409

    async def test_missing_field(self, client: AsyncClient):
        r = await client.post("/v1/admin/pravachans", json={"natural_key": "x"}, auth=ADMIN_AUTH)
        assert r.status_code == 422

    async def test_wrong_credentials(self, client: AsyncClient):
        r = await client.post("/v1/admin/pravachans", json=_PRAVACHAN_BODY, auth=("bad", "x"))
        assert r.status_code == 401
