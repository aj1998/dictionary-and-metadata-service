from __future__ import annotations

import logging
import unicodedata

from jain_kb_common.hydration.topic_extracts import (
    count_displayable_extract_blocks,
    hydrate_topic_extracts_hi,
)

from .topics_match import ancestors_from_natural_key
from .traverse import NeighborRow, bucket_neighbors

logger = logging.getLogger(__name__)

# One BFS hop from a set of (origin_anchor, frontier_node) pairs. The origin
# anchor is carried through the UNWIND payload so neighbors stay grouped by their
# originating anchor across multiple rounds. ``displayable_extract_count`` (the
# denormalized node prop from query_engine/08 Part D) is returned so depth can be
# content-gated without a Mongo round-trip; a null falls back to a Mongo check.
_TOPIC_NEIGHBORS_QUERY = """
UNWIND $pairs AS pair
MATCH (t:Topic {natural_key: pair.node})-[r:RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC]-(n)
WHERE NOT type(r) IN ['IN_SHASTRA','IN_TEEKA','IN_PUBLICATION']
RETURN pair.origin AS anchor_nk, type(r) AS rel, labels(n) AS node_labels,
       n.natural_key AS neighbor_nk, n.display_text_hi AS neighbor_hi,
       n.gatha_number AS gatha_number, n.shastra_natural_key AS shastra_nk,
       n.is_leaf AS is_leaf, n.source AS source,
       n.displayable_extract_count AS extract_count
LIMIT $hard_cap
"""


async def fetch_frontier_neighbors(
    driver: object,
    pairs: list[dict],
    max_per: int,
    edge_types: list[str] | None,
    database: str,
) -> list[NeighborRow]:
    """Run one BFS hop. ``pairs`` = [{origin, node}]; rows are keyed by origin."""
    hard_cap = max(len(pairs), 1) * max_per * 3
    query = _TOPIC_NEIGHBORS_QUERY
    if edge_types:
        rel_pattern = "|".join(edge_types)
        query = query.replace(
            "r:RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC",
            f"r:{rel_pattern}",
        )

    rows: list[NeighborRow] = []
    async with driver.session(database=database) as session:  # type: ignore[attr-defined]
        result = await session.run(query, pairs=pairs, hard_cap=hard_cap)
        data = await result.data()
        for row in data:
            rows.append(NeighborRow(
                topic_nk=row["anchor_nk"],  # origin anchor is the grouping key
                rel=row["rel"],
                node_labels=list(row.get("node_labels") or []),
                neighbor_nk=row.get("neighbor_nk") or "",
                neighbor_hi=row.get("neighbor_hi") or "",
                gatha_number=row.get("gatha_number"),
                shastra_nk=row.get("shastra_nk"),
                is_leaf=row.get("is_leaf"),
                source=row.get("source"),
                extract_count=row.get("extract_count"),
            ))
    return rows


def _apply_caps(bucketed: dict[str, dict], cap: int) -> None:
    for anchor_data in bucketed.values():
        # Sort related topics by content depth (closest first), preserving graph
        # order within a hop, before capping per bucket.
        anchor_data["related_topics"].sort(key=lambda t: t.get("hops", 1))
        for bucket in ("related_topics", "mentioned_in_gathas", "related_keywords"):
            anchor_data[bucket] = anchor_data[bucket][:cap]


def _enrich_related_topics(bucketed: dict[str, dict]) -> None:
    """Add ancestors_hi to each related_topic entry (computable from topic_natural_key)."""
    for anchor_data in bucketed.values():
        for t in anchor_data.get("related_topics", []):
            t.setdefault("ancestors_hi", ancestors_from_natural_key(t["topic_natural_key"]))


