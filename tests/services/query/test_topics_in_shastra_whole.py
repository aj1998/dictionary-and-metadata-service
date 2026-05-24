from __future__ import annotations

import pytest
from httpx import AsyncClient

URL = "/v1/query/topics_in_shastra"

# Whole-shastra rollup: 3 distinct topics across all gathas
_SHASTRA_TOPICS_ROWS = [
    {
        "topic_nk": "द्रव्य",
        "display_text_hi": "द्रव्य",
        "is_leaf": False,
        "mention_count": 10,
    },
    {
        "topic_nk": "द्रव्य/स्वतंत्रता",
        "display_text_hi": "स्वतंत्रता",
        "is_leaf": True,
        "mention_count": 7,
    },
    {
        "topic_nk": "गुण/परिणाम",
        "display_text_hi": "परिणाम",
        "is_leaf": True,
        "mention_count": 2,
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [(_SHASTRA_TOPICS_ROWS, [])],
    indirect=True,
)
async def test_whole_shastra_rollup(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """No gatha_number → whole-shastra rollup; all topics returned."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "shastra_natural_key": "samaysaar",
    })
    assert resp.status_code == 200
    data = resp.json()

    topics = data["topics"]
    assert len(topics) == 3
    assert topics[0]["topic_natural_key"] == "द्रव्य"
    assert topics[0]["mention_count"] == 10
    assert topics[0]["ancestors_hi"] == []  # root topic, no ancestors


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [(_SHASTRA_TOPICS_ROWS, [])],
    indirect=True,
)
async def test_whole_shastra_sorted_desc(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """Mention counts must be non-increasing."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "shastra_natural_key": "samaysaar",
        "limit": 25,
    })
    assert resp.status_code == 200
    counts = [t["mention_count"] for t in resp.json()["topics"]]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [(_SHASTRA_TOPICS_ROWS, [])],
    indirect=True,
)
async def test_whole_shastra_limit_respected(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """Mock returns 3 rows; a limit=2 request still returns all 3 (cap applied in Neo4j)."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "shastra_natural_key": "samaysaar",
        "limit": 2,
    })
    assert resp.status_code == 200
    # The mock returns preset rows regardless of limit; just verify no crash
    assert isinstance(resp.json()["topics"], list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [(_SHASTRA_TOPICS_ROWS, [])],
    indirect=True,
)
async def test_ancestors_hi_computed_from_natural_key(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """ancestors_hi is derived from slashes in natural_key, not from Neo4j data."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "shastra_natural_key": "samaysaar",
    })
    assert resp.status_code == 200
    topics = resp.json()["topics"]

    # द्रव्य/स्वतंत्रता → ancestors = ["द्रव्य"]
    t = next(t for t in topics if t["topic_natural_key"] == "द्रव्य/स्वतंत्रता")
    assert t["ancestors_hi"] == ["द्रव्य"]

    # गुण/परिणाम → ancestors = ["गुण"]
    t2 = next(t for t in topics if t["topic_natural_key"] == "गुण/परिणाम")
    assert t2["ancestors_hi"] == ["गुण"]
