from __future__ import annotations

import pytest
from httpx import AsyncClient

URL = "/v1/query/graphrag"


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_neo4j", [([], [], [])], indirect=True)
async def test_unknown_tokens_go_to_unresolved(client_with_neo4j: AsyncClient) -> None:
    """Tokens that don't resolve to any keyword land in unresolved_tokens."""
    resp = await client_with_neo4j.post(URL, json={
        "tokens": ["xyzunknown123", "abcnonexistent456"],
        "include_extracts": False,
        "include_neighbors": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ranked_topics"] == []
    assert "xyzunknown123" in data["unresolved_tokens"]
    assert "abcnonexistent456" in data["unresolved_tokens"]


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_neo4j", [([], [], [])], indirect=True)
async def test_mixed_tokens_partial_resolve(client_with_neo4j: AsyncClient) -> None:
    """Mix of known and unknown tokens: unknown go to unresolved, traversal runs for known."""
    import uuid
    from sqlalchemy import text

    factory = client_with_neo4j.state  # type: ignore[attr-defined]
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, sources, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, ARRAY[]::text[], '[]'::jsonb)"
            ),
            {"id": str(uuid.uuid4()), "nk": "द्रव्य", "dt": "द्रव्य"},
        )
        await session.commit()

    resp = await client_with_neo4j.post(URL, json={
        "tokens": ["द्रव्य", "xyznonexistent999"],
        "include_extracts": False,
        "include_neighbors": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    # xyznonexistent999 must be in unresolved
    assert "xyznonexistent999" in data["unresolved_tokens"]
    # द्रव्य resolved — not in unresolved
    assert "द्रव्य" not in data["unresolved_tokens"]


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_neo4j", [([], [], [])], indirect=True)
async def test_empty_traversal_returns_empty_ranked(client_with_neo4j: AsyncClient) -> None:
    """When traversal returns no hits, ranked_topics is empty but response is valid."""
    import uuid
    from sqlalchemy import text

    factory = client_with_neo4j.state  # type: ignore[attr-defined]
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, sources, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, ARRAY[]::text[], '[]'::jsonb)"
            ),
            {"id": str(uuid.uuid4()), "nk": "आत्मा", "dt": "आत्मा"},
        )
        await session.commit()

    resp = await client_with_neo4j.post(URL, json={
        "tokens": ["आत्मा"],
        "include_extracts": False,
        "include_neighbors": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ranked_topics"] == []
    assert "tool_trace_id" in data
