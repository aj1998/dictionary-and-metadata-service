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
                "INSERT INTO keywords (id, natural_key, display_text, sources, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, ARRAY[]::text[], '[]'::jsonb)"
            ),
            {"id": kid, "nk": natural_key, "dt": natural_key},
        )
        await session.commit()
    return kid


@pytest.mark.asyncio
async def test_too_many_tokens_returns_422(client: AsyncClient) -> None:
    """Posting more than 32 tokens should return HTTP 422."""
    tokens = [f"token_{i}" for i in range(33)]
    resp = await client.post(URL, json={"tokens": tokens, "include_definitions": False})
    assert resp.status_code == 422
    detail = resp.json().get("detail", {})
    assert detail.get("code") == "tokens_too_many"


@pytest.mark.asyncio
async def test_exactly_32_tokens_is_allowed(client: AsyncClient) -> None:
    """Exactly 32 tokens should be accepted."""
    tokens = [f"token_{i}" for i in range(32)]
    resp = await client.post(URL, json={"tokens": tokens, "include_definitions": False})
    assert resp.status_code == 200
    assert len(resp.json()["resolutions"]) == 32


@pytest.mark.asyncio
async def test_fuzzy_top_k_clamped_to_20(client: AsyncClient) -> None:
    """fuzzy_top_k > 20 is clamped to 20 — suggestions cannot exceed 20."""
    factory = client.state  # type: ignore[attr-defined]
    # Insert many similar keywords so fuzzy can return results
    for i in range(30):
        await _insert_keyword(factory, f"कर्म{i:02d}")

    resp = await client.post(
        URL,
        json={
            "tokens": ["कर्म"],
            "include_definitions": False,
            "min_similarity": 0.1,
            "fuzzy_top_k": 25,  # over the cap
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    if r["match_kind"] == "none" and r["suggestions"]:
        assert len(r["suggestions"]) <= 20


@pytest.mark.asyncio
async def test_tool_trace_id_present(client: AsyncClient) -> None:
    """Every response must include a tool_trace_id."""
    resp = await client.post(
        URL, json={"tokens": ["आत्मा"], "include_definitions": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tool_trace_id" in data
    assert len(data["tool_trace_id"]) > 0


@pytest.mark.asyncio
async def test_healthz(client: AsyncClient) -> None:
    """Health endpoint should return ok."""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
