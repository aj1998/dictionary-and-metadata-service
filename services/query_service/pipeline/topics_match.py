from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import TOPIC_EXTRACTS
from jain_kb_common.hydration.topic_extracts import (
    count_displayable_extract_blocks,
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
    """Return the human-readable ancestor segments of a topic natural_key.

    Real jainkosh topic keys are colon-separated with kebab-cased Hindi
    segments (e.g. ``द्रव्य:द्रव्य-के-भेद-व-लक्षण:...``); legacy/spec keys use
    ``/`` (e.g. ``द्रव्य/स्वतंत्रता/लक्षण``). We pick whichever separator is
    present (preferring ``:``), drop the leaf segment, and turn ``-`` back into
    spaces so the breadcrumb reads naturally.
    """
    sep = ":" if ":" in natural_key else "/"
    parts = natural_key.split(sep)
    return [p.replace("-", " ") for p in parts[:-1]]


async def search_topics_trigram(
    session: AsyncSession,
    search_str: str,
    limit: int,
    min_similarity: float,
    leaf_only: bool,
) -> list[TopicTrigramHit]:
    """Match topics over their natural_key path, merging two logics:

    1. **Leaf substring (ILIKE)** — a literal match of the search string inside
       the topic's own Hindi ``display_text`` (the leaf heading). This catches
       exact occurrences (e.g. ``विभाव`` inside ``स्वभाव विभाव गुणों के लक्षण``)
       without phonetically over-matching neighbours like ``विभाग``. Crucially
       it matches the *leaf* only, **not** the ancestor path — otherwise every
       descendant of a matching ancestor (the whole ``द्रव्य/…/स्वतंत्रता``
       branch) would spuriously score 1.0. Leaf substring hits get ``sim = 1.0``.
    2. **Trigram similarity** — parent-aware fuzzy match against the full
       natural_key path (slashes → spaces), so multi-word phrase queries such as
       ``द्रव्य स्वतंत्रता`` still resolve ``द्रव्य/स्वतंत्रता/लक्षण`` even when
       no exact leaf substring is present. These contextual matches score below
       1.0 and rank under the direct leaf matches.

    A topic qualifies if *either* logic matches; the reported ``sim`` is the
    greater of the two. ``score`` then applies the leaf/container weighting.
    """
    leaf_filter = "AND t.is_leaf = true" if leaf_only else ""
    sql = text(f"""
        WITH ranked AS (
            SELECT
                t.id::text AS topic_pg_id,
                t.natural_key,
                t.display_text,
                t.is_leaf,
                t.source,
                GREATEST(
                    similarity(REPLACE(t.natural_key, '/', ' '), :search_str),
                    CASE
                        WHEN t.display_text::text ILIKE :like_pat
                        THEN 1.0 ELSE 0.0
                    END
                ) AS sim
            FROM topics t
            WHERE (
                similarity(REPLACE(t.natural_key, '/', ' '), :search_str) >= :min_similarity
                OR t.display_text::text ILIKE :like_pat
            )
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
        "like_pat": f"%{search_str}%",
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
        nk: [
            {
                "block_index": b["block_index"],
                "text_hi": b["text_hi"],
                "main_reference": b.get("main_reference"),
            }
            for b in blocks
        ]
        for nk, blocks in rich.items()
    }


async def fetch_topic_references_batch(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, list[dict]]:
    """Fetch flattened, de-duplicated references per topic from Mongo.

    Delegates to the common ``hydrate_topic_extracts_hi`` (which already extracts
    per-block references) and flattens them per topic in document order, mirroring
    the reference-assembly logic used by ``graphrag.hydrate_topics``. Returns
    ``{natural_key: [reference_dict, ...]}``.
    """
    if not natural_keys:
        return {}
    rich = await hydrate_topic_extracts_hi(mongo_db, natural_keys)
    out: dict[str, list[dict]] = {}
    for nk, blocks in rich.items():
        seen: set[tuple] = set()
        flat_refs: list[dict] = []
        for b in blocks:
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
        out[nk] = flat_refs
    return out


async def fetch_topic_source_urls(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, str]:
    """Return {natural_key: source_url} for the given topics.

    Reads the top-level ``source_url`` of each topic_extracts doc (the canonical
    jainkosh wiki page + section anchor for the extract). Topics with no doc or
    no source_url are simply absent from the result.
    """
    if not natural_keys:
        return {}
    out: dict[str, str] = {}
    cursor = mongo_db[TOPIC_EXTRACTS].find(  # type: ignore[index]
        {"natural_key": {"$in": natural_keys}},
        {"natural_key": 1, "source_url": 1, "_id": 0},
    )
    async for doc in cursor:
        url = doc.get("source_url")
        if url:
            out[doc["natural_key"]] = url
    logger.debug(
        "fetch_topic_source_urls topics=%d → urls=%d",
        len(natural_keys), len(out),
    )
    return out


async def count_topic_extract_blocks(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, int]:
    """Return {natural_key: displayable block count} for the given topics.

    Delegates to the shared ``count_displayable_extract_blocks`` so the search
    cards count only blocks the modal would actually render (excluding
    ``see_also`` / ``table`` and text-less blocks) and gate the "पढ़ें"
    affordance accurately. Mirrors the data-service topics listing, which uses
    the same shared helper.
    """
    return await count_displayable_extract_blocks(mongo_db, natural_keys)


# Alias kept for existing callers in this module and graphrag.py
extract_references_from_blocks = extract_references
