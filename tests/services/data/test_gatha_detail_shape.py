"""4A — GathaDetail shape audit.

Verifies that the direct_retrieval fields required by Phase 4 spec are
present in the response from GET /v1/gathas/{ident}.

Field mapping (spec name → current field):
  shastra_natural_key  → shastra.natural_key          ✅ present
  number               → gatha_number                 ✅ present
  prakrit              → prakrit                       ✅ present (None if no Mongo doc)
  sanskrit_chhaya      → sanskrit                      ✅ present (None if no Mongo doc)
  hindi_anyavaarth     → hindi_chhand                  ✅ present ([] if no Mongo doc)
  word_meanings        → word_meanings                 ✅ present
  bhavarth_hi          → teeka_bhaavarth               ✅ via ?include=teeka_bhaavarth
  teeka_blocks_hi      → teeka_hindi                   ✅ via ?include=teeka_hindi
  page_numbers         →                               ❌ NOT in Postgres model (see notes)
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_GOLDEN_NK = "samaysaar:006"
_GOLDEN_NUMBER = "006"


async def _seed_gatha(client: AsyncClient) -> dict:
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
            natural_key="samaysaar",
            title=[{"lang": "hin", "script": "Deva", "text": "समयसार"}],
            author_id=author.id,
        )
        session.add(shastra)
        await session.flush()

        gatha = Gatha(
            natural_key=_GOLDEN_NK,
            shastra_id=shastra.id,
            gatha_number=_GOLDEN_NUMBER,
            adhikaar=[{"lang": "hin", "script": "Deva", "text": "जीव-अधिकार"}],
            heading=[{"lang": "hin", "script": "Deva", "text": "शुद्धात्मा का वर्णन"}],
        )
        session.add(gatha)
        await session.commit()
        return {
            "gatha_nk": gatha.natural_key,
            "shastra_nk": shastra.natural_key,
        }


class TestGathaDetailShape:
    """Audit that direct_retrieval fields are accessible from the gatha endpoint."""

    async def test_shastra_natural_key_present(self, client: AsyncClient):
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        body = r.json()
        # shastra_natural_key accessible via shastra.natural_key
        assert body["shastra"]["natural_key"] == "samaysaar"

    async def test_gatha_number_present(self, client: AsyncClient):
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        assert r.json()["gatha_number"] == _GOLDEN_NUMBER

    async def test_prakrit_field_present(self, client: AsyncClient):
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        body = r.json()
        # prakrit is None when no Mongo doc; field must be present
        assert "prakrit" in body

    async def test_sanskrit_field_present(self, client: AsyncClient):
        """sanskrit_chhaya maps to 'sanskrit' in the current schema."""
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        assert "sanskrit" in r.json()

    async def test_hindi_chhand_field_present(self, client: AsyncClient):
        """hindi_anyavaarth maps to 'hindi_chhand' in the current schema."""
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        body = r.json()
        assert "hindi_chhand" in body
        assert isinstance(body["hindi_chhand"], list)

    async def test_word_meanings_field_present(self, client: AsyncClient):
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        assert "word_meanings" in r.json()

    async def test_bhavarth_hi_via_include_param(self, client: AsyncClient):
        """bhavarth_hi (teeka_bhaavarth) is accessible via ?include=teeka_bhaavarth."""
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=teeka_bhaavarth")
        assert r.status_code == 200
        body = r.json()
        assert "teeka_bhaavarth" in body
        assert isinstance(body["teeka_bhaavarth"], list)

    async def test_teeka_blocks_hi_via_include_param(self, client: AsyncClient):
        """teeka_blocks_hi maps to 'teeka_hindi', accessible via ?include=teeka_hindi."""
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}?include=teeka_hindi")
        assert r.status_code == 200
        body = r.json()
        assert "teeka_hindi" in body
        assert isinstance(body["teeka_hindi"], list)

    async def test_all_include_fields_together(self, client: AsyncClient):
        data = await _seed_gatha(client)
        r = await client.get(
            f"/v1/gathas/{data['gatha_nk']}?include=teeka_mapping,teeka_sanskrit,teeka_hindi,teeka_bhaavarth"
        )
        assert r.status_code == 200
        body = r.json()
        for field in ("teeka_mapping", "teeka_sanskrit", "teeka_hindi", "teeka_bhaavarth"):
            assert field in body, f"Missing field: {field}"

    async def test_page_numbers_audit_not_in_model(self, client: AsyncClient):
        """page_numbers is NOT in the current Postgres/Mongo schema.
        This test documents the gap — the field is absent from the response.
        Fix: requires adding page_number to Gatha Postgres model + Mongo docs.
        """
        data = await _seed_gatha(client)
        r = await client.get(f"/v1/gathas/{data['gatha_nk']}")
        assert r.status_code == 200
        body = r.json()
        # Documented gap: page_numbers not yet in the data model
        assert "page_numbers" not in body
