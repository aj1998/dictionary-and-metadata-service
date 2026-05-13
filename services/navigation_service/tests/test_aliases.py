"""Integration tests for alias add/delete admin endpoints.

Postgres is real; Neo4j driver is mocked (MERGE calls are no-ops).
"""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def keyword(client: AsyncClient):
    from jain_kb_common.db.postgres.keywords import Keyword

    async with client.state() as session:  # type: ignore[attr-defined]
        kw = Keyword(natural_key="जीव", display_text="जीव")
        session.add(kw)
        await session.commit()
        await session.refresh(kw)
        return {"id": str(kw.id), "natural_key": kw.natural_key}


class TestAddAlias:
    async def test_add_alias_success(self, client: AsyncClient, keyword):
        r = await client.post(
            f"/v1/admin/keywords/{keyword['id']}/aliases",
            json={"alias_text": "जीवा", "source": "admin"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["alias_text"] == "जीवा"
        assert data["source"] == "admin"
        assert data["keyword_natural_key"] == "जीव"
        assert "id" in data
        assert "created_at" in data

    async def test_add_alias_idempotent(self, client: AsyncClient, keyword):
        payload = {"alias_text": "जीवन", "source": "admin"}
        r1 = await client.post(
            f"/v1/admin/keywords/{keyword['id']}/aliases",
            json=payload,
            auth=ADMIN_AUTH,
        )
        r2 = await client.post(
            f"/v1/admin/keywords/{keyword['id']}/aliases",
            json=payload,
            auth=ADMIN_AUTH,
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Same alias returned both times
        assert r1.json()["id"] == r2.json()["id"]

    async def test_add_alias_wrong_creds(self, client: AsyncClient, keyword):
        r = await client.post(
            f"/v1/admin/keywords/{keyword['id']}/aliases",
            json={"alias_text": "test"},
            auth=("bad", "creds"),
        )
        assert r.status_code == 401

    async def test_add_alias_keyword_not_found(self, client: AsyncClient):
        r = await client.post(
            f"/v1/admin/keywords/{uuid.uuid4()}/aliases",
            json={"alias_text": "test", "source": "admin"},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 404


class TestDeleteAlias:
    async def test_delete_alias_success(self, client: AsyncClient, keyword):
        # First add an alias
        add_r = await client.post(
            f"/v1/admin/keywords/{keyword['id']}/aliases",
            json={"alias_text": "जीवस", "source": "admin"},
            auth=ADMIN_AUTH,
        )
        alias_id = add_r.json()["id"]

        # Now delete it
        del_r = await client.delete(
            f"/v1/admin/keywords/{keyword['id']}/aliases/{alias_id}",
            auth=ADMIN_AUTH,
        )
        assert del_r.status_code == 204

    async def test_delete_alias_not_found(self, client: AsyncClient, keyword):
        r = await client.delete(
            f"/v1/admin/keywords/{keyword['id']}/aliases/{uuid.uuid4()}",
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 404
