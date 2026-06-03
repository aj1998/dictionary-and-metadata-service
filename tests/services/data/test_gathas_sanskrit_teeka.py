"""Tests for the kalashas include option added to GET /v1/gathas/{nk}."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _seed_gatha_with_kalash(client: AsyncClient) -> dict:
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.gathas import Gatha
    from jain_kb_common.db.postgres.kalashas import Kalash
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.teekas import Teeka

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="amritchandra",
            display_name=[{"lang": "hin", "script": "Deva", "text": "अमृतचन्द्र"}],
            kind="acharya",
        )
        session.add(author)
        await session.flush()

        shastra = Shastra(
            natural_key="samaysaar",
            title=[{"lang": "hin", "script": "Deva", "text": "समयसार"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        teeka = Teeka(
            natural_key="samaysaar:amritchandra",
            shastra_id=shastra.id,
            teekakar_id=author.id,
        )
        session.add(teeka)
        await session.flush()

        gatha = Gatha(
            natural_key="samaysaar:001",
            shastra_id=shastra.id,
            gatha_number="001",
            adhikaar=[],
            heading=[],
        )
        session.add(gatha)
        await session.flush()

        kalash = Kalash(
            natural_key="samaysaar:amritchandra:kalash:001",
            teeka_id=teeka.id,
            kalash_number="001",
            gatha_id=gatha.id,
        )
        session.add(kalash)
        await session.commit()

        return {
            "gatha_nk": gatha.natural_key,
            "kalash_nk": kalash.natural_key,
            "gatha_id": str(gatha.id),
        }


def _mongo_with_kalash_docs(kalash_nk: str) -> MagicMock:
    mongo = MagicMock()

    def _make_col(name: str) -> MagicMock:
        col = MagicMock()
        if name == "kalash_sanskrit":
            col.find_one = AsyncMock(return_value={
                "_id": "oid1",
                "natural_key": f"{kalash_nk}:sanskrit",
                "text": [{"lang": "san", "script": "Deva", "text": "कलश संस्कृत पाठ"}],
            })
        elif name == "kalash_hindi":
            col.find_one = AsyncMock(return_value={
                "_id": "oid2",
                "natural_key": f"{kalash_nk}:hindi",
                "text": [{"lang": "hin", "script": "Deva", "text": "कलश हिन्दी पाठ"}],
            })
        elif name == "kalash_bhaavarth_hindi":
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[{
                "_id": "oid3",
                "natural_key": f"{kalash_nk}:bhaavarth:001",
                "kalash_natural_key": kalash_nk,
                "text": [{"lang": "hin", "script": "Deva", "text": "कलश भावार्थ"}],
            }])
            col.find = MagicMock(return_value=cursor)
            col.find_one = AsyncMock(return_value=None)
        else:
            col.find_one = AsyncMock(return_value=None)
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[])
            col.find = MagicMock(return_value=cursor)
        return col

    mongo.__getitem__ = MagicMock(side_effect=_make_col)
    return mongo


class TestGathasKalashasInclude:
    async def test_kalashas_not_in_response_without_include(self, client: AsyncClient):
        data = await _seed_gatha_with_kalash(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        assert "kalashas" not in r.json()

    async def test_kalashas_present_with_include(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        data = await _seed_gatha_with_kalash(client)
        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_kalash_docs(data["kalash_nk"])
        try:
            r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=kalashas")
            assert r.status_code == 200
            body = r.json()
            assert "kalashas" in body
            assert isinstance(body["kalashas"], list)
            assert len(body["kalashas"]) == 1
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_kalash_has_natural_key_and_number(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        data = await _seed_gatha_with_kalash(client)
        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_kalash_docs(data["kalash_nk"])
        try:
            r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=kalashas")
            assert r.status_code == 200
            kalash = r.json()["kalashas"][0]
            assert kalash["natural_key"] == data["kalash_nk"]
            assert kalash["kalash_number"] == "001"
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_kalash_has_sanskrit_hindi_bhaavarth(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        data = await _seed_gatha_with_kalash(client)
        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_kalash_docs(data["kalash_nk"])
        try:
            r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=kalashas")
            assert r.status_code == 200
            kalash = r.json()["kalashas"][0]
            assert kalash["sanskrit"] is not None
            assert kalash["hindi"] is not None
            assert isinstance(kalash["bhaavarth"], list)
            assert len(kalash["bhaavarth"]) == 1
            assert "_id" not in kalash["sanskrit"]
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_kalashas_empty_when_no_kalash_for_gatha(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        # seed a gatha with NO kalash
        from jain_kb_common.db.postgres.authors import Author
        from jain_kb_common.db.postgres.gathas import Gatha
        from jain_kb_common.db.postgres.shastras import Shastra

        async with client.state() as session:  # type: ignore[attr-defined]
            author = Author(
                natural_key="kundkund2",
                display_name=[{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
                kind="acharya",
            )
            session.add(author)
            await session.flush()
            shastra = Shastra(
                natural_key="niyamsaar",
                title=[{"lang": "hin", "script": "Deva", "text": "नियमसार"}],
                author_id=author.id,
            )
            session.add(shastra)
            await session.flush()
            gatha = Gatha(
                natural_key="niyamsaar:001",
                shastra_id=shastra.id,
                gatha_number="001",
                adhikaar=[],
                heading=[],
            )
            session.add(gatha)
            await session.commit()
            gatha_nk = gatha.natural_key

        app.dependency_overrides[deps.get_mongo_db] = lambda: _mongo_with_kalash_docs("unused")
        try:
            r = await client.get(f"/v1/gathas/{gatha_nk}?include=kalashas")
            assert r.status_code == 200
            assert r.json()["kalashas"] == []
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)
