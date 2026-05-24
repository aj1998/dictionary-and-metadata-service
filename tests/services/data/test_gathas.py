from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def gatha_data(client: AsyncClient):
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.gathas import Gatha
    from jain_kb_common.db.postgres.shastras import Shastra

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="kundkund",
            display_name=[{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
            kind="acharya",
        )
        session.add(author)
        await session.flush()

        shastra = Shastra(
            natural_key="pravachansaar",
            title=[{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        gatha = Gatha(
            natural_key="pravachansaar:039",
            shastra_id=shastra.id,
            gatha_number="039",
            adhikaar=[{"lang": "hin", "script": "Deva", "text": "ज्ञानतत्त्व-प्रज्ञापन-अधिकार"}],
            heading=[{"lang": "hin", "script": "Deva", "text": "भूत-भावि पर्यायों की असद्भूत संज्ञा है"}],
        )
        session.add(gatha)
        await session.commit()
        await session.refresh(gatha)
        await session.refresh(shastra)
        return {
            "gatha_id": str(gatha.id),
            "gatha_nk": gatha.natural_key,
            "shastra_nk": shastra.natural_key,
            "shastra_id": str(shastra.id),
        }


class TestListGathas:
    async def test_empty(self, client: AsyncClient):
        r = await client.get("/v1/gathas")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_returns_gatha(self, client: AsyncClient, gatha_data):
        r = await client.get("/v1/gathas")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_shastra_natural_key(self, client: AsyncClient, gatha_data):
        r = await client.get(f"/v1/gathas?shastra_id={gatha_data['shastra_nk']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_filter_by_shastra_uuid(self, client: AsyncClient, gatha_data):
        r = await client.get(f"/v1/gathas?shastra_id={gatha_data['shastra_id']}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    async def test_cache_control(self, client: AsyncClient):
        r = await client.get("/v1/gathas")
        assert "Cache-Control" in r.headers


class TestGathaDetail:
    async def test_basic(self, client: AsyncClient, gatha_data):
        r = await client.get(f"/v1/gathas/{gatha_data['gatha_nk']}")
        assert r.status_code == 200
        data = r.json()
        assert data["natural_key"] == "pravachansaar:039"
        assert data["shastra"]["natural_key"] == "pravachansaar"
        assert data["prakrit"] is None
        assert "teeka_mapping" not in data

    async def test_by_uuid(self, client: AsyncClient, gatha_data):
        r = await client.get(f"/v1/gathas/{gatha_data['gatha_id']}")
        assert r.status_code == 200

    async def test_include_teeka_mapping(self, client: AsyncClient, gatha_data):
        r = await client.get(f"/v1/gathas/{gatha_data['gatha_nk']}?include=teeka_mapping")
        assert r.status_code == 200
        data = r.json()
        assert "teeka_mapping" in data
        assert data["teeka_mapping"] == []
        assert "teeka_sanskrit" not in data

    async def test_include_all(self, client: AsyncClient, gatha_data):
        r = await client.get(
            f"/v1/gathas/{gatha_data['gatha_nk']}?include=teeka_mapping,teeka_sanskrit,teeka_hindi,teeka_bhaavarth"
        )
        assert r.status_code == 200
        data = r.json()
        assert "teeka_mapping" in data
        assert "teeka_sanskrit" in data
        assert "teeka_hindi" in data
        assert "teeka_bhaavarth" in data

    async def test_include_partial(self, client: AsyncClient, gatha_data):
        r = await client.get(
            f"/v1/gathas/{gatha_data['gatha_nk']}?include=teeka_hindi"
        )
        assert r.status_code == 200
        data = r.json()
        assert "teeka_hindi" in data
        assert "teeka_mapping" not in data

    async def test_404(self, client: AsyncClient):
        r = await client.get("/v1/gathas/nonexistent:999")
        assert r.status_code == 404
