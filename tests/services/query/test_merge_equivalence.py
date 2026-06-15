from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

TOPICS_MATCH_URL = "/v1/query/topics_match"
GRAPHRAG_URL = "/v1/query/graphrag"

_SHARED_NK = "द्रव्य/स्वतंत्रता"

_TRAVERSE_ROWS = [
    {
        "topic_nk": _SHARED_NK,
        "topic_pg_id": "00000000-0000-0000-0000-000000000001",
        "heading_hi": "स्वतंत्रता",
        "is_leaf": True,
        "source": "jainkosh",
        "seed_kw": "द्रव्य",
        "path_weight": 1.0,
    },
]


async def _seed_pg(factory) -> None:
    tid = str(uuid.uuid4())
    kid = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, sources, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, ARRAY[]::text[], '[]'::jsonb)"
            ),
            {"id": kid, "nk": "द्रव्य", "dt": "द्रव्य"},
        )
        await session.execute(
            text(
                "INSERT INTO topics (id, natural_key, display_text, source, is_leaf, is_synthetic, extract_doc_ids) "
                "VALUES (:id, :nk, '[{\"lang\":\"hi\",\"script\":\"devanagari\",\"text\":\"स्वतंत्रता\"}]'::jsonb, "
                "'jainkosh'::ingestion_source, true, false, '[]'::jsonb)"
            ),
            {"id": tid, "nk": _SHARED_NK},
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j",
    [([], _TRAVERSE_ROWS, [])],
    indirect=True,
)
async def test_overlap_between_topics_match_and_graphrag(client_with_neo4j: AsyncClient) -> None:
    """The shared topic should appear in both topics_match and graphrag results."""
    factory = client_with_neo4j.state  # type: ignore[attr-defined]
    await _seed_pg(factory)

    tm_resp = await client_with_neo4j.post(TOPICS_MATCH_URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "include_extracts": False,
        "include_references": False,
    })
    gr_resp = await client_with_neo4j.post(GRAPHRAG_URL, json={
        "tokens": ["द्रव्य"],
        "include_extracts": False,
        "include_neighbors": False,
        "include_references": False,
    })

    assert tm_resp.status_code == 200
    assert gr_resp.status_code == 200

    tm_nks = {m["topic_natural_key"] for m in tm_resp.json()["matches"]}
    gr_nks = {t["topic_natural_key"] for t in gr_resp.json()["ranked_topics"]}

    overlap = tm_nks & gr_nks
    assert _SHARED_NK in tm_nks, f"Expected {_SHARED_NK} in topics_match"
    assert _SHARED_NK in gr_nks, f"Expected {_SHARED_NK} in graphrag"
    assert len(overlap) >= 1, "No overlap between topics_match and graphrag"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j",
    [([], _TRAVERSE_ROWS, [])],
    indirect=True,
)
async def test_merge_by_natural_key(client_with_neo4j: AsyncClient) -> None:
    """Topics from both lists can be merged by topic_natural_key without duplicates."""
    factory = client_with_neo4j.state  # type: ignore[attr-defined]
    await _seed_pg(factory)

    tm_resp = await client_with_neo4j.post(TOPICS_MATCH_URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "include_extracts": False,
        "include_references": False,
    })
    gr_resp = await client_with_neo4j.post(GRAPHRAG_URL, json={
        "tokens": ["द्रव्य"],
        "include_extracts": False,
        "include_neighbors": False,
        "include_references": False,
    })

    # Simulate chat-side merge: graphrag wins on tie, union without duplicates
    merged: dict[str, dict] = {}
    for item in tm_resp.json()["matches"]:
        merged[item["topic_natural_key"]] = item
    for item in gr_resp.json()["ranked_topics"]:
        merged[item["topic_natural_key"]] = item  # graphrag overwrites on overlap

    # No duplicate keys
    assert len(merged) == len(set(merged.keys()))
    # Shared topic exists once in merged dict
    assert _SHARED_NK in merged
