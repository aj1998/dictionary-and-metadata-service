from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def keyword(client: AsyncClient):
    from jain_kb_common.db.postgres.keywords import Keyword

    async with client.state() as session:  # type: ignore[attr-defined]
        kw = Keyword(
            natural_key="आत्मा",
            display_text="आत्मा",
            source_url="https://www.jainkosh.org/wiki/आत्मा",
        )
        session.add(kw)
        await session.commit()
        await session.refresh(kw)
        return {"id": str(kw.id), "natural_key": kw.natural_key, "display_text": kw.display_text}


class TestListKeywords:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/keywords")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0

    async def test_returns_keyword(self, client: AsyncClient, keyword):
        r = await client.get("/v1/keywords")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_letter(self, client: AsyncClient, keyword):
        r = await client.get("/v1/keywords?letter=आ")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_letter_no_match(self, client: AsyncClient, keyword):
        r = await client.get("/v1/keywords?letter=क")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 0

    async def test_cache_control_header(self, client: AsyncClient):
        r = await client.get("/v1/keywords")
        assert "Cache-Control" in r.headers


class TestLetterIndex:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/keywords/letters")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_letters(self, client: AsyncClient, keyword):
        r = await client.get("/v1/keywords/letters")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["letter"] == "आ"
        assert data[0]["count"] == 1


class TestKeywordDetail:
    async def test_by_natural_key(self, client: AsyncClient, keyword):
        r = await client.get("/v1/keywords/आत्मा")
        assert r.status_code == 200
        data = r.json()
        assert data["natural_key"] == "आत्मा"
        assert data["aliases"] == []
        assert data["definition"] is None

    async def test_by_uuid(self, client: AsyncClient, keyword):
        r = await client.get(f"/v1/keywords/{keyword['id']}")
        assert r.status_code == 200

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/keywords/nonexistent")
        assert r.status_code == 404

    async def test_cache_control(self, client: AsyncClient, keyword):
        r = await client.get("/v1/keywords/आत्मा")
        assert "Cache-Control" in r.headers


class TestAdminKeyword:
    async def test_patch_display_text(self, client: AsyncClient, keyword):
        r = await client.patch(
            f"/v1/admin/keywords/{keyword['id']}",
            json={"display_text": "आत्मन्"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 200
        assert r.json()["display_text"] == "आत्मन्"

    async def test_patch_unknown_field_rejected(self, client: AsyncClient, keyword):
        r = await client.patch(
            f"/v1/admin/keywords/{keyword['id']}",
            json={"unknown_field": "value"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 422

    async def test_patch_wrong_credentials(self, client: AsyncClient, keyword):
        r = await client.patch(
            f"/v1/admin/keywords/{keyword['id']}",
            json={"display_text": "x"},
            auth=("bad", "creds"),
        )
        assert r.status_code == 401

    async def test_patch_404(self, client: AsyncClient):
        import uuid
        r = await client.patch(
            f"/v1/admin/keywords/{uuid.uuid4()}",
            json={"display_text": "x"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 404
