from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/graphrag"

_TOPIC_NK = "द्रव्य/स्वतंत्रता"

_TRAVERSE_ROWS = [
    {
        "topic_nk": _TOPIC_NK,
        "topic_pg_id": "00000000-0000-0000-0000-000000000001",
        "heading_hi": "स्वतंत्रता",
        "is_leaf": True,
        "source": "jainkosh",
        "seed_kw": "द्रव्य",
        "path_weight": 1.0,
    },
    {
        "topic_nk": _TOPIC_NK,
        "topic_pg_id": "00000000-0000-0000-0000-000000000001",
        "heading_hi": "स्वतंत्रता",
        "is_leaf": True,
        "source": "jainkosh",
        "seed_kw": "स्वतंत्रता",
        "path_weight": 1.5,
    },
]

_NEIGHBOR_ROWS = [
    {
        "nk": _TOPIC_NK,
        "rel": "RELATED_TO",
        "node_labels": ["Topic"],
        "neighbor_nk": "द्रव्य/लक्षण",
        "neighbor_hi": "लक्षण",
        "gatha_number": None,
        "shastra_nk": None,
    },
    {
        "nk": _TOPIC_NK,
        "rel": "MENTIONS_TOPIC",
        "node_labels": ["Keyword"],
        "neighbor_nk": "स्वभाव",
        "neighbor_hi": "स्वभाव",
        "gatha_number": None,
        "shastra_nk": None,
    },
]

_MONGO_DOCS = [
    {
        "natural_key": _TOPIC_NK,
        "blocks": [
            {
                "kind": "hindi_text",
                "text_devanagari": "द्रव्य स्वतंत्र है।",
                "references": [
                    {
                        "text": "samaysaar 6",
                        "resolved_fields": [
                            {"field": "shastra", "value": "samaysaar"},
                            {"field": "gatha_number", "value": 6},
                        ],
                        "shastra_name": "samaysaar",
                        "teeka_name": "",
                    }
                ],
            }
        ],
    }
]


async def _insert_keyword(factory, natural_key: str) -> None:
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, sources, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, ARRAY[]::text[], '[]'::jsonb)"
            ),
            {"id": str(uuid.uuid4()), "nk": natural_key, "dt": natural_key},
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j",
    [(_MONGO_DOCS, _TRAVERSE_ROWS, _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_graphrag_returns_ranked_topics(client_with_neo4j: AsyncClient) -> None:
    """E2E: given seed keywords, graphrag returns ranked topics with correct structure."""
    factory = client_with_neo4j.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "द्रव्य")
    await _insert_keyword(factory, "स्वतंत्रता")

    resp = await client_with_neo4j.post(URL, json={
        "tokens": ["द्रव्य", "स्वतंत्रता"],
        "max_hops": 2,
        "limit": 5,
        "include_extracts": True,
        "include_neighbors": True,
        "include_references": True,
    })
    assert resp.status_code == 200
    data = resp.json()

    assert "ranked_topics" in data
    assert "unresolved_tokens" in data
    assert "tool_trace_id" in data

    ranked = data["ranked_topics"]
    assert len(ranked) >= 1

    topic = next((t for t in ranked if t["topic_natural_key"] == _TOPIC_NK), None)
    assert topic is not None, f"Expected {_TOPIC_NK} in ranked_topics"

    assert topic["is_leaf"] is True
    assert topic["source"] == "jainkosh"
    assert topic["overlap_count"] == 2
    assert sorted(topic["matched_seed_keywords"]) == ["द्रव्य", "स्वतंत्रता"]
    assert topic["ancestors_hi"] == ["द्रव्य"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j",
    [(_MONGO_DOCS, _TRAVERSE_ROWS, _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_graphrag_neighbors_buckets(client_with_neo4j: AsyncClient) -> None:
    """Neighbors should be bucketed into related_topics and related_keywords."""
    factory = client_with_neo4j.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "द्रव्य")

    resp = await client_with_neo4j.post(URL, json={
        "tokens": ["द्रव्य"],
        "include_extracts": False,
        "include_neighbors": True,
        "include_references": False,
    })
    assert resp.status_code == 200
    ranked = resp.json()["ranked_topics"]
    topic = next((t for t in ranked if t["topic_natural_key"] == _TOPIC_NK), None)
    assert topic is not None
    nb = topic["neighbors"]
    assert nb is not None
    nks_related = [t["topic_natural_key"] for t in nb["related_topics"]]
    assert "द्रव्य/लक्षण" in nks_related
    kw_nks = [k["keyword_natural_key"] for k in nb["related_keywords"]]
    assert "स्वभाव" in kw_nks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j",
    [(_MONGO_DOCS, _TRAVERSE_ROWS, _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_graphrag_extracts_and_references(client_with_neo4j: AsyncClient) -> None:
    """Extracts should be Hindi-only; references should be extracted from blocks."""
    factory = client_with_neo4j.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, "द्रव्य")

    resp = await client_with_neo4j.post(URL, json={
        "tokens": ["द्रव्य"],
        "include_extracts": True,
        "include_neighbors": False,
        "include_references": True,
    })
    assert resp.status_code == 200
    ranked = resp.json()["ranked_topics"]
    topic = next((t for t in ranked if t["topic_natural_key"] == _TOPIC_NK), None)
    assert topic is not None

    extracts = topic["extracts_hi"]
    assert extracts is not None and len(extracts) > 0
    assert "द्रव्य स्वतंत्र है" in extracts[0]["text_hi"]

    refs = topic["references"]
    assert refs is not None and len(refs) > 0
    ref = refs[0]
    assert ref["shastra_natural_key"] == "samaysaar"
    assert ref["gatha_number"] == 6