async def _content_gated_bfs(
    neo4j_driver: object,
    nfc_anchors: list[str],
    max_neighbors_per_topic: int,
    edge_types: list[str] | None,
    mongo_db: object,
    database: str,
    max_hops: int,
) -> tuple[dict[str, dict], set[str]]:
    """Content-gated BFS (query_engine/08 Part B).

    Walks RELATED_TO/MENTIONS_TOPIC/HAS_TOPIC edges from each anchor. Only
    arrivals at *hydrated* topics (displayable_extract_count > 0) are collected
    and advance the content-depth counter; content-less topics are free
    passthroughs that extend the frontier without consuming a hop. Keywords and
    gathas are terminal — collected, never expanded, never counted.

    Returns (bucketed_by_anchor, found_anchors).
    """
    visited: set[str] = set(nfc_anchors)
    collected: dict[str, list[dict]] = {a: [] for a in nfc_anchors}
    collected_nks: dict[str, set[str]] = {a: set() for a in nfc_anchors}
    kw_by_anchor: dict[str, list[dict]] = {a: [] for a in nfc_anchors}
    kw_seen: dict[str, set[str]] = {a: set() for a in nfc_anchors}
    gatha_by_anchor: dict[str, list[dict]] = {a: [] for a in nfc_anchors}
    gatha_seen: dict[str, set[tuple]] = {a: set() for a in nfc_anchors}
    frontier: dict[str, set[str]] = {a: {a} for a in nfc_anchors}
    found_anchors: set[str] = set()

    content_depth = 0
    rounds = 0
    safety = max_hops + 3  # absorb passthrough chains; logged when tripped

    while content_depth < max_hops and any(frontier.values()):
        if rounds >= safety:
            logger.warning(
                "topic_neighbors BFS safety bound tripped rounds=%d max_hops=%d",
                rounds, max_hops,
            )
            break
        rounds += 1

        pairs = [
            {"origin": origin, "node": node}
            for origin, nodes in frontier.items()
            for node in nodes
        ]
        rows = await fetch_frontier_neighbors(
            neo4j_driver, pairs, max_neighbors_per_topic, edge_types, database
        )
        for row in rows:
            found_anchors.add(row.topic_nk)
        bucketed_round = bucket_neighbors(rows)

        # Fallback Mongo content-check only for topics missing the node prop.
        need_mongo: list[str] = []
        for data in bucketed_round.values():
            for t in data.get("related_topics", []):
                if t.get("extract_count") is None and t["topic_natural_key"] not in visited:
                    need_mongo.append(t["topic_natural_key"])
        mongo_counts: dict[str, int] = {}
        if need_mongo:
            mongo_counts = await count_displayable_extract_blocks(
                mongo_db, list(set(need_mongo))
            )

        next_frontier: dict[str, set[str]] = {a: set() for a in nfc_anchors}
        produced_hydrated = False
        hydrated_count = 0
        passthrough_count = 0

        for anchor, data in bucketed_round.items():
            for t in data.get("related_topics", []):
                nk = t["topic_natural_key"]
                if nk in visited:
                    continue
                visited.add(nk)
                cnt = t.get("extract_count")
                if cnt is None:
                    cnt = mongo_counts.get(nk, 0)
                    t["extract_count"] = cnt
                if cnt and cnt > 0:
                    produced_hydrated = True
                    hydrated_count += 1
                    if nk not in collected_nks[anchor]:
                        collected_nks[anchor].add(nk)
                        entry = dict(t)
                        entry["hops"] = content_depth + 1
                        collected[anchor].append(entry)
                    next_frontier[anchor].add(nk)  # hydrated may expand further
                else:
                    passthrough_count += 1
                    next_frontier[anchor].add(nk)  # free passthrough
            for k in data.get("related_keywords", []):
                key = k["keyword_natural_key"]
                if key not in kw_seen[anchor]:
                    kw_seen[anchor].add(key)
                    kw_by_anchor[anchor].append(k)
            for g in data.get("mentioned_in_gathas", []):
                gkey = (g.get("shastra_natural_key"), g.get("gatha_number"))
                if gkey not in gatha_seen[anchor]:
                    gatha_seen[anchor].add(gkey)
                    gatha_by_anchor[anchor].append(g)

        # Only rounds that landed on a hydrated topic consume a content hop;
        # passthrough-only rounds just extend the frontier (free traversal).
        if produced_hydrated:
            content_depth += 1
        logger.info(
            "topic_neighbors BFS round=%d frontier_size=%d hydrated=%d passthrough=%d content_depth=%d",
            rounds, len(pairs), hydrated_count, passthrough_count, content_depth,
        )
        frontier = next_frontier

    # Only anchors that actually resolved to graph edges are emitted; anchors
    # with no neighbors fall through to unresolved_topic_keys (parity with 07).
    bucketed: dict[str, dict] = {
        a: {
            "related_topics": collected[a],
            "related_keywords": kw_by_anchor[a],
            "mentioned_in_gathas": gatha_by_anchor[a],
        }
        for a in nfc_anchors
        if a in found_anchors
    }
    return bucketed, found_anchors


async def expand_neighbors(
    neo4j_driver: object,
    anchors: list[str],
    max_neighbors_per_topic: int,
    edge_types: list[str] | None,
    mongo_db: object,
    database: str,
    include_extracts: bool,
    include_references: bool,
    max_hops: int = 1,
) -> tuple[dict[str, dict], list[str]]:
    """
    Expand content-gated multi-hop neighbors for each anchor topic.

    Returns (bucketed_by_anchor, unresolved_anchor_keys).
    bucketed_by_anchor: {anchor_nk: {related_topics, mentioned_in_gathas, related_keywords}}
    """
    nfc_anchors = [unicodedata.normalize("NFC", a) for a in anchors]

    bucketed, found_anchors = await _content_gated_bfs(
        neo4j_driver,
        nfc_anchors,
        max_neighbors_per_topic,
        edge_types,
        mongo_db,
        database,
        max(max_hops, 1),
    )

    unresolved = [a for a in nfc_anchors if a not in found_anchors]

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
                            {
                                "block_index": b["block_index"],
                                "text_hi": b["text_hi"],
                                "main_reference": b.get("main_reference"),
                            }
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

    total_related = sum(len(d.get("related_topics", [])) for d in bucketed.values())
    logger.info(
        "topic_neighbors anchors=%d found=%d unresolved=%d max_hops=%d total_related=%d",
        len(nfc_anchors), len(found_anchors), len(unresolved), max(max_hops, 1), total_related,
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
