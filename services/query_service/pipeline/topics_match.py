from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import TOPIC_EXTRACTS

logger = logging.getLogger(__name__)

HINDI_BLOCK_KINDS = {"hindi_text", "hindi_gatha"}
BLOCK_TEXT_CAP = 1500
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
        if isinstance(item, dict) and item.get("lang") == "hi":
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
    """Fetch topic_extracts from Mongo; returns {natural_key: [ExtractBlock dicts]}."""
    result: dict[str, list[dict]] = {}
    cursor = mongo_db[TOPIC_EXTRACTS].find(  # type: ignore[index]
        {"natural_key": {"$in": natural_keys}},
        {"natural_key": 1, "blocks": 1, "_id": 0},
    )
    async for doc in cursor:
        nk = doc["natural_key"]
        blocks_out: list[dict] = []
        for idx, block in enumerate(doc.get("blocks", [])):
            kind = block.get("kind", "")
            if kind in HINDI_BLOCK_KINDS:
                raw = block.get("text_devanagari") or ""
                text_hi = raw[:BLOCK_TEXT_CAP]
                if text_hi:
                    blocks_out.append({"block_index": idx, "text_hi": text_hi})
        result[nk] = blocks_out
    return result


def extract_references_from_blocks(blocks: list[dict]) -> list[dict]:
    """Extract {shastra_natural_key, gatha_number, teeka_natural_key, page_number} from block refs."""
    refs: list[dict] = []
    seen: set[tuple] = set()
    for block in blocks:
        for ref in block.get("references", []):
            rf: dict[str, object] = {f["field"]: f["value"] for f in ref.get("resolved_fields", [])}
            shastra_nk = rf.get("shastra") or ref.get("shastra_name") or None
            if shastra_nk == "":
                shastra_nk = None

            raw_gatha = rf.get("gatha_number") or rf.get("gatha")
            gatha_num: int | None = None
            try:
                gatha_num = int(raw_gatha) if raw_gatha is not None else None
            except (ValueError, TypeError):
                pass

            teeka_nk = rf.get("teeka") or ref.get("teeka_name") or None
            if teeka_nk == "":
                teeka_nk = None

            raw_page = rf.get("page_number") or rf.get("page")
            page_num: int | None = None
            try:
                page_num = int(raw_page) if raw_page is not None else None
            except (ValueError, TypeError):
                pass

            key = (shastra_nk, gatha_num, teeka_nk, page_num)
            if any(v is not None for v in key) and key not in seen:
                seen.add(key)
                refs.append({
                    "shastra_natural_key": shastra_nk,
                    "gatha_number": gatha_num,
                    "teeka_natural_key": teeka_nk,
                    "page_number": page_num,
                })
    return refs
