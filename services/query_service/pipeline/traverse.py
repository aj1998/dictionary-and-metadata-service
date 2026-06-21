from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STRUCTURAL_EDGE_TYPES = {"IN_SHASTRA", "IN_TEEKA", "IN_PUBLICATION"}

# Stage 4 traversal query — returns one row per (seed_keyword, topic, path).
# Grouping by topic happens in the ranker.
_TRAVERSE_QUERY_TEMPLATE = """
UNWIND $seed_kws AS seed
MATCH (k:Keyword {{natural_key: seed}})
MATCH p = (k)-[r*1..{max_hops}]-(t:Topic)
WHERE NOT any(rel IN relationships(p)
      WHERE type(rel) IN ['IN_SHASTRA','IN_TEEKA','IN_PUBLICATION'])
WITH t, k.natural_key AS seed_kw,
     [rel IN relationships(p) | type(rel)] AS rel_types,
     reduce(w = 0.0, rel IN relationships(p) | w + coalesce(rel.weight, 1.0)) AS path_weight
RETURN t.natural_key AS topic_nk,
       t.pg_id        AS topic_pg_id,
       t.display_text_hi AS heading_hi,
       t.is_leaf      AS is_leaf,
       t.source       AS source,
       seed_kw,
       path_weight
"""

_NEIGHBORS_QUERY = """
UNWIND $topic_nks AS nk
MATCH (t:Topic {natural_key: nk})-[r:RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC]-(n)
WHERE NOT type(r) IN ['IN_SHASTRA','IN_TEEKA','IN_PUBLICATION']
RETURN nk,
       type(r) AS rel,
       labels(n) AS node_labels,
       n.natural_key AS neighbor_nk,
       n.display_text_hi AS neighbor_hi,
       n.gatha_number AS gatha_number,
       n.shastra_natural_key AS shastra_nk
LIMIT 200
"""


@dataclass
class TraversalHit:
    topic_nk: str
    topic_pg_id: str
    heading_hi: str
    is_leaf: bool
    source: str
    seed_kw: str
    path_weight: float


@dataclass
class NeighborRow:
    topic_nk: str
    rel: str
    node_labels: list[str]
    neighbor_nk: str
    neighbor_hi: str
    gatha_number: object = None
    shastra_nk: object = None
    is_leaf: bool | None = None
    source: str | None = None
    extract_count: int | None = None


async def traverse_topics(
    driver: object,
    seed_kws: list[str],
    max_hops: int,
    edge_types: list[str] | None,
    database: str,
) -> list[TraversalHit]:
    """Stage 4: traverse from seed keywords to candidate topics via Neo4j."""
    if not seed_kws:
        return []

    query = _TRAVERSE_QUERY_TEMPLATE.format(max_hops=max_hops)
    if edge_types:
        rel_pattern = "|".join(edge_types)
        query = query.replace("[r*1..", f"[r:{rel_pattern}*1..")

    hits: list[TraversalHit] = []
    async with driver.session(database=database) as session:  # type: ignore[attr-defined]
        result = await session.run(query, seed_kws=seed_kws)
        rows = await result.data()
        for row in rows:
            hits.append(TraversalHit(
                topic_nk=row["topic_nk"],
                topic_pg_id=row.get("topic_pg_id") or "",
                heading_hi=row.get("heading_hi") or "",
                is_leaf=bool(row.get("is_leaf", True)),
                source=row.get("source") or "",
                seed_kw=row["seed_kw"],
                path_weight=float(row.get("path_weight") or 1.0),
            ))

    logger.debug("traverse: seed_kws=%s max_hops=%d → %d raw hits", seed_kws, max_hops, len(hits))
    return hits


async def fetch_neighbors(
    driver: object,
    topic_nks: list[str],
    database: str,
) -> list[NeighborRow]:
    """Fetch 1-hop RELATED_TO/MENTIONS_TOPIC/HAS_TOPIC neighbors for ranked topics."""
    if not topic_nks:
        return []
    neighbors: list[NeighborRow] = []
    async with driver.session(database=database) as session:  # type: ignore[attr-defined]
        result = await session.run(_NEIGHBORS_QUERY, topic_nks=topic_nks)
        rows = await result.data()
        for row in rows:
            neighbors.append(NeighborRow(
                topic_nk=row["nk"],
                rel=row["rel"],
                node_labels=list(row.get("node_labels") or []),
                neighbor_nk=row.get("neighbor_nk") or "",
                neighbor_hi=row.get("neighbor_hi") or "",
                gatha_number=row.get("gatha_number"),
                shastra_nk=row.get("shastra_nk"),
            ))
    return neighbors


def bucket_neighbors(rows: list[NeighborRow]) -> dict[str, dict]:
    """Group neighbor rows by topic_nk into the three neighbor buckets."""
    result: dict[str, dict] = {}
    for row in rows:
        bucket = result.setdefault(row.topic_nk, {
            "related_topics": [],
            "mentioned_in_gathas": [],
            "related_keywords": [],
        })
        labels = set(row.node_labels)
        if "Topic" in labels:
            entry: dict = {
                "topic_natural_key": row.neighbor_nk,
                "display_text_hi": row.neighbor_hi,
            }
            if row.is_leaf is not None:
                entry["is_leaf"] = row.is_leaf
            if row.source is not None:
                entry["source"] = row.source
            if row.extract_count is not None:
                entry["extract_count"] = row.extract_count
            bucket["related_topics"].append(entry)
        elif "Keyword" in labels:
            bucket["related_keywords"].append({"keyword_natural_key": row.neighbor_nk})
        elif "Gatha" in labels:
            try:
                gn = int(row.gatha_number) if row.gatha_number is not None else None
            except (ValueError, TypeError):
                gn = None
            bucket["mentioned_in_gathas"].append({
                "shastra_natural_key": row.shastra_nk or "",
                "gatha_number": gn,
            })
    return result
