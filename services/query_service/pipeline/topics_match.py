from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.hydration.topic_extracts import (
    extract_references,
    hydrate_topic_extracts_hi,
)

logger = logging.getLogger(__name__)
LEAF_SCORE_FACTOR = 1.0
CONTAINER_SCORE_FACTOR = 0.6


@dataclass
class TopicTrigramHit:
    topic_pg_id: str
    natural_key: str
    display_text: object  # raw JSONB
    is_leaf: bool
    source: str
    similarity: float
    score: float = field(init=False)

    def __post_init__(self) -> None:
        factor = LEAF_SCORE_FACTOR if self.is_leaf else CONTAINER_SCORE_FACTOR
        self.score = self.similarity * factor


def get_display_text_hi(display_text: object) -> str:
    """Extract Hindi text from the display_text JSONB field."""
    if display_text is None:
        return ""
    if isinstance(display_text, dict):
        display_text = [display_text]
    for item in (display_text or []):
        if isinstance(item, dict) and item.get("lang") in ("hin", "hi"):
            return item.get("text", "")
    return ""


def ancestors_from_natural_key(natural_key: str) -> list[str]:
    """Split a slash-separated natural_key and return all but the last segment."""
    parts = natural_key.split("/")
    return parts[:-1]


async def search_topics_trigram(
    session: AsyncSession,
    search_str: str,
    limit: int,
    min_similarity: float,
    leaf_only: bool,
) -> list[TopicTrigramHit]:
    """Run pg_trgm similarity search over topics.natural_key (slashes replaced with spaces)."""
    leaf_filter = "AND t.is_leaf = true" if leaf_only else ""
    sql = text(f"""
        WITH ranked AS (
            SELECT
                t.id::text AS topic_pg_id,
                t.natural_key,
                t.display_text,
                t.is_leaf,
                t.source,
                similarity(REPLACE(t.natural_key, '/', ' '), :search_str) AS sim
            FROM topics t
            WHERE similarity(REPLACE(t.natural_key, '/', ' '), :search_str) >= :min_similarity
            {leaf_filter}
        )
        SELECT *,
               sim * CASE WHEN is_leaf THEN {LEAF_SCORE_FACTOR} ELSE {CONTAINER_SCORE_FACTOR} END AS score
        FROM ranked
        ORDER BY score DESC
        LIMIT :limit
    """)
    rows = await session.execute(sql, {
        "search_str": search_str,
        "min_similarity": min_similarity,
        "limit": limit,
    })
    hits = []
    for row in rows:
        hits.append(TopicTrigramHit(
            topic_pg_id=row.topic_pg_id,
            natural_key=row.natural_key,
            display_text=row.display_text,
            is_leaf=row.is_leaf,
            source=str(row.source),
            similarity=float(row.sim),
        ))
    logger.debug(
        "topics_match trigram search_str=%r min_sim=%.2f leaf_only=%s → %d hits",
        search_str, min_similarity, leaf_only, len(hits),
    )
    return hits


async def fetch_topic_extracts_batch(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, list[dict]]:
    """Fetch topic_extracts from Mongo; returns {natural_key: [{block_index, text_hi}]}.

    Delegates to common hydrate_topic_extracts_hi; strips the per-block references
    field to preserve the existing caller contract.
    """
    rich = await hydrate_topic_extracts_hi(mongo_db, natural_keys)
    return {
        nk: [{"block_index": b["block_index"], "text_hi": b["text_hi"]} for b in blocks]
        for nk, blocks in rich.items()
    }


# Alias kept for existing callers in this module and graphrag.py
extract_references_from_blocks = extract_references
