from __future__ import annotations

import pytest
from httpx import AsyncClient

URL = "/v1/query/topic_neighbors"

_ANCHOR_NK = "द्रव्य/गुण"
_NEIGHBOR_TOPIC_NK = "द्रव्य/स्वतंत्रता"

_NEIGHBOR_ROWS = [
    {
        "anchor_nk": _ANCHOR_NK,
        "rel": "RELATED_TO",
        "node_labels": ["Topic"],
        "neighbor_nk": _NEIGHBOR_TOPIC_NK,
        "neighbor_hi": "स्वतंत्रता",
        "gatha_number": None,
        "shastra_nk": None,
        "is_leaf": True,
        "source": "jainkosh",
    },
]

_MONGO_DOCS = [
    {
        "natural_key": _NEIGHBOR_TOPIC_NK,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [(_MONGO_DOCS, _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_include_extracts_false_returns_empty_arrays(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """include_extracts=False (default) → extracts_hi is an empty list."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_ANCHOR_NK],
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    group = data["neighbors_by_anchor"][0]
    for t in group["related_topics"]:
        assert t["extracts_hi"] == []
        assert t["references"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [(_MONGO_DOCS, _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_include_extracts_true_populates_hindi_text(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """include_extracts=True → extracts_hi is populated with Hindi text blocks."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_ANCHOR_NK],
        "include_extracts": True,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    group = data["neighbors_by_anchor"][0]
    topic = next(
        (t for t in group["related_topics"] if t["topic_natural_key"] == _NEIGHBOR_TOPIC_NK),
        None,
    )
    assert topic is not None
    assert len(topic["extracts_hi"]) > 0
    assert "द्रव्य स्वतंत्र है" in topic["extracts_hi"][0]["text_hi"]
    assert topic["references"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [(_MONGO_DOCS, _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_include_references_true_populates_refs(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """include_references=True → references populated for neighbor topics."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_ANCHOR_NK],
        "include_extracts": False,
        "include_references": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    group = data["neighbors_by_anchor"][0]
    topic = next(
        (t for t in group["related_topics"] if t["topic_natural_key"] == _NEIGHBOR_TOPIC_NK),
        None,
    )
    assert topic is not None
    assert topic["extracts_hi"] == []
    refs = topic["references"]
    assert len(refs) > 0
    assert refs[0]["shastra_natural_key"] == "samaysaar"
    assert refs[0]["gatha_number"] == 6
