"""Unit tests for the content-gated multi-hop BFS in topic_neighbors.

See docs/design/query_engine/08_content_gated_topic_neighbors.md Part B.

The fake Neo4j driver dispatches by the frontier node carried in the ``pairs``
UNWIND payload, so each BFS round returns the true neighbors of its frontier —
which a single static row list (the HTTP fixture) cannot express.
"""
from __future__ import annotations

import pytest

from services.query_service.pipeline.topic_neighbors import expand_neighbors

# Graph (RELATED_TO, undirected):
#   A(content) ── B(container, 0) ── C(content, 2) ── D(content, 1)
#   A ── K (keyword)
# B is a content-less passthrough: reaching C through B must NOT cost a hop.
_EDGES: dict[str, list[dict]] = {
    "A": [
        {"node_labels": ["Topic"], "neighbor_nk": "B", "neighbor_hi": "B",
         "extract_count": 0, "is_leaf": False, "source": "jainkosh"},
        {"node_labels": ["Keyword"], "neighbor_nk": "K", "neighbor_hi": "K",
         "extract_count": None, "is_leaf": None, "source": None},
    ],
    "B": [
        {"node_labels": ["Topic"], "neighbor_nk": "C", "neighbor_hi": "C",
         "extract_count": 2, "is_leaf": True, "source": "jainkosh"},
        {"node_labels": ["Topic"], "neighbor_nk": "A", "neighbor_hi": "A",
         "extract_count": 5, "is_leaf": True, "source": "jainkosh"},  # back-edge
    ],
    "C": [
        {"node_labels": ["Topic"], "neighbor_nk": "D", "neighbor_hi": "D",
         "extract_count": 1, "is_leaf": True, "source": "jainkosh"},
        {"node_labels": ["Topic"], "neighbor_nk": "B", "neighbor_hi": "B",
         "extract_count": 0, "is_leaf": False, "source": "jainkosh"},  # back-edge
    ],
    "D": [
        {"node_labels": ["Topic"], "neighbor_nk": "C", "neighbor_hi": "C",
         "extract_count": 2, "is_leaf": True, "source": "jainkosh"},  # back-edge
    ],
}


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def data(self) -> list[dict]:
        return self._rows


class _FakeSession:
    async def run(self, cypher: str, **kwargs: object) -> _FakeResult:
        pairs = kwargs.get("pairs", [])
        rows: list[dict] = []
        for pair in pairs:  # type: ignore[assignment]
            origin = pair["origin"]
            node = pair["node"]
            for nb in _EDGES.get(node, []):
                rows.append({"anchor_nk": origin, "rel": "RELATED_TO",
                             "gatha_number": None, "shastra_nk": None, **nb})
        return _FakeResult(rows)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakeDriver:
    def session(self, database: str | None = None) -> _FakeSession:
        return _FakeSession()


def _related(bucketed: dict, anchor: str) -> dict[str, int]:
    return {t["topic_natural_key"]: t["hops"] for t in bucketed[anchor]["related_topics"]}


@pytest.mark.asyncio
async def test_passthrough_does_not_consume_hop() -> None:
    """max_hops=1: C (behind content-less B) is reached at hops=1; D excluded."""
    bucketed, unresolved = await expand_neighbors(
        _FakeDriver(), ["A"], max_neighbors_per_topic=25, edge_types=None,
        mongo_db=None, database="db", include_extracts=False,
        include_references=False, max_hops=1,
    )
    rel = _related(bucketed, "A")
    assert rel == {"C": 1}          # B (passthrough) not emitted; D out of depth
    assert unresolved == []
    # keyword K collected, never expanded / counted
    assert bucketed["A"]["related_keywords"] == [{"keyword_natural_key": "K"}]


@pytest.mark.asyncio
async def test_two_content_hops() -> None:
    """max_hops=2: C at hops=1, D at hops=2."""
    bucketed, _ = await expand_neighbors(
        _FakeDriver(), ["A"], max_neighbors_per_topic=25, edge_types=None,
        mongo_db=None, database="db", include_extracts=False,
        include_references=False, max_hops=2,
    )
    assert _related(bucketed, "A") == {"C": 1, "D": 2}


@pytest.mark.asyncio
async def test_no_cycle_and_anchor_not_self_neighbor() -> None:
    """Back-edges (C→B, B→A, D→C) never loop nor collect the anchor itself."""
    bucketed, _ = await expand_neighbors(
        _FakeDriver(), ["A"], max_neighbors_per_topic=25, edge_types=None,
        mongo_db=None, database="db", include_extracts=False,
        include_references=False, max_hops=5,
    )
    rel = _related(bucketed, "A")
    assert "A" not in rel
    assert rel == {"C": 1, "D": 2}
