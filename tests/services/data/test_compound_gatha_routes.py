"""Phase 5 — compound gatha route tests.

Tests for:
  - GET /v1/shastras/{shastra_nk}/gathas/{raw_id} (compound + legacy)
  - GET /v1/shastras/{shastra_nk}/gathas/{raw_id}/adjacent
  - 400 on arity mismatch for compound shastras
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_COMPOUND_SHASTRA_NK = "परमात्मप्रकाश"
_LEGACY_SHASTRA_NK = "samaysaar"


@pytest_asyncio.fixture
async def compound_data(client: AsyncClient):
    """Seed परमात्मप्रकाश with 4 gathas across 2 adhikaars."""
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.gathas import Gatha
    from jain_kb_common.db.postgres.shastras import Shastra

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="yogindra",
            display_name=[{"lang": "hin", "script": "Deva", "text": "योगीन्द्र"}],
            kind="acharya",
        )
        session.add(author)
        await session.flush()

        shastra = Shastra(
            natural_key=_COMPOUND_SHASTRA_NK,
            title=[{"lang": "hin", "script": "Deva", "text": "परमात्मप्रकाश"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        # adhikaar 1: gathas 2, 10, 21; adhikaar 2: gatha 1
        for adhikaar, gatha_num in [(1, 2), (1, 10), (1, 21), (2, 1)]:
            g = Gatha(
                natural_key=f"{_COMPOUND_SHASTRA_NK}:अधिकार:{adhikaar}:गाथा:{gatha_num}",
                shastra_id=shastra.id,
                gatha_number=f"अधिकार:{adhikaar}:गाथा:{gatha_num}",
                adhikaar={"अधिकार": str(adhikaar), "परमात्मप्रकाशगाथा": str(gatha_num)},
                heading=[],
            )
            session.add(g)
        await session.commit()
        return {"shastra_nk": _COMPOUND_SHASTRA_NK}


@pytest_asyncio.fixture
async def legacy_data(client: AsyncClient):
    """Seed समयसार with gathas 1, 2, 8."""
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
            natural_key=_LEGACY_SHASTRA_NK,
            title=[{"lang": "hin", "script": "Deva", "text": "समयसार"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        for num in [1, 2, 8]:
            g = Gatha(
                natural_key=f"{_LEGACY_SHASTRA_NK}:गाथा:{num}",
                shastra_id=shastra.id,
                gatha_number=str(num),
                adhikaar=[],
                heading=[],
            )
            session.add(g)
        await session.commit()
        return {"shastra_nk": _LEGACY_SHASTRA_NK}


class TestCompoundGathaRoute:
    async def test_compound_route_resolves_to_correct_pg_row(self, client: AsyncClient, compound_data):
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1,2")
        assert r.status_code == 200
        body = r.json()
        assert body["natural_key"] == f"{_COMPOUND_SHASTRA_NK}:अधिकार:1:गाथा:2"
        assert body["gatha_number"] == "अधिकार:1:गाथा:2"

    async def test_compound_route_returns_identifier_block(self, client: AsyncClient, compound_data):
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1,2")
        assert r.status_code == 200
        body = r.json()
        assert "identifier" in body
        ident = body["identifier"]
        assert ident["is_compound"] is True
        assert ident["compact"] == "1,2"
        assert len(ident["fields"]) == 2
        assert ident["fields"][0]["value"] == "1"
        assert ident["fields"][1]["value"] == "2"

    async def test_compound_route_400_on_arity_mismatch(self, client: AsyncClient, compound_data):
        # परमात्मप्रकाश expects 2 values; "1" has only 1
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1")
        assert r.status_code == 400

    async def test_compound_route_404_for_nonexistent_gatha(self, client: AsyncClient, compound_data):
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1,99")
        assert r.status_code == 404

    async def test_legacy_route_unchanged(self, client: AsyncClient, legacy_data):
        r = await client.get(f"/v1/shastras/{_LEGACY_SHASTRA_NK}/gathas/8")
        assert r.status_code == 200
        body = r.json()
        assert body["natural_key"] == f"{_LEGACY_SHASTRA_NK}:गाथा:8"
        ident = body["identifier"]
        assert ident["is_compound"] is False
        assert ident["compact"] == "8"


class TestAdjacentGathaEndpoint:
    async def test_adjacent_returns_prev_and_next(self, client: AsyncClient, compound_data):
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1,10/adjacent")
        assert r.status_code == 200
        body = r.json()
        assert body["previous"]["compact"] == "1,2"
        assert body["next"]["compact"] == "1,21"

    async def test_adjacent_first_gatha_has_no_prev(self, client: AsyncClient, compound_data):
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1,2/adjacent")
        assert r.status_code == 200
        body = r.json()
        assert body["previous"] is None
        assert body["next"]["compact"] == "1,10"

    async def test_adjacent_cross_adhikaar_boundary(self, client: AsyncClient, compound_data):
        """Gatha 1,21 (last in adhikaar 1) → next is 2,1 (first in adhikaar 2)."""
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1,21/adjacent")
        assert r.status_code == 200
        body = r.json()
        assert body["next"]["compact"] == "2,1"

    async def test_adjacent_last_gatha_has_no_next(self, client: AsyncClient, compound_data):
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/2,1/adjacent")
        assert r.status_code == 200
        body = r.json()
        assert body["next"] is None

    async def test_adjacent_numeric_order_not_lexical(self, client: AsyncClient, compound_data):
        """Gathas ordered as 2, 10, 21 numerically — not lexically (10 < 2 lexically)."""
        r = await client.get(f"/v1/shastras/{_COMPOUND_SHASTRA_NK}/gathas/1,2/adjacent")
        assert r.status_code == 200
        assert r.json()["next"]["compact"] == "1,10"

    async def test_adjacent_legacy_shastra(self, client: AsyncClient, legacy_data):
        r = await client.get(f"/v1/shastras/{_LEGACY_SHASTRA_NK}/gathas/2/adjacent")
        assert r.status_code == 200
        body = r.json()
        assert body["previous"]["compact"] == "1"
        assert body["next"]["compact"] == "8"
