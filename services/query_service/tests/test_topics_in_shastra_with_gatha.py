from __future__ import annotations

import pytest
from httpx import AsyncClient

URL = "/v1/query/topics_in_shastra"

_TOPICS_ROWS = [
    {
        "topic_nk": "द्रव्य/स्वतंत्रता",
        "display_text_hi": "स्वतंत्रता",
        "is_leaf": True,
        "mention_count": 3,
    },
    {
        "topic_nk": "द्रव्य/लक्षण",
        "display_text_hi": "लक्षण",
        "is_leaf": True,
        "mention_count": 1,
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [(_TOPICS_ROWS, [])],
    indirect=True,
)
async def test_topics_in_gatha_returns_sorted_topics(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """Per-gatha: topics sorted by mention_count DESC, shape correct."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "shastra_natural_key": "samaysaar",
        "gatha_number": 6,
        "limit": 25,
    })
    assert resp.status_code == 200
    data = resp.json()

    assert "topics" in data
    assert "tool_trace_id" in data

    topics = data["topics"]
    assert len(topics) == 2

    # First topic must have the highest mention_count
    assert topics[0]["topic_natural_key"] == "द्रव्य/स्वतंत्रता"
    assert topics[0]["mention_count"] == 3
    assert topics[0]["display_text_hi"] == "स्वतंत्रता"
    assert topics[0]["is_leaf"] is True
    assert topics[0]["ancestors_hi"] == ["द्रव्य"]

    assert topics[1]["topic_natural_key"] == "द्रव्य/लक्षण"
    assert topics[1]["mention_count"] == 1
    assert topics[1]["ancestors_hi"] == ["द्रव्य"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [(_TOPICS_ROWS, [])],
    indirect=True,
)
async def test_topics_in_gatha_mention_count_descending(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """Verify mention_count ordering is preserved (highest first)."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "shastra_natural_key": "samaysaar",
        "gatha_number": 6,
    })
    assert resp.status_code == 200
    counts = [t["mention_count"] for t in resp.json()["topics"]]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], [])],
    indirect=True,
)
async def test_topics_in_gatha_empty_result(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """No topics for a gatha → empty list, not an error."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "shastra_natural_key": "samaysaar",
        "gatha_number": 999,
    })
    assert resp.status_code == 200
    assert resp.json()["topics"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], [])],
    indirect=True,
)
async def test_topics_in_shastra_missing_required_field(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """Missing shastra_natural_key → 422."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={"gatha_number": 6})
    assert resp.status_code == 422
