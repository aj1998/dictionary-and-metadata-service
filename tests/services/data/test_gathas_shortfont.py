"""Tests for shortfont_entries hydration on teeka_bhaavarth and kalash bhaavarth."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_SHORTFONT_ENTRY = {
    "marker_number": 4,
    "marker_devanagari": "४",
    "anchor_text": "मोक्ष-मार्ग-प्रपंच-सूचक",
    "meaning": "मोक्ष का विस्तार बतलाने वाली।",
    "is_definition": True,
    "occurrences": [{"start_offset": 10, "end_offset": 34}],
}


async def _seed_gatha(client: AsyncClient) -> dict:
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.gathas import Gatha
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.teekas import Teeka

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="kundkund_sf",
            display_name=[{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
            kind="acharya",
        )
        session.add(author)
        await session.flush()

        shastra = Shastra(
            natural_key="panchaastikaya",
            title=[{"lang": "hin", "script": "Deva", "text": "पञ्चास्तिकाय"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        teeka = Teeka(
            natural_key="panchaastikaya:amritchandra",
            shastra_id=shastra.id,
            teekakar_id=author.id,
        )
        session.add(teeka)
        await session.flush()

        gatha = Gatha(
            natural_key="panchaastikaya:गाथा:161",
            shastra_id=shastra.id,
            gatha_number="161",
            adhikaar=[],
            heading=[],
        )
        session.add(gatha)
        await session.commit()

        return {
            "gatha_nk": gatha.natural_key,
            "gatha_number": gatha.gatha_number,
            "teeka_nk": teeka.natural_key,
            "shastra_nk": shastra.natural_key,
        }


def _mongo_with_bhaavarth_and_shortfont(gatha_nk: str, gatha_number: str, shastra_nk: str) -> MagicMock:
    pub_nk = f"{shastra_nk}:amritchandra:0"
    bh_nk = f"{pub_nk}:गाथा:टीका:भावार्थ:{gatha_number}"
    sf_nk = f"{bh_nk}:shortfont"

    mongo = MagicMock()

    def _make_col(name: str) -> MagicMock:
        col = MagicMock()
        if name == "gatha_teeka_bhaavarth_hindi":
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[{
                "_id": "oid_bh",
                "natural_key": bh_nk,
                "gatha_teeka_natural_key": f"{shastra_nk}:amritchandra:{gatha_number}",
                "publication_natural_key": pub_nk,
                "publisher_id": "0",
                "text": [{"lang": "hin", "script": "Deva", "text": "अब मोक्ष-मार्ग-प्रपंच-सूचक चूलिका है।"}],
            }])
            col.find = MagicMock(return_value=cursor)
            col.find_one = AsyncMock(return_value=None)
        elif name == "gatha_teeka_bhaavarth_shortfont":
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[{
                "_id": "oid_sf",
                "natural_key": sf_nk,
                "bhaavarth_natural_key": bh_nk,
                "gatha_natural_key": gatha_nk,
                "gatha_number": gatha_number,
                "entries": [_SHORTFONT_ENTRY],
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


def _mongo_no_shortfont(gatha_nk: str, gatha_number: str, shastra_nk: str) -> MagicMock:
    pub_nk = f"{shastra_nk}:amritchandra:0"
    bh_nk = f"{pub_nk}:गाथा:टीका:भावार्थ:{gatha_number}"

    mongo = MagicMock()

    def _make_col(name: str) -> MagicMock:
        col = MagicMock()
        if name == "gatha_teeka_bhaavarth_hindi":
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[{
                "_id": "oid_bh",
                "natural_key": bh_nk,
                "gatha_teeka_natural_key": f"{shastra_nk}:amritchandra:{gatha_number}",
                "publication_natural_key": pub_nk,
                "publisher_id": "0",
                "text": [{"lang": "hin", "script": "Deva", "text": "सामान्य भावार्थ पाठ।"}],
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


class TestTeekaBhaavarthShortfont:
    async def test_shortfont_entries_present_when_mongo_doc_exists(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        data = await _seed_gatha(client)
        mongo = _mongo_with_bhaavarth_and_shortfont(
            data["gatha_nk"], data["gatha_number"], data["shastra_nk"]
        )
        app.dependency_overrides[deps.get_mongo_db] = lambda: mongo
        try:
            r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=teeka_bhaavarth")
            assert r.status_code == 200
            body = r.json()
            bhs = body.get("teeka_bhaavarth", [])
            assert len(bhs) == 1
            entries = bhs[0].get("shortfont_entries")
            assert isinstance(entries, list)
            assert len(entries) == 1
            assert entries[0]["anchor_text"] == "मोक्ष-मार्ग-प्रपंच-सूचक"
            assert entries[0]["marker_devanagari"] == "४"
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_shortfont_entries_empty_when_no_mongo_doc(self, client: AsyncClient):
        from services.core_service import deps
        from services.core_service.main import app

        data = await _seed_gatha(client)
        mongo = _mongo_no_shortfont(
            data["gatha_nk"], data["gatha_number"], data["shastra_nk"]
        )
        app.dependency_overrides[deps.get_mongo_db] = lambda: mongo
        try:
            r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=teeka_bhaavarth")
            assert r.status_code == 200
            body = r.json()
            bhs = body.get("teeka_bhaavarth", [])
            assert len(bhs) == 1
            entries = bhs[0].get("shortfont_entries", [])
            assert entries == []
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)

    async def test_shortfont_not_included_without_teeka_bhaavarth(self, client: AsyncClient):
        """shortfont_entries should not appear if teeka_bhaavarth is not in include."""
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        body = r.json()
        assert "teeka_bhaavarth" not in body

    async def test_shortfont_id_stripped(self, client: AsyncClient):
        """_id field from MongoDB must not leak into shortfont_entries."""
        from services.core_service import deps
        from services.core_service.main import app

        data = await _seed_gatha(client)
        mongo = _mongo_with_bhaavarth_and_shortfont(
            data["gatha_nk"], data["gatha_number"], data["shastra_nk"]
        )
        app.dependency_overrides[deps.get_mongo_db] = lambda: mongo
        try:
            r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=teeka_bhaavarth")
            assert r.status_code == 200
            bh = r.json()["teeka_bhaavarth"][0]
            assert "_id" not in bh
        finally:
            app.dependency_overrides.pop(deps.get_mongo_db, None)
