from __future__ import annotations

import pytest
from httpx import AsyncClient

URL = "/v1/query/topic_neighbors"

_KNOWN_NK = "द्रव्य/स्वतंत्रता"
_UNKNOWN_NK = "द्रव्य/xyznonexistent"

_NEIGHBOR_ROWS = [
    {
        "anchor_nk": _KNOWN_NK,
        "rel": "RELATED_TO",
        "node_labels": ["Topic"],
        "neighbor_nk": "द्रव्य/लक्षण",
        "neighbor_hi": "लक्षण",
        "gatha_number": None,
        "shastra_nk": None,
        "is_leaf": True,
        "source": "jainkosh",
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [([], _NEIGHBOR_ROWS)],
    indirect=True,
)
async def test_unknown_anchor_goes_to_unresolved(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """Unknown anchors land in unresolved_topic_keys; known anchors still expand."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [_KNOWN_NK, _UNKNOWN_NK],
    })
    assert resp.status_code == 200
    data = resp.json()

    assert _UNKNOWN_NK in data["unresolved_topic_keys"]
    assert _KNOWN_NK not in data["unresolved_topic_keys"]

    groups = data["neighbors_by_anchor"]
    anchor_keys = [g["anchor_topic_natural_key"] for g in groups]
    assert _KNOWN_NK in anchor_keys
    assert _UNKNOWN_NK not in anchor_keys


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [([], [])],
    indirect=True,
)
async def test_all_anchors_unknown_returns_empty_groups(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """When all anchors are unknown, neighbors_by_anchor is empty, no crash."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": ["xyzunknown1", "xyzunknown2"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighbors_by_anchor"] == []
    assert set(data["unresolved_topic_keys"]) == {"xyzunknown1", "xyzunknown2"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_topic_neighbors",
    [([], [])],
    indirect=True,
)
async def test_empty_topic_natural_keys_returns_400(
    client_with_neo4j_topic_neighbors: AsyncClient,
) -> None:
    """Empty topic_natural_keys list must return HTTP 400."""
    resp = await client_with_neo4j_topic_neighbors.post(URL, json={
        "topic_natural_keys": [],
    })
    assert resp.status_code == 400
