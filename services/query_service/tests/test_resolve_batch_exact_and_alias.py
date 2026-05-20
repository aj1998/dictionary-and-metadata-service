from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/keyword_resolve_batch"


async def _insert_keyword(factory, natural_key: str, display_text: str) -> str:
    """Insert a keyword and return its id."""
    kid = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, '[]'::jsonb)"
            ),
            {"id": kid, "nk": natural_key, "dt": display_text},
        )
        await session.commit()
    return kid


async def _insert_alias(factory, keyword_id: str, alias_text: str) -> None:
    """Insert an alias for a keyword."""
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keyword_aliases (id, keyword_id, alias_text, source) "
                "VALUES (:id, :kid, :alias, 'test')"
            ),
            {"id": str(uuid.uuid4()), "kid": keyword_id, "alias": alias_text},
        )
        await session.commit()


@pytest.mark.asyncio
async def test_exact_match(client: AsyncClient) -> None:
    factory = client.state  # type: ignore[attr-defined]
    kid = await _insert_keyword(factory, "आत्मा", "आत्मा")

    resp = await client.post(URL, json={"tokens": ["आत्मा"], "include_definitions": False})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["resolutions"]) == 1
    r = data["resolutions"][0]
    assert r["match_kind"] == "exact"
    assert r["keyword_natural_key"] == "आत्मा"
    assert r["keyword_id"] == kid
    assert r["input_token"] == "आत्मा"


@pytest.mark.asyncio
async def test_alias_match(client: AsyncClient) -> None:
    factory = client.state  # type: ignore[attr-defined]
    kid = await _insert_keyword(factory, "आत्मा", "आत्मा")
    await _insert_alias(factory, kid, "आत्मन्")

    resp = await client.post(URL, json={"tokens": ["आत्मन्"], "include_definitions": False})
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    assert r["match_kind"] == "alias"
    assert r["keyword_natural_key"] == "आत्मा"
    assert r["input_token"] == "आत्मन्"


@pytest.mark.asyncio
async def test_suffix_strip_match(client: AsyncClient) -> None:
    factory = client.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "आत्मा", "आत्मा")

    # "आत्माओं" strips suffix "ओं" wait — let's use a token that strip gives us आत्मा
    # "आत्माओं" -> strip suffix "ओं" (in list as "ों") may not work; use "आत्माका" -> strip "का" -> "आत्मा"
    resp = await client.post(URL, json={"tokens": ["आत्माका"], "include_definitions": False})
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    assert r["match_kind"] == "suffix_strip"
    assert r["keyword_natural_key"] == "आत्मा"


@pytest.mark.asyncio
async def test_no_match_returns_none(client: AsyncClient) -> None:
    resp = await client.post(
        URL, json={"tokens": ["xyznonexistent"], "include_definitions": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    assert r["match_kind"] == "none"
    assert r["keyword_natural_key"] is None
    assert r["keyword_id"] is None


@pytest.mark.asyncio
async def test_exact_takes_priority_over_alias(client: AsyncClient) -> None:
    """If a token matches both as exact and as alias (edge case), exact wins."""
    factory = client.state  # type: ignore[attr-defined]
    kid1 = await _insert_keyword(factory, "धर्म", "धर्म")
    kid2 = await _insert_keyword(factory, "अधर्म", "अधर्म")
    # Make "धर्म" also an alias for अधर्म (contrived, but tests priority)
    await _insert_alias(factory, kid2, "धर्म")

    resp = await client.post(URL, json={"tokens": ["धर्म"], "include_definitions": False})
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["match_kind"] == "exact"
    assert r["keyword_natural_key"] == "धर्म"
