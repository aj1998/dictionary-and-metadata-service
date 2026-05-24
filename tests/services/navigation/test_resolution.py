"""Integration tests for keyword resolution endpoint.

Tests: exact match, alias match, suffix strip, and none cases.
Uses real Postgres; Neo4j is mocked (resolution is pure-Postgres).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def keyword_with_alias(client: AsyncClient):
    from jain_kb_common.db.postgres.keywords import Keyword, KeywordAlias

    async with client.state() as session:  # type: ignore[attr-defined]
        kw = Keyword(
            natural_key="आत्मा",
            display_text="आत्मा",
            source_url="https://www.jainkosh.org/wiki/आत्मा",
        )
        session.add(kw)
        await session.flush()

        alias = KeywordAlias(
            keyword_id=kw.id,
            alias_text="आतम",
            source="admin",
        )
        session.add(alias)
        await session.commit()
        return {"keyword": kw.natural_key, "alias": "आतम"}


class TestResolveKeyword:
    async def test_exact_match(self, client: AsyncClient, keyword_with_alias):
        r = await client.get("/v1/keywords/आत्मा/resolve")
        assert r.status_code == 200
        data = r.json()
        assert data["matched_keyword_natural_key"] == "आत्मा"
        assert data["match_kind"] == "exact"
        assert data["input"] == "आत्मा"

    async def test_alias_match(self, client: AsyncClient, keyword_with_alias):
        r = await client.get("/v1/keywords/आतम/resolve")
        assert r.status_code == 200
        data = r.json()
        assert data["matched_keyword_natural_key"] == "आत्मा"
        assert data["match_kind"] == "alias"

    async def test_suffix_strip_exact(self, client: AsyncClient):
        from jain_kb_common.db.postgres.keywords import Keyword

        async with client.state() as session:  # type: ignore[attr-defined]
            kw = Keyword(natural_key="मोक्ष", display_text="मोक्ष")
            session.add(kw)
            await session.commit()

        # "मोक्षा" → strip ा → "मोक्ष" (exact match)
        r = await client.get("/v1/keywords/मोक्षा/resolve")
        assert r.status_code == 200
        data = r.json()
        assert data["matched_keyword_natural_key"] == "मोक्ष"
        assert data["match_kind"] == "suffix_strip"

    async def test_no_match(self, client: AsyncClient):
        r = await client.get("/v1/keywords/nonexistent/resolve")
        assert r.status_code == 200
        data = r.json()
        assert data["matched_keyword_natural_key"] is None
        assert data["match_kind"] == "none"

    async def test_no_match_returns_200(self, client: AsyncClient):
        """Status is always 200 even when match_kind is 'none'."""
        r = await client.get("/v1/keywords/xyz123/resolve")
        assert r.status_code == 200
