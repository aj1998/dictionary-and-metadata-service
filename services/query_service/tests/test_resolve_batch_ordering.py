from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/keyword_resolve_batch"


async def _insert_keyword(factory, natural_key: str) -> str:
    kid = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, '[]'::jsonb)"
            ),
            {"id": kid, "nk": natural_key, "dt": natural_key},
        )
        await session.commit()
    return kid


@pytest.mark.asyncio
async def test_response_order_matches_request_order(client: AsyncClient) -> None:
    """Response resolutions must be in the same order as request tokens."""
    factory = client.state  # type: ignore[attr-defined]
    tokens_to_insert = ["कर्म", "धर्म", "मोक्ष"]
    for nk in tokens_to_insert:
        await _insert_keyword(factory, nk)

    request_tokens = ["मोक्ष", "धर्म", "कर्म"]
    resp = await client.post(
        URL, json={"tokens": request_tokens, "include_definitions": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    returned_tokens = [r["input_token"] for r in data["resolutions"]]
    assert returned_tokens == request_tokens


@pytest.mark.asyncio
async def test_response_with_mixed_resolution_preserves_order(client: AsyncClient) -> None:
    """Order is preserved with a mix of exact matches and unknowns."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "आत्मा")

    request_tokens = ["unknown_xyz", "आत्मा", "another_unknown"]
    resp = await client.post(
        URL, json={"tokens": request_tokens, "include_definitions": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    returned_tokens = [r["input_token"] for r in data["resolutions"]]
    assert returned_tokens == request_tokens
    assert data["resolutions"][0]["match_kind"] == "none"
    assert data["resolutions"][1]["match_kind"] == "exact"
    assert data["resolutions"][2]["match_kind"] == "none"


@pytest.mark.asyncio
async def test_duplicate_tokens_deduplicated(client: AsyncClient) -> None:
    """Duplicate tokens in the request should yield one result per unique token."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "आत्मा")

    request_tokens = ["आत्मा", "आत्मा", "आत्मा"]
    resp = await client.post(
        URL, json={"tokens": request_tokens, "include_definitions": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should return only 1 resolution for the unique token
    assert len(data["resolutions"]) == 1
    assert data["resolutions"][0]["input_token"] == "आत्मा"
    assert data["resolutions"][0]["match_kind"] == "exact"


@pytest.mark.asyncio
async def test_duplicate_mixed_tokens_deduplicated(client: AsyncClient) -> None:
    """Mixed duplicate tokens: each unique token appears once."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "कर्म")
    await _insert_keyword(factory, "धर्म")

    request_tokens = ["कर्म", "धर्म", "कर्म", "धर्म", "unknown"]
    resp = await client.post(
        URL, json={"tokens": request_tokens, "include_definitions": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    returned_tokens = [r["input_token"] for r in data["resolutions"]]
    # Each unique token appears once, in first-occurrence order
    assert returned_tokens == ["कर्म", "धर्म", "unknown"]
