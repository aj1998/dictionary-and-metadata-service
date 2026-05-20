from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from . import resolve as resolve_pipeline
from .ranking import RankedTopic, rank
from .topics_match import (
    extract_references_from_blocks,
    fetch_topic_extracts_batch,
)
from .traverse import bucket_neighbors, fetch_neighbors, traverse_topics

logger = logging.getLogger(__name__)


async def run_graphrag(
    session: AsyncSession,
    mongo_db: object,
    neo4j_driver: object,
    neo4j_database: str,
    tokens: list[str],
    max_hops: int,
    limit: int,
    edge_types: list[str] | None,
    include_extracts: bool,
    include_neighbors: bool,
    include_references: bool,
    fuzzy: bool,
) -> tuple[list[RankedTopic], list[str]]:
    """
    Stages 1–5 of the GraphRAG pipeline.

    Returns (ranked_topics[:limit], unresolved_tokens).
    Hydration (Stage 6) of extracts/neighbors is handled by the caller so
    the route handler can attach them to the schema objects.
    """
    # Stage 1–3: normalize + resolve
    resolutions = await resolve_pipeline.resolve_tokens(
        session,
        tokens,
        fuzzy_top_k=5,
        min_similarity=0.35,
    )

    seed_kws: list[str] = []
    unresolved: list[str] = []
    for r in resolutions:
        if r.match_kind in ("exact", "alias", "suffix_strip") and r.keyword_natural_key:
            seed_kws.append(r.keyword_natural_key)
        elif r.match_kind == "none":
            if fuzzy and r.suggestions:
                # use top fuzzy suggestion as seed
                seed_kws.append(r.suggestions[0]["keyword_natural_key"])
            else:
                unresolved.append(r.input_token)

    logger.debug(
        "graphrag tokens=%d seeds=%d unresolved=%d fuzzy=%s",
        len(tokens), len(seed_kws), len(unresolved), fuzzy,
    )

    # Stage 4: graph traversal
    hits = await traverse_topics(
        neo4j_driver,
        list(dict.fromkeys(seed_kws)),  # deduplicate, preserve order
        max_hops=max_hops,
        edge_types=edge_types,
        database=neo4j_database,
    )

    # Stage 5: ranking
    ranked = rank(hits, seed_kws)[:limit]
    return ranked, unresolved


async def hydrate_topics(
    mongo_db: object,
    neo4j_driver: object,
    neo4j_database: str,
    ranked: list[RankedTopic],
    include_extracts: bool,
    include_neighbors: bool,
    include_references: bool,
) -> dict[str, dict]:
    """
    Stage 6: batch-fetch topic_extracts + optional neighbor rows.

    Returns a dict keyed by topic_nk with hydration payloads:
    {topic_nk: {"extracts_hi": [...], "references": [...], "neighbors": {...}}}
    """
    topic_nks = [r.topic_nk for r in ranked]
    hydration: dict[str, dict] = {nk: {} for nk in topic_nks}

    if include_extracts and topic_nks:
        extracts_map = await fetch_topic_extracts_batch(mongo_db, topic_nks)
        for nk in topic_nks:
            blocks = extracts_map.get(nk, [])
            hydration[nk]["extracts_hi"] = blocks
            if include_references:
                # need raw block dicts for reference extraction - re-fetch raw
                pass  # handled below

    if (include_extracts and include_references) and topic_nks:
        raw_extracts = await _fetch_raw_blocks(mongo_db, topic_nks)
        for nk, raw_blocks in raw_extracts.items():
            refs = extract_references_from_blocks(raw_blocks)
            hydration[nk]["references"] = refs

    if include_neighbors and topic_nks:
        neighbor_rows = await fetch_neighbors(neo4j_driver, topic_nks, neo4j_database)
        bucketed = bucket_neighbors(neighbor_rows)
        for nk in topic_nks:
            hydration[nk]["neighbors"] = bucketed.get(nk, {
                "related_topics": [],
                "mentioned_in_gathas": [],
                "related_keywords": [],
            })

    return hydration


async def _fetch_raw_blocks(mongo_db: object, natural_keys: list[str]) -> dict[str, list[dict]]:
    """Fetch raw block dicts from topic_extracts for reference extraction."""
    from jain_kb_common.db.mongo.collections import TOPIC_EXTRACTS
    result: dict[str, list[dict]] = {}
    cursor = mongo_db[TOPIC_EXTRACTS].find(  # type: ignore[index]
        {"natural_key": {"$in": natural_keys}},
        {"natural_key": 1, "blocks": 1, "_id": 0},
    )
    async for doc in cursor:
        result[doc["natural_key"]] = doc.get("blocks", [])
    return result
