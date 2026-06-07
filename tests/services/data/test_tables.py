"""Tests for GET /v1/tables endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio

_TABLE_NK = "table:jainkosh:द्रव्य:षट्द्रव्य:01"
_PARENT_NK = "द्रव्य:षट्द्रव्य"

_MONGO_TABLE_DOC = {
    "natural_key": _TABLE_NK,
    "source": "jainkosh",
    "parent_natural_key": _PARENT_NK,
    "parent_kind": "Topic",
    "seq": 1,
    "source_url": "https://www.jainkosh.org/wiki/द्रव्य",
    "caption": [{"lang": "hi", "script": "devanagari", "text": "षट् द्रव्य"}],
    "raw_html": "<table><tr><td>कुछ</td></tr></table>",
    "cells": [["कुछ"]],
    "header_rows": 0,
    "plaintext": "कुछ",
    "mentioned_keyword_natural_keys": [],
    "mentioned_topic_natural_keys": [],
}


def _make_mongo_with_table(doc: dict | None = _MONGO_TABLE_DOC) -> MagicMock:
    mongo = MagicMock()

    def _col(name: str):
        col = MagicMock()
        col.find_one = AsyncMock(return_value=dict(doc) if doc else None)
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[])
        col.find = MagicMock(return_value=cursor)
        return col

    mongo.__getitem__ = MagicMock(side_effect=_col)
    return mongo


@pytest_asyncio.fixture
async def table_row(client: AsyncClient):
    """Seed a Table PG row."""
    from jain_kb_common.db.postgres.tables import Table

    async with client.state() as session:  # type: ignore[attr-defined]
        row = Table(
            natural_key=_TABLE_NK,
            source="jainkosh",
            parent_natural_key=_PARENT_NK,
            parent_kind="Topic",
            seq=1,
            caption=[{"lang": "hi", "script": "devanagari", "text": "षट् द्रव्य"}],
            source_url="https://www.jainkosh.org/wiki/द्रव्य",
            raw_html_doc_id="abc123",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


@pytest_asyncio.fixture
async def client_with_table_mongo(client: AsyncClient, table_row):
    """Override mongo so the tables collection returns the test doc."""
    from services.core_service import deps
    from services.core_service.main import app

    async def _override():
        return _make_mongo_with_table()

    app.dependency_overrides[deps.get_mongo_db] = _override
    yield client

    from tests.services.data.conftest import make_mock_mongo

    async def _restore():
        return make_mock_mongo()

    app.dependency_overrides[deps.get_mongo_db] = _restore


class TestGetTableByNaturalKey:
    async def test_returns_200_with_full_payload(self, client_with_table_mongo: AsyncClient):
        r = await client_with_table_mongo.get(f"/v1/tables/{_TABLE_NK}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["natural_key"] == _TABLE_NK
        assert data["parent_natural_key"] == _PARENT_NK
        assert data["seq"] == 1
        assert data["raw_html"] == "<table><tr><td>कुछ</td></tr></table>"
        assert data["cells"] == [["कुछ"]]
        assert data["header_rows"] == 0
        assert data["plaintext"] == "कुछ"
        assert isinstance(data["caption"], list)
        assert data["pg_id"]

    async def test_cache_control_header(self, client_with_table_mongo: AsyncClient):
        r = await client_with_table_mongo.get(f"/v1/tables/{_TABLE_NK}")
        assert r.status_code == 200
        assert "Cache-Control" in r.headers

    async def test_404_for_unknown_key(self, client: AsyncClient):
        r = await client.get("/v1/tables/table:jainkosh:nonexistent:99")
        assert r.status_code == 404


class TestGetTableMissingMongoDoc:
    async def test_returns_empty_cells_not_500(self, client: AsyncClient, table_row):
        """When Mongo doc is absent, endpoint still returns 200 with empty cells."""
        from services.core_service import deps
        from services.core_service.main import app

        async def _override():
            return _make_mongo_with_table(doc=None)

        app.dependency_overrides[deps.get_mongo_db] = _override

        r = await client.get(f"/v1/tables/{_TABLE_NK}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cells"] == []
        assert data["raw_html"] == ""

        from tests.services.data.conftest import make_mock_mongo

        async def _restore():
            return make_mock_mongo()

        app.dependency_overrides[deps.get_mongo_db] = _restore


class TestListTablesForParent:
    async def test_returns_summaries_in_seq_order(self, client: AsyncClient):
        """Seed two tables with different seqs; list endpoint returns them ordered."""
        from jain_kb_common.db.postgres.tables import Table

        async with client.state() as session:  # type: ignore[attr-defined]
            for seq in (2, 1):
                row = Table(
                    natural_key=f"table:jainkosh:द्रव्य:parent:{seq:02d}",
                    source="jainkosh",
                    parent_natural_key="द्रव्य:parent",
                    parent_kind="Topic",
                    seq=seq,
                    caption=[],
                    source_url=None,
                    raw_html_doc_id="x",
                )
                session.add(row)
            await session.commit()

        r = await client.get("/v1/tables?parent_natural_key=द्रव्य:parent")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        assert items[0]["seq"] == 1
        assert items[1]["seq"] == 2

    async def test_returns_empty_list_when_no_tables(self, client: AsyncClient):
        r = await client.get("/v1/tables?parent_natural_key=nonexistent:topic")
        assert r.status_code == 200
        assert r.json() == []

    async def test_parent_natural_key_required(self, client: AsyncClient):
        r = await client.get("/v1/tables")
        assert r.status_code == 422
