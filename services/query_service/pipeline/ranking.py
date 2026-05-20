from __future__ import annotations

from dataclasses import dataclass, field

from .traverse import TraversalHit

LEAF_FACTOR = 1.0
CONTAINER_FACTOR = 0.5  # matches 12_query_engine.md Stage 5
OVERLAP_WEIGHT = 10.0
MAX_WEIGHT_SUM = 5.0


@dataclass
class RankedTopic:
    topic_nk: str
    topic_pg_id: str
    heading_hi: str
    is_leaf: bool
    source: str
    score: float
    overlap_count: int
    matched_seed_keywords: list[str]
    weight_sum: float = 0.0
    ancestors_hi: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        parts = self.topic_nk.split("/")
        self.ancestors_hi = parts[:-1]


def rank(hits: list[TraversalHit], seed_kws: list[str]) -> list[RankedTopic]:
    """Stage 5: collapse multi-path hits per topic, score, and sort."""
    by_topic: dict[str, list[TraversalHit]] = {}
    for h in hits:
        by_topic.setdefault(h.topic_nk, []).append(h)

    ranked: list[RankedTopic] = []
    for topic_nk, paths in by_topic.items():
        seeds_reached: set[str] = set()
        weight_sum = 0.0
        for p in paths:
            seeds_reached.add(p.seed_kw)
            weight_sum += p.path_weight

        overlap = len(seeds_reached)
        is_leaf = paths[0].is_leaf
        leaf_factor = LEAF_FACTOR if is_leaf else CONTAINER_FACTOR
        score = (overlap * OVERLAP_WEIGHT + min(weight_sum, MAX_WEIGHT_SUM)) * leaf_factor

        ranked.append(RankedTopic(
            topic_nk=topic_nk,
            topic_pg_id=paths[0].topic_pg_id,
            heading_hi=paths[0].heading_hi,
            is_leaf=is_leaf,
            source=paths[0].source,
            score=score,
            overlap_count=overlap,
            matched_seed_keywords=sorted(seeds_reached),
            weight_sum=weight_sum,
        ))

    # v2 swap point: replace with PageRank or graph+vector hybrid here.
    # v1: dominate by overlap, tiebreak by weight_sum, then stable alphabetical.
    ranked.sort(key=lambda r: (-r.score, -r.overlap_count, -r.weight_sum, r.topic_nk))
    return ranked
