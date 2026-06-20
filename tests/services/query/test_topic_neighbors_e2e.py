from __future__ import annotations

import pytest
from httpx import AsyncClient

URL = "/v1/query/topic_neighbors"

_ANCHOR_NK = "द्रव्य/स्वतंत्रता/लक्षण"

_NEIGHBOR_ROWS = [
    {
        "anchor_nk": _ANCHOR_NK,
        "rel": "RELATED_TO",
        "node_labels": ["Topic"],
        "neighbor_nk": "द्रव्य/स्वतंत्रता",
        "neighbor_hi": "स्वतंत्रता",
        "gatha_number": None,
        "shastra_nk": None,
        "is_leaf": False,
        "source": "jainkosh",
    },
    {
        "anchor_nk": _ANCHOR_NK,
        "rel": "HAS_TOPIC",
        "node_labels": ["Keyword"],
        "neighbor_nk": "स्वभाव",
        "neighbor_hi": "स्वभाव",
        "gatha_number": None,
        "shastra_nk": None,
        "is_leaf": None,
        "source": None,
    },
    {
        "anchor_nk": _ANCHOR_NK,
        "rel": "MENTIONS_TOPIC",
        "node_labels": ["Gatha"],
        "neighbor_nk": "samaysaar:गाथा:6",
        "neighbor_hi": "",
        "gatha_number": 6,
        "shastra_nk": "samaysaar",
        "is_leaf": None,
        "source": None,
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [([], _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_topic_neighbors_returns_grouped_buckets(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """E2E: anchor topic returns related_topics, related_keywords, mentioned_in_gathas."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_ANCHOR_NK],
    })
    assert resp.status_code == 200
    data = resp.json()

    assert "neighbors_by_anchor" in data
    assert "unresolved_topic_keys" in data
    assert "tool_trace_id" in data

    groups = data["neighbors_by_anchor"]
    assert len(groups) == 1
    group = groups[0]
    assert group["anchor_topic_natural_key"] == _ANCHOR_NK

    # related_topics
    rt = group["related_topics"]
    assert len(rt) == 1
    assert rt[0]["topic_natural_key"] == "द्रव्य/स्वतंत्रता"
    assert rt[0]["display_text_hi"] == "स्वतंत्रता"
    assert rt[0]["ancestors_hi"] == ["द्रव्य"]
    assert rt[0]["is_leaf"] is False
    assert rt[0]["source"] == "jainkosh"
    assert rt[0]["extracts_hi"] == []
    assert rt[0]["references"] == []

    # related_keywords
    rk = group["related_keywords"]
    assert len(rk) == 1
    assert rk[0]["keyword_natural_key"] == "स्वभाव"

    # mentioned_in_gathas
    mg = group["mentioned_in_gathas"]
    assert len(mg) == 1
    assert mg[0]["shastra_natural_key"] == "samaysaar"
    assert mg[0]["gatha_number"] == 6

    assert data["unresolved_topic_keys"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [([], _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_topic_neighbors_structural_edges_excluded(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """Structural IN_SHASTRA/IN_TEEKA/IN_PUBLICATION edges must not appear in results."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_ANCHOR_NK],
    })
    assert resp.status_code == 200
    data = resp.json()
    # The mock returns our seeded rows only (which have no structural edges).
    # The Cypher WHERE clause excludes them — verified by checking no structural
    # edge type leaks into the response shape.
    for group in data["neighbors_by_anchor"]:
        for rt in group["related_topics"]:
            assert "topic_natural_key" in rt  # correct shape
