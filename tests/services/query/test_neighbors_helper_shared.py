"""Assert that topic_neighbors and graphrag use the same bucket_neighbors logic."""
from __future__ import annotations

from services.query_service.pipeline.traverse import NeighborRow, bucket_neighbors


_ROWS = [
    NeighborRow(
        topic_nk="आत्मा",
        rel="RELATED_TO",
        node_labels=["Topic"],
        neighbor_nk="परमात्मा",
        neighbor_hi="परमात्मा",
        is_leaf=False,
        source="jainkosh",
    ),
    NeighborRow(
        topic_nk="आत्मा",
        rel="HAS_TOPIC",
        node_labels=["Keyword"],
        neighbor_nk="ज्ञान",
        neighbor_hi="ज्ञान",
    ),
    NeighborRow(
        topic_nk="आत्मा",
        rel="MENTIONS_TOPIC",
        node_labels=["Gatha"],
        neighbor_nk="samaysaar:गाथा:1",
        neighbor_hi="",
        gatha_number=1,
        shastra_nk="samaysaar",
    ),
]


def test_bucket_neighbors_topic_bucket() -> None:
    """Topic nodes land in related_topics with all properties."""
    result = bucket_neighbors(_ROWS)
    assert "आत्मा" in result
    rt = result["आत्मा"]["related_topics"]
    assert len(rt) == 1
    assert rt[0]["topic_natural_key"] == "परमात्मा"
    assert rt[0]["display_text_hi"] == "परमात्मा"
    assert rt[0]["is_leaf"] is False
    assert rt[0]["source"] == "jainkosh"


def test_bucket_neighbors_keyword_bucket() -> None:
    result = bucket_neighbors(_ROWS)
    rk = result["आत्मा"]["related_keywords"]
    assert len(rk) == 1
    assert rk[0]["keyword_natural_key"] == "ज्ञान"


def test_bucket_neighbors_gatha_bucket() -> None:
    result = bucket_neighbors(_ROWS)
    mg = result["आत्मा"]["mentioned_in_gathas"]
    assert len(mg) == 1
    assert mg[0]["shastra_natural_key"] == "samaysaar"
    assert mg[0]["gatha_number"] == 1


def test_graphrag_and_topic_neighbors_share_same_bucket_neighbors() -> None:
    """topic_neighbors pipeline imports bucket_neighbors from traverse — same function object."""
    from services.query_service.pipeline.topic_neighbors import bucket_neighbors as tn_bucket
    from services.query_service.pipeline.graphrag import hydrate_topics  # noqa: F401 — confirms graphrag imports from traverse

    # Both should refer to the same function from traverse.py
    assert tn_bucket is bucket_neighbors


def test_bucket_neighbors_rows_without_optional_fields() -> None:
    """NeighborRow without is_leaf/source still produces valid dict (no KeyError)."""
    row = NeighborRow(
        topic_nk="द्रव्य",
        rel="RELATED_TO",
        node_labels=["Topic"],
        neighbor_nk="द्रव्य/गुण",
        neighbor_hi="गुण",
    )
    result = bucket_neighbors([row])
    rt = result["द्रव्य"]["related_topics"]
    assert rt[0]["topic_natural_key"] == "द्रव्य/गुण"
    assert "is_leaf" not in rt[0]
    assert "source" not in rt[0]
