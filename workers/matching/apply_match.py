"""Upsert an extract_matches document for a (source_block, target) pair."""

from __future__ import annotations

import logging
from uuid import UUID

from jain_kb_common.db.mongo.upserts import upsert_extract_match
from jain_kb_common.matching import MatchResult, threshold_for

from .source_iter import SourceBlock
from .target_resolver import Target

logger = logging.getLogger("jain_kb.matching.apply_match")


def _build_natural_key(source: SourceBlock, target_nk: str) -> str:
    if source.kind == "keyword_definition":
        return (
            f"match:keyword_definition:{source.parent_natural_key}"
            f":s{source.section_index}:d{source.definition_index}"
            f":b{source.block_index}:target:{target_nk}"
        )
    return (
        f"match:topic_extract:{source.parent_natural_key}"
        f":b{source.block_index}:target:{target_nk}"
    )


async def apply_match(
    mongo,
    source: SourceBlock,
    target: Target,
    result: MatchResult | None,
    *,
    run_id: UUID,
    dry_run: bool = False,
) -> None:
    """Upsert one extract_matches document. Skips write when dry_run=True."""
    nk = _build_natural_key(source, target.natural_key)
    threshold = threshold_for(target.match_block_kind or source.block_kind)  # type: ignore[arg-type]

    if target.status_hint == "target_missing":
        match_status = "target_missing"
        method = "none"
        score = 0.0
        char_start = None
        char_end = None
    elif result is None or not result.matched:
        match_status = "unmatched"
        method = result.method if result else "none"
        score = result.score if result else 0.0
        char_start = None
        char_end = None
    else:
        match_status = "matched"
        method = result.method
        score = result.score
        char_start = result.char_start
        char_end = result.char_end

    source_doc: dict = {
        "kind": source.kind,
        "parent_natural_key": source.parent_natural_key,
        "block_index": source.block_index,
        "block_kind": source.block_kind,
        "text_devanagari": source.text_devanagari,
        "reference_text": source.reference_text,
    }
    # Record which source field was matched so downstream/debugging can tell the
    # verse match (text_devanagari) from the anvayartha match (hindi_translation).
    if target.source_text_kind == "hindi_translation":
        source_doc["source_text_kind"] = "hindi_translation"
        source_doc["hindi_translation"] = source.hindi_translation
    if source.kind == "keyword_definition":
        source_doc["section_index"] = source.section_index
        source_doc["definition_index"] = source.definition_index

    doc = {
        "source": source_doc,
        "target": {
            "collection": target.collection,
            "natural_key": target.natural_key,
            "stub_label": target.stub_label,
            "shastra_natural_key": target.shastra_natural_key,
            "gatha_natural_key": target.gatha_natural_key,
            "lang": target.lang,
        },
        "match": {
            "status": match_status,
            "method": method,
            "score": score,
            "char_start": char_start,
            "char_end": char_end,
            "threshold": threshold,
        },
        "matcher_version": "1.0.0",
        "ingestion_run_id": str(run_id),
    }

    logger.info(
        "apply_match source_nk=%s target_nk=%s status=%s score=%.4f",
        f"{source.parent_natural_key}:b{source.block_index}",
        target.natural_key,
        match_status,
        score,
    )

    if not dry_run:
        await upsert_extract_match(mongo, natural_key=nk, doc=doc)
