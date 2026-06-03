from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_FIXTURE_DOC = {
    "natural_key": "match:samaysaar:गाथा:1:block:0",
    "target": {
        "collection": "gatha_teeka_sanskrit",
        "natural_key": "samaysaar:amritchandra:1:sanskrit",
        "lang": "san",
    },
    "match": {
        "status": "matched",
        "char_start": 42,
        "char_end": 89,
    },
}


def _mongo_with_doc(doc: dict | None) -> MagicMock:
    mongo = MagicMock()
    col = MagicMock()
    col.find_one = AsyncMock(return_value=dict(doc, _id="oid") if doc else None)
    mongo.__getitem__ = MagicMock(return_value=col)
    return mongo


class TestGetExtractMatch:
    async def test_returns_match_doc(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_doc(_FIXTURE_DOC)
        try:
            r = await client.get(f"/v1/extract-matches/{_FIXTURE_DOC['natural_key']}")
            assert r.status_code == 200
            body = r.json()
            assert body["natural_key"] == _FIXTURE_DOC["natural_key"]
            assert body["target"]["collection"] == "gatha_teeka_sanskrit"
            assert body["match"]["status"] == "matched"
            assert body["match"]["char_start"] == 42
            assert body["match"]["char_end"] == 89
            assert "_id" not in body
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_returns_404_when_not_found(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_doc(None)
        try:
            r = await client.get("/v1/extract-matches/nonexistent:key")
            assert r.status_code == 404
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_strips_mongo_id_from_response(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_doc(_FIXTURE_DOC)
        try:
            r = await client.get(f"/v1/extract-matches/{_FIXTURE_DOC['natural_key']}")
            assert r.status_code == 200
            assert "_id" not in r.json()
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_handles_unmatched_status(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        unmatched_doc = {**_FIXTURE_DOC, "match": {"status": "unmatched", "char_start": None, "char_end": None}}
        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_doc(unmatched_doc)
        try:
            r = await client.get(f"/v1/extract-matches/{_FIXTURE_DOC['natural_key']}")
            assert r.status_code == 200
            assert r.json()["match"]["status"] == "unmatched"
            assert r.json()["match"]["char_start"] is None
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)
