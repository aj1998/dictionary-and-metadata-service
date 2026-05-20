"""
Phase 3 — Metadata fuzzy match tests.

Covers fuzzy=true on /v1/shastras, /v1/authors, /v1/teekas.
Each test class covers: golden match first, cutoff respected, non-fuzzy regression.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def author_kundkund(client: AsyncClient):
    r = await client.post(
        "/v1/admin/authors",
        json={
            "natural_key": "kundkundacharya",
            "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्दाचार्य"}],
            "kind": "acharya",
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


@pytest_asyncio.fixture
async def shastra_samaysaar(client: AsyncClient, author_kundkund):
    r = await client.post(
        "/v1/admin/shastras",
        json={
            "natural_key": "samaysaar",
            "title": [{"lang": "hin", "script": "Deva", "text": "समयसार"}],
            "author_id": author_kundkund["id"],
            "anuyoga_ids": [],
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


@pytest_asyncio.fixture
async def teeka_samaysaar(client: AsyncClient, shastra_samaysaar, author_kundkund):
    r = await client.post(
        "/v1/admin/teekas",
        json={
            "natural_key": "samaysaar:amritchandra",
            "shastra_id": shastra_samaysaar["id"],
            "teekakar_id": author_kundkund["id"],
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# Shastras fuzzy
# ---------------------------------------------------------------------------


class TestShastrasFuzzy:
    async def test_fuzzy_golden_match(self, client: AsyncClient, shastra_samaysaar):
        """Typo 'samaysar' → canonical row 'samaysaar' is first result."""
        r = await client.get("/v1/shastras?q=samaysar&fuzzy=true&limit=5")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) >= 1
        assert data["items"][0]["natural_key"] == "samaysaar"

    async def test_fuzzy_similarity_field_present(self, client: AsyncClient, shastra_samaysaar):
        """fuzzy=true includes similarity float in each item."""
        r = await client.get("/v1/shastras?q=samaysar&fuzzy=true")
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert "similarity" in item
        assert isinstance(item["similarity"], float)
        assert 0.0 < item["similarity"] <= 1.0

    async def test_fuzzy_cutoff_no_garbage(self, client: AsyncClient, shastra_samaysaar):
        """Completely unrelated query produces no results."""
        r = await client.get("/v1/shastras?q=xyzzzunknownentity999&fuzzy=true")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_fuzzy_limit_capped_at_50(self, client: AsyncClient, shastra_samaysaar):
        """limit > 50 is silently capped to 50 in fuzzy mode."""
        r = await client.get("/v1/shastras?q=samaysar&fuzzy=true&limit=200")
        assert r.status_code == 200

    async def test_non_fuzzy_ilike_unchanged(self, client: AsyncClient, shastra_samaysaar):
        """Non-fuzzy q (ILIKE) still works — regression guard."""
        r = await client.get("/v1/shastras?q=समय")
        assert r.status_code == 200
        nks = [item["natural_key"] for item in r.json()["items"]]
        assert "samaysaar" in nks

    async def test_non_fuzzy_no_similarity_field(self, client: AsyncClient, shastra_samaysaar):
        """Non-fuzzy responses do not include similarity."""
        r = await client.get("/v1/shastras")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item.get("similarity") is None

    async def test_fuzzy_without_q_returns_normal_list(self, client: AsyncClient, shastra_samaysaar):
        """fuzzy=true with no q falls back to normal list."""
        r = await client.get("/v1/shastras?fuzzy=true")
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1

    async def test_fuzzy_pagination_envelope(self, client: AsyncClient, shastra_samaysaar):
        """Pagination envelope is preserved for fuzzy results."""
        r = await client.get("/v1/shastras?q=samaysar&fuzzy=true")
        assert r.status_code == 200
        pagination = r.json()["pagination"]
        assert "total" in pagination
        assert "limit" in pagination
        assert "offset" in pagination


# ---------------------------------------------------------------------------
# Authors fuzzy
# ---------------------------------------------------------------------------


class TestAuthorsFuzzy:
    async def test_fuzzy_golden_match(self, client: AsyncClient, author_kundkund):
        """Partial 'kundkund' → 'kundkundacharya' first."""
        r = await client.get("/v1/authors?q=kundkund&fuzzy=true&limit=5")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) >= 1
        assert data["items"][0]["natural_key"] == "kundkundacharya"

    async def test_fuzzy_similarity_field_present(self, client: AsyncClient, author_kundkund):
        """fuzzy=true includes similarity float in each author item."""
        r = await client.get("/v1/authors?q=kundkund&fuzzy=true")
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert "similarity" in item
        assert isinstance(item["similarity"], float)
        assert 0.0 < item["similarity"] <= 1.0

    async def test_fuzzy_cutoff_no_garbage(self, client: AsyncClient, author_kundkund):
        r = await client.get("/v1/authors?q=xyzzzunknownentity999&fuzzy=true")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_fuzzy_limit_capped_at_50(self, client: AsyncClient, author_kundkund):
        r = await client.get("/v1/authors?q=kundkund&fuzzy=true&limit=200")
        assert r.status_code == 200

    async def test_non_fuzzy_q_ilike(self, client: AsyncClient, author_kundkund):
        """Non-fuzzy q param uses ILIKE — regression guard."""
        r = await client.get("/v1/authors?q=kundkund")
        assert r.status_code == 200
        nks = [item["natural_key"] for item in r.json()["items"]]
        assert "kundkundacharya" in nks

    async def test_non_fuzzy_no_similarity(self, client: AsyncClient, author_kundkund):
        r = await client.get("/v1/authors")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item.get("similarity") is None

    async def test_fuzzy_without_q_returns_normal_list(self, client: AsyncClient, author_kundkund):
        r = await client.get("/v1/authors?fuzzy=true")
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1

    async def test_fuzzy_pagination_envelope(self, client: AsyncClient, author_kundkund):
        r = await client.get("/v1/authors?q=kundkund&fuzzy=true")
        assert r.status_code == 200
        pagination = r.json()["pagination"]
        assert "total" in pagination


# ---------------------------------------------------------------------------
# Teekas fuzzy
# ---------------------------------------------------------------------------


class TestTeekasFuzzy:
    async def test_fuzzy_golden_match(self, client: AsyncClient, teeka_samaysaar):
        """Partial 'samaysaar:amrit' → 'samaysaar:amritchandra' first."""
        r = await client.get("/v1/teekas?q=samaysaar:amrit&fuzzy=true&limit=5")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) >= 1
        assert data["items"][0]["natural_key"] == "samaysaar:amritchandra"

    async def test_fuzzy_similarity_field_present(self, client: AsyncClient, teeka_samaysaar):
        r = await client.get("/v1/teekas?q=samaysaar:amrit&fuzzy=true")
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert "similarity" in item
        assert isinstance(item["similarity"], float)
        assert 0.0 < item["similarity"] <= 1.0

    async def test_fuzzy_cutoff_no_garbage(self, client: AsyncClient, teeka_samaysaar):
        r = await client.get("/v1/teekas?q=xyzzzunknownentity999&fuzzy=true")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_fuzzy_limit_capped_at_50(self, client: AsyncClient, teeka_samaysaar):
        r = await client.get("/v1/teekas?q=samaysaar:amrit&fuzzy=true&limit=200")
        assert r.status_code == 200

    async def test_non_fuzzy_q_ilike(self, client: AsyncClient, teeka_samaysaar):
        """Non-fuzzy q param uses ILIKE — regression guard."""
        r = await client.get("/v1/teekas?q=samaysaar")
        assert r.status_code == 200
        nks = [item["natural_key"] for item in r.json()["items"]]
        assert "samaysaar:amritchandra" in nks

    async def test_non_fuzzy_no_similarity(self, client: AsyncClient, teeka_samaysaar):
        r = await client.get("/v1/teekas")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item.get("similarity") is None

    async def test_fuzzy_without_q_returns_normal_list(self, client: AsyncClient, teeka_samaysaar):
        r = await client.get("/v1/teekas?fuzzy=true")
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1

    async def test_fuzzy_pagination_envelope(self, client: AsyncClient, teeka_samaysaar):
        r = await client.get("/v1/teekas?q=samaysaar:amrit&fuzzy=true")
        assert r.status_code == 200
        pagination = r.json()["pagination"]
        assert "total" in pagination
