from __future__ import annotations

import pytest
from httpx import AsyncClient

URL = "/v1/query/topic_neighbors"

_ANCHOR_NK = "आत्मा"

# 5 related topics to test cap at max_neighbors_per_topic=2
_NEIGHBOR_ROWS = [
    {
        "anchor_nk": _ANCHOR_NK,
        "rel": "RELATED_TO",
        "node_labels": ["Topic"],
        "neighbor_nk": f"आत्मा/topic-{i}",
        "neighbor_hi": f"विषय {i}",
        "gatha_number": None,
        "shastra_nk": None,
        "is_leaf": True,
        "source": "jainkosh",
    }
    for i in range(5)
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [([], _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_max_neighbors_per_topic_capped(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """max_neighbors_per_topic=2 should cap related_topics to 2 even when 5 are returned."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_ANCHOR_NK],
        "max_neighbors_per_topic": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    groups = data["neighbors_by_anchor"]
    assert len(groups) == 1
    related = groups[0]["related_topics"]
    assert len(related) <= 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [([], _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_default_cap_is_25(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """Default max_neighbors_per_topic=25: all 5 rows are returned (below cap)."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_ANCHOR_NK],
    })
    assert resp.status_code == 200
    data = resp.json()
    groups = data["neighbors_by_anchor"]
    assert len(groups) == 1
    related = groups[0]["related_topics"]
    assert len(related) == 5
