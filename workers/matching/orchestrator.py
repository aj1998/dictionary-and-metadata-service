"""Orchestrates the full extract-matching pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from uuid import UUID

from neo4j import AsyncDriver

from jain_kb_common.matching import locate, normalize, threshold_for

from .apply_match import apply_match
from .source_iter import SourceBlock, iter_keyword_blocks, iter_topic_extract_blocks
from .target_resolver import Target, resolve_targets, resolve_targets_for_shastra

logger = logging.getLogger("jain_kb.matching.orchestrator")


@dataclass
class Stats:
    blocks_processed: int = 0
    edges_attempted: int = 0
    matched: int = 0
    unmatched: int = 0
    target_missing: int = 0
    elapsed_seconds: float = 0.0


async def _process_block(
    mongo,
    neo4j: AsyncDriver,
    source: SourceBlock,
    *,
    run_id: UUID,
    stats: Stats,
    dry_run: bool = False,
    database: str = "jainkb",
) -> None:
    targets: list[Target] = await resolve_targets(
        neo4j, mongo, source, database=database
    )
    if not targets:
        logger.debug(
            "no targets for %s:b%d", source.parent_natural_key, source.block_index
        )

    for target in targets:
        stats.edges_attempted += 1
        result = None

        if target.status_hint == "target_missing":
            stats.target_missing += 1
        elif target.text and source.text_devanagari:
            src_norm = normalize(source.text_devanagari)
            tgt_norm = normalize(target.text)
            threshold = threshold_for(source.block_kind)  # type: ignore[arg-type]
            result = locate(src_norm, tgt_norm, threshold=threshold)
            if result.matched:
                stats.matched += 1
                logger.info(
                    "matched source=%s:b%d target=%s method=%s score=%.4f",
                    source.parent_natural_key,
                    source.block_index,
                    target.natural_key,
                    result.method,
                    result.score,
                )
            else:
                stats.unmatched += 1
                logger.info(
                    "unmatched source=%s:b%d target=%s score=%.4f",
                    source.parent_natural_key,
                    source.block_index,
                    target.natural_key,
                    result.score,
                )
        else:
            # target text missing from Mongo doc (empty text list)
            stats.unmatched += 1

        await apply_match(
            mongo, source, target, result,
            run_id=run_id, dry_run=dry_run,
        )

    stats.blocks_processed += 1


async def match_all(
    mongo,
    neo4j: AsyncDriver,
    *,
    run_id: UUID,
    dry_run: bool = False,
    limit: int | None = None,
    database: str = "jainkb",
) -> Stats:
    """Run matching for all keyword_definition and topic_extract blocks."""
    stats = Stats()
    t0 = time.monotonic()
    count = 0

    async for source in iter_keyword_blocks(mongo):
        if limit is not None and count >= limit:
            break
        await _process_block(
            mongo, neo4j, source, run_id=run_id, stats=stats,
            dry_run=dry_run, database=database,
        )
        count += 1

    async for source in iter_topic_extract_blocks(mongo):
        if limit is not None and count >= limit:
            break
        await _process_block(
            mongo, neo4j, source, run_id=run_id, stats=stats,
            dry_run=dry_run, database=database,
        )
        count += 1

    stats.elapsed_seconds = time.monotonic() - t0
    _log_summary(stats)
    return stats


async def match_for_jainkosh_keyword(
    mongo,
    neo4j: AsyncDriver,
    *,
    keyword_nk: str,
    run_id: UUID,
    dry_run: bool = False,
    database: str = "jainkb",
) -> Stats:
    """Run matching for all blocks in a single keyword_definition."""
    stats = Stats()
    t0 = time.monotonic()

    async for source in iter_keyword_blocks(mongo, keyword_natural_key=keyword_nk):
        await _process_block(
            mongo, neo4j, source, run_id=run_id, stats=stats,
            dry_run=dry_run, database=database,
        )

    stats.elapsed_seconds = time.monotonic() - t0
    _log_summary(stats)
    return stats


async def match_for_jainkosh_topic(
    mongo,
    neo4j: AsyncDriver,
    *,
    topic_nk: str,
    run_id: UUID,
    dry_run: bool = False,
    database: str = "jainkb",
) -> Stats:
    """Run matching for all blocks in a single topic_extract."""
    stats = Stats()
    t0 = time.monotonic()

    async for source in iter_topic_extract_blocks(mongo, topic_natural_key=topic_nk):
        await _process_block(
            mongo, neo4j, source, run_id=run_id, stats=stats,
            dry_run=dry_run, database=database,
        )

    stats.elapsed_seconds = time.monotonic() - t0
    _log_summary(stats)
    return stats


async def match_for_nj_shastra(
    mongo,
    neo4j: AsyncDriver,
    *,
    shastra_nk: str,
    run_id: UUID,
    dry_run: bool = False,
    database: str = "jainkb",
) -> Stats:
    """
    Run matching for all blocks whose resolved stub targets belong to shastra_nk.
    Queries Neo4j for stubs in the shastra, then fetches the relevant source blocks.
    """
    stats = Stats()
    t0 = time.monotonic()

    block_refs = await resolve_targets_for_shastra(
        neo4j, shastra_nk=shastra_nk, database=database
    )

    seen: set[tuple] = set()
    for ref in block_refs:
        parent_nk: str = ref["parent_nk"] or ""
        parent_labels: list[str] = ref.get("parent_labels") or []
        block_idx: int = ref.get("block_idx") or 0
        section_idx = ref.get("section_idx")
        def_idx = ref.get("def_idx")

        dedup_key = (parent_nk, block_idx, section_idx, def_idx)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if "Keyword" in parent_labels:
            async for source in iter_keyword_blocks(
                mongo, keyword_natural_key=parent_nk
            ):
                if (
                    source.block_index == block_idx
                    and source.section_index == section_idx
                    and source.definition_index == def_idx
                ):
                    await _process_block(
                        mongo, neo4j, source, run_id=run_id, stats=stats,
                        dry_run=dry_run, database=database,
                    )
                    break
        elif "Topic" in parent_labels:
            async for source in iter_topic_extract_blocks(
                mongo, topic_natural_key=parent_nk
            ):
                if source.block_index == block_idx:
                    await _process_block(
                        mongo, neo4j, source, run_id=run_id, stats=stats,
                        dry_run=dry_run, database=database,
                    )
                    break

    stats.elapsed_seconds = time.monotonic() - t0
    _log_summary(stats)
    return stats


def _log_summary(stats: Stats) -> None:
    logger.info(
        "run complete: blocks=%d edges=%d matched=%d unmatched=%d target_missing=%d elapsed=%.1fs",
        stats.blocks_processed,
        stats.edges_attempted,
        stats.matched,
        stats.unmatched,
        stats.target_missing,
        stats.elapsed_seconds,
    )
