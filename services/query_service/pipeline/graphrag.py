from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.hydration.topic_extracts import hydrate_topic_extracts_hi
from . import resolve as resolve_pipeline
from .ranking import RankedTopic, rank
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

    Returns {topic_nk: {"extracts_hi": [...], "references": [...], "neighbors": {...}}}.

    Single Mongo query via common hydrate_topic_extracts_hi covers both extracts
    and per-block references (eliminating the previous 2-query pattern).
    """
    topic_nks = [r.topic_nk for r in ranked]
    hydration: dict[str, dict] = {nk: {} for nk in topic_nks}

    if (include_extracts or include_references) and topic_nks:
        rich_map = await hydrate_topic_extracts_hi(mongo_db, topic_nks)
        for nk in topic_nks:
            rich_blocks = rich_map.get(nk, [])
            if include_extracts:
                hydration[nk]["extracts_hi"] = [
                    {
                        "block_index": b["block_index"],
                        "text_hi": b["text_hi"],
                        "main_reference": b.get("main_reference"),
                    }
                    for b in rich_blocks
                ]
            if include_references:
                seen: set[tuple] = set()
                flat_refs: list[dict] = []
                for b in rich_blocks:
                    for r in b.get("references", []):
                        key = (
                            r.get("shastra_natural_key"),
                            r.get("gatha_number"),
                            r.get("teeka_natural_key"),
                            r.get("page_number"),
                        )
                        if key not in seen:
                            seen.add(key)
                            flat_refs.append(r)
                hydration[nk]["references"] = flat_refs

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
