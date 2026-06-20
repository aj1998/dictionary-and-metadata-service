from __future__ import annotations

import logging
import unicodedata

from jain_kb_common.hydration.topic_extracts import hydrate_topic_extracts_hi

from .topics_match import ancestors_from_natural_key
from .traverse import NeighborRow, bucket_neighbors

logger = logging.getLogger(__name__)

# Identical traversal to graphrag include_neighbors, keyed on caller-supplied anchors.
# Returns anchor_nk per row so we can group by anchor in Python.
_TOPIC_NEIGHBORS_QUERY = """
UNWIND $topic_nks AS nk
MATCH (t:Topic {natural_key: nk})-[r:RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC]-(n)
WHERE NOT type(r) IN ['IN_SHASTRA','IN_TEEKA','IN_PUBLICATION']
RETURN nk AS anchor_nk, type(r) AS rel, labels(n) AS node_labels,
       n.natural_key AS neighbor_nk, n.display_text_hi AS neighbor_hi,
       n.gatha_number AS gatha_number, n.shastra_natural_key AS shastra_nk,
       n.is_leaf AS is_leaf, n.source AS source
LIMIT $hard_cap
"""


async def fetch_anchor_neighbors(
    driver: object,
    anchors: list[str],
    max_per: int,
    edge_types: list[str] | None,
    database: str,
) -> list[NeighborRow]:
    """Run the topic-neighbors Cypher and return rows with topic_nk = anchor_nk."""
    hard_cap = len(anchors) * max_per * 3
    query = _TOPIC_NEIGHBORS_QUERY
    if edge_types:
        rel_pattern = "|".join(edge_types)
        query = query.replace(
            "r:RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC",
            f"r:{rel_pattern}",
        )

    rows: list[NeighborRow] = []
    async with driver.session(database=database) as session:  # type: ignore[attr-defined]
        result = await session.run(query, topic_nks=anchors, hard_cap=hard_cap)
        data = await result.data()
        for row in data:
            rows.append(NeighborRow(
                topic_nk=row["anchor_nk"],  # anchor is the "grouping key"
                rel=row["rel"],
                node_labels=list(row.get("node_labels") or []),
                neighbor_nk=row.get("neighbor_nk") or "",
                neighbor_hi=row.get("neighbor_hi") or "",
                gatha_number=row.get("gatha_number"),
                shastra_nk=row.get("shastra_nk"),
                is_leaf=row.get("is_leaf"),
                source=row.get("source"),
            ))
    return rows


def _apply_caps(bucketed: dict[str, dict], cap: int) -> None:
    for anchor_data in bucketed.values():
        for bucket in ("related_topics", "mentioned_in_gathas", "related_keywords"):
            anchor_data[bucket] = anchor_data[bucket][:cap]


def _enrich_related_topics(bucketed: dict[str, dict]) -> None:
    """Add ancestors_hi to each related_topic entry (computable from topic_natural_key)."""
    for anchor_data in bucketed.values():
        for t in anchor_data.get("related_topics", []):
            t.setdefault("ancestors_hi", ancestors_from_natural_key(t["topic_natural_key"]))


async def expand_neighbors(
    neo4j_driver: object,
    anchors: list[str],
    max_neighbors_per_topic: int,
    edge_types: list[str] | None,
    mongo_db: object,
    database: str,
    include_extracts: bool,
    include_references: bool,
) -> tuple[dict[str, dict], list[str]]:
    """
    Expand 1-hop neighbors for each anchor topic.

    Returns (bucketed_by_anchor, unresolved_anchor_keys).
    bucketed_by_anchor: {anchor_nk: {related_topics, mentioned_in_gathas, related_keywords}}
    """
    nfc_anchors = [unicodedata.normalize("NFC", a) for a in anchors]

    rows = await fetch_anchor_neighbors(
        neo4j_driver, nfc_anchors, max_neighbors_per_topic, edge_types, database
    )

    found_anchors = {row.topic_nk for row in rows}
    unresolved = [a for a in nfc_anchors if a not in found_anchors]

    # Reuse graphrag's bucket_neighbors — single source of truth for label→bucket routing
    bucketed = bucket_neighbors(rows)

    _enrich_related_topics(bucketed)
    _apply_caps(bucketed, max_neighbors_per_topic)

    # Hydrate neighbor topics when requested
    if (include_extracts or include_references) and bucketed:
        neighbor_topic_nks: list[str] = []
        for anchor_data in bucketed.values():
            for t in anchor_data.get("related_topics", []):
                nk = t["topic_natural_key"]
                if nk not in neighbor_topic_nks:
                    neighbor_topic_nks.append(nk)

        if neighbor_topic_nks:
            rich_map = await hydrate_topic_extracts_hi(mongo_db, neighbor_topic_nks)
            for anchor_data in bucketed.values():
                for t in anchor_data.get("related_topics", []):
                    nk = t["topic_natural_key"]
                    rich_blocks = rich_map.get(nk, [])
                    if include_extracts:
                        t["extracts_hi"] = [
                            {"block_index": b["block_index"], "text_hi": b["text_hi"]}
                            for b in rich_blocks
                        ]
                    else:
                        t.setdefault("extracts_hi", [])
                    if include_references:
                        seen: set[tuple] = set()
                        flat_refs: list[dict] = []
                        for b in rich_blocks:
                            for ref in b.get("references", []):
                                key = (
                                    ref.get("shastra_natural_key"),
                                    ref.get("gatha_number"),
                                    ref.get("teeka_natural_key"),
                                    ref.get("page_number"),
                                )
                                if key not in seen:
                                    seen.add(key)
                                    flat_refs.append(ref)
                        t["references"] = flat_refs
                    else:
                        t.setdefault("references", [])
        else:
            for anchor_data in bucketed.values():
                for t in anchor_data.get("related_topics", []):
                    t.setdefault("extracts_hi", [])
                    t.setdefault("references", [])
    else:
        for anchor_data in bucketed.values():
            for t in anchor_data.get("related_topics", []):
                t.setdefault("extracts_hi", [])
                t.setdefault("references", [])

    logger.info(
        "topic_neighbors anchors=%d found=%d unresolved=%d total_rows=%d",
        len(nfc_anchors), len(found_anchors), len(unresolved), len(rows),
    )
    for anchor_nk, anchor_data in bucketed.items():
        logger.debug(
            "topic_neighbors anchor=%s related_topics=%d mentioned_in_gathas=%d related_keywords=%d",
            anchor_nk,
            len(anchor_data.get("related_topics", [])),
            len(anchor_data.get("mentioned_in_gathas", [])),
            len(anchor_data.get("related_keywords", [])),
        )

    return bucketed, unresolved
