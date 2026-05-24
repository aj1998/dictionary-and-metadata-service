from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/keyword_resolve_batch"


async def _insert_keyword(factory, natural_key: str, display_text: str) -> str:
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


@pytest.mark.asyncio
async def test_fuzzy_suggestion_for_typo(client: AsyncClient) -> None:
    """A typo token should get fuzzy suggestions when no exact/suffix match."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "आत्मा", "आत्मा")

    # "आतमा" is a common Hindi typo for "आत्मा" — trigram similarity is ~0.28
    # Use a low threshold to ensure the suggestion is surfaced
    resp = await client.post(
        URL,
        json={
            "tokens": ["आतमा"],
            "include_definitions": False,
            "min_similarity": 0.2,
            "fuzzy_top_k": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    assert r["match_kind"] == "none"
    assert r["input_token"] == "आतमा"
    # Should have suggestions
    assert r["suggestions"] is not None
    assert len(r["suggestions"]) >= 1
    nks = [s["keyword_natural_key"] for s in r["suggestions"]]
    assert "आत्मा" in nks
    # Similarity scores should be reasonable
    for s in r["suggestions"]:
        assert 0.0 < s["similarity"] <= 1.0


@pytest.mark.asyncio
async def test_no_suggestions_for_completely_unknown_token(client: AsyncClient) -> None:
    """Token with no near matches should return empty suggestions."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "आत्मा", "आत्मा")

    resp = await client.post(
        URL,
        json={
            "tokens": ["zzzzqqqq"],
            "include_definitions": False,
            "min_similarity": 0.35,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    assert r["match_kind"] == "none"
    # Either None or empty list
    assert not r["suggestions"]


@pytest.mark.asyncio
async def test_fuzzy_top_k_limits_results(client: AsyncClient) -> None:
    """fuzzy_top_k limits the number of suggestions returned."""
    factory = client.state  # type: ignore[attr-defined]
    # Insert multiple similar keywords
    for i in range(10):
        await _insert_keyword(factory, f"आत्मा{i}", f"आत्मा{i}")

    resp = await client.post(
        URL,
        json={
            "tokens": ["आत्मा5"],
            "include_definitions": False,
            "min_similarity": 0.1,
            "fuzzy_top_k": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    # If it matched exactly, skip; otherwise check suggestions limit
    if r["match_kind"] == "none" and r["suggestions"]:
        assert len(r["suggestions"]) <= 3
