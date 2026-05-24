from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def kalash_data(client: AsyncClient):
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.kalashas import Kalash
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.teekas import Teeka

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="kundkund",
            display_name=[{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
            kind="acharya",
        )
        teekakar = Author(
            natural_key="amritchandra",
            display_name=[{"lang": "hin", "script": "Deva", "text": "अमृतचंद्राचार्य"}],
            kind="acharya",
        )
        session.add_all([author, teekakar])
        await session.flush()

        shastra = Shastra(
            natural_key="pravachansaar",
            title=[{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        teeka = Teeka(
            natural_key="pravachansaar:amritchandra",
            shastra_id=shastra.id,
            teekakar_id=teekakar.id,
        )
        session.add(teeka)
        await session.flush()

        kalash = Kalash(
            natural_key="pravachansaar:amritchandra:kalash:001",
            teeka_id=teeka.id,
            kalash_number="001",
        )
        session.add(kalash)
        await session.commit()
        await session.refresh(kalash)
        return {
            "kalash_id": str(kalash.id),
            "kalash_nk": kalash.natural_key,
            "teeka_nk": teeka.natural_key,
            "teeka_id": str(teeka.id),
        }


class TestListKalashas:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/kalashas")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_kalash(self, client: AsyncClient, kalash_data):
        r = await client.get("/v1/kalashas")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_teeka_nk(self, client: AsyncClient, kalash_data):
        r = await client.get(f"/v1/kalashas?teeka_id={kalash_data['teeka_nk']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_teeka_uuid(self, client: AsyncClient, kalash_data):
        r = await client.get(f"/v1/kalashas?teeka_id={kalash_data['teeka_id']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_cache_control(self, client: AsyncClient):
        r = await client.get("/v1/kalashas")
        assert "Cache-Control" in r.headers


class TestKalashDetail:
    async def test_basic(self, client: AsyncClient, kalash_data):
        r = await client.get(f"/v1/kalashas/{kalash_data['kalash_nk']}")
        assert r.status_code == 200
        data = r.json()
        assert data["natural_key"] == "pravachansaar:amritchandra:kalash:001"
        assert data["teeka"]["natural_key"] == "pravachansaar:amritchandra"
        assert data["teeka"]["teekakar"]["natural_key"] == "amritchandra"
        assert data["bhaavarth"] == []

    async def test_by_uuid(self, client: AsyncClient, kalash_data):
        r = await client.get(f"/v1/kalashas/{kalash_data['kalash_id']}")
        assert r.status_code == 200

    async def test_include_default_is_all(self, client: AsyncClient, kalash_data):
        r = await client.get(f"/v1/kalashas/{kalash_data['kalash_nk']}")
        assert r.status_code == 200
        data = r.json()
        assert "sanskrit" in data
        assert "hindi" in data
        assert "bhaavarth" in data

    async def test_include_none(self, client: AsyncClient, kalash_data):
        r = await client.get(f"/v1/kalashas/{kalash_data['kalash_nk']}?include=")
        assert r.status_code == 200

    async def test_bhaavarth_is_array(self, client: AsyncClient, kalash_data):
        r = await client.get(f"/v1/kalashas/{kalash_data['kalash_nk']}")
        assert isinstance(r.json()["bhaavarth"], list)

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/kalashas/nonexistent:teeka:kalash:999")
        assert r.status_code == 404


class TestKalashWordMeanings:
    async def test_404_when_no_kalash(self, client: AsyncClient):
        r = await client.get("/v1/kalashas/nonexistent:kalash:999/word_meanings")
        assert r.status_code == 404

    async def test_404_when_kalash_exists_but_no_word_meanings(
        self, client: AsyncClient, kalash_data
    ):
        r = await client.get(
            f"/v1/kalashas/{kalash_data['kalash_nk']}/word_meanings"
        )
        assert r.status_code == 404

    async def test_200_with_word_meanings(self, client: AsyncClient, kalash_data):
        from unittest.mock import AsyncMock, MagicMock

        from services.data_service import deps
        from services.data_service.main import app

        wm_doc = {
            "natural_key": f"{kalash_data['kalash_nk']}:word_meanings",
            "kalash_natural_key": kalash_data["kalash_nk"],
            "teeka_natural_key": kalash_data["teeka_nk"],
            "kalash_number": "001",
            "entries": [
                {"source_word": "स्वानुभूत्या", "meaning": "स्वानुभूति से", "position": 1}
            ],
        }

        def _make_wm_collection():
            col = MagicMock()
            col.find_one = AsyncMock(return_value=wm_doc)
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[])
            col.find = MagicMock(return_value=cursor)
            return col

        mock_mongo = MagicMock()
        mock_mongo.__getitem__ = MagicMock(side_effect=lambda name: _make_wm_collection())

        async def _override_mongo():
            return mock_mongo

        original_override = app.dependency_overrides.get(deps.get_mongo_db)
        app.dependency_overrides[deps.get_mongo_db] = _override_mongo
        try:
            r = await client.get(
                f"/v1/kalashas/{kalash_data['kalash_nk']}/word_meanings"
            )
            assert r.status_code == 200
            data = r.json()
            assert data["kalash_natural_key"] == kalash_data["kalash_nk"]
            assert data["kalash_number"] == "001"
            assert len(data["entries"]) == 1
            assert data["entries"][0]["source_word"] == "स्वानुभूत्या"
        finally:
            if original_override is not None:
                app.dependency_overrides[deps.get_mongo_db] = original_override
            else:
                app.dependency_overrides.pop(deps.get_mongo_db, None)
