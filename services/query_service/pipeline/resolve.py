from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .normalize import nfc, strip_one_suffix

logger = logging.getLogger(__name__)

HINDI_KINDS = {"hindi_text", "hindi_gatha"}
BLOCK_TEXT_CAP = 1500


@dataclass
class Resolution:
    input_token: str
    match_kind: str  # "exact", "alias", "suffix_strip", "none"
    keyword_natural_key: Optional[str] = None
    keyword_id: Optional[str] = None
    suggestions: list[dict] = field(default_factory=list)


async def resolve_tokens(
    session: AsyncSession,
    tokens: list[str],
    fuzzy_top_k: int = 5,
    min_similarity: float = 0.35,
) -> list[Resolution]:
    """Resolve tokens via exact/alias/suffix-strip/fuzzy passes."""
    # Deduplicate while preserving order
    seen: dict[str, int] = {}
    for i, t in enumerate(tokens):
        if t not in seen:
            seen[t] = i
    unique_tokens = list(seen.keys())

    # NFC normalize
    normalized = [nfc(t) for t in unique_tokens]

    # Pass 1+2: exact + alias in single SQL
    resolved_map: dict[str, Resolution] = {}
    await _batch_lookup(session, normalized, resolved_map, suffix_stripped=False)

    # Find misses
    missed_normalized = [t for t in normalized if t not in resolved_map]

    # Pass 3: suffix-strip + re-lookup
    if missed_normalized:
        stripped_map: dict[str, str] = {}  # stripped -> original normalized
        stripped_tokens = []
        for orig in missed_normalized:
            stripped = strip_one_suffix(orig)
            if stripped != orig:
                stripped_map[stripped] = orig
                stripped_tokens.append(stripped)

        if stripped_tokens:
            strip_resolved: dict[str, Resolution] = {}
            await _batch_lookup(session, stripped_tokens, strip_resolved, suffix_stripped=True)
            for stripped, res in strip_resolved.items():
                orig = stripped_map[stripped]
                resolved_map[orig] = Resolution(
                    input_token=orig,
                    match_kind="suffix_strip",
                    keyword_natural_key=res.keyword_natural_key,
                    keyword_id=res.keyword_id,
                )

    # Pass 4: fuzzy for still-unresolved
    still_missed = [t for t in normalized if t not in resolved_map]
    fuzzy_map: dict[str, list[dict]] = {}
    if still_missed:
        fuzzy_map = await fuzzy_suggestions(session, still_missed, fuzzy_top_k, min_similarity)

    # Build final results in input order
    result = []
    for orig_token in unique_tokens:
        norm = nfc(orig_token)
        if norm in resolved_map:
            r = resolved_map[norm]
            result.append(Resolution(
                input_token=orig_token,
                match_kind=r.match_kind,
                keyword_natural_key=r.keyword_natural_key,
                keyword_id=r.keyword_id,
            ))
        else:
            result.append(Resolution(
                input_token=orig_token,
                match_kind="none",
                suggestions=fuzzy_map.get(norm, []),
            ))
    return result


async def _batch_lookup(
    session: AsyncSession,
    tokens: list[str],
    out: dict[str, Resolution],
    suffix_stripped: bool,
) -> None:
    if not tokens:
        return
    sql = text("""
        WITH input(tok) AS (SELECT unnest(CAST(:tokens AS text[])))
        SELECT i.tok,
               k.natural_key AS keyword_natural_key,
               k.id::text    AS keyword_id,
               'exact'::text AS match_kind
        FROM input i
        JOIN keywords k ON k.natural_key = i.tok
        UNION ALL
        SELECT i.tok,
               k.natural_key,
               k.id::text,
               'alias'::text
        FROM input i
        JOIN keyword_aliases ka ON ka.alias_text = i.tok
        JOIN keywords k ON k.id = ka.keyword_id
        WHERE NOT EXISTS (
            SELECT 1 FROM keywords k2 WHERE k2.natural_key = i.tok
        )
    """)
    rows = await session.execute(sql, {"tokens": tokens})
    for row in rows:
        tok = row.tok
        if tok not in out:
            out[tok] = Resolution(
                input_token=tok,
                match_kind=row.match_kind,
                keyword_natural_key=row.keyword_natural_key,
                keyword_id=row.keyword_id,
            )


async def fuzzy_suggestions(
    session: AsyncSession,
    tokens: list[str],
    top_k: int,
    min_similarity: float,
) -> dict[str, list[dict]]:
    if not tokens:
        return {}
    sql = text("""
        WITH unresolved(tok) AS (SELECT unnest(CAST(:tokens AS text[])))
        SELECT u.tok,
               sub.natural_key AS keyword_natural_key,
               sub.sim         AS similarity
        FROM unresolved u
        CROSS JOIN LATERAL (
            SELECT k.natural_key, similarity(k.natural_key, u.tok) AS sim
            FROM keywords k
            WHERE similarity(k.natural_key, u.tok) >= :min_similarity
            UNION ALL
            SELECT k.natural_key, similarity(ka.alias_text, u.tok) AS sim
            FROM keyword_aliases ka
            JOIN keywords k ON k.id = ka.keyword_id
            WHERE similarity(ka.alias_text, u.tok) >= :min_similarity
            ORDER BY sim DESC
            LIMIT :top_k
        ) sub
        ORDER BY u.tok, sub.sim DESC
    """)
    rows = await session.execute(sql, {
        "tokens": tokens,
        "min_similarity": min_similarity,
        "top_k": top_k,
    })
    result: dict[str, list[dict]] = {}
    for row in rows:
        result.setdefault(row.tok, []).append({
            "keyword_natural_key": row.keyword_natural_key,
            "similarity": float(row.similarity),
        })
    return result


async def fetch_definitions_batch(
    mongo_db: object,
    natural_keys: list[str],
    definitions_per_keyword: int = 0,
) -> dict[str, list[dict]]:
    """Returns {natural_key: [DefinitionBlock dicts]}"""
    from jain_kb_common.db.mongo.collections import KEYWORD_DEFINITIONS

    cursor = mongo_db[KEYWORD_DEFINITIONS].find(  # type: ignore[index]
        {"natural_key": {"$in": natural_keys}},
        {"natural_key": 1, "page_sections": 1, "_id": 0},
    )

    result: dict[str, list[dict]] = {}
    async for doc in cursor:
        nk = doc["natural_key"]
        blocks_out: list[dict] = []
        block_index = 0
        for section in doc.get("page_sections", []):
            for defn in section.get("definitions", []):
                for block in defn.get("blocks", []):
                    kind = block.get("kind", "")
                    if kind in HINDI_KINDS:
                        raw_text = block.get("text_devanagari") or ""
                        text_hi = raw_text[:BLOCK_TEXT_CAP]
                        if text_hi:
                            blocks_out.append({
                                "source_natural_key": nk,
                                "block_index": block_index,
                                "text_hi": text_hi,
                            })
                        block_index += 1
        if definitions_per_keyword > 0:
            blocks_out = blocks_out[:definitions_per_keyword]
        result[nk] = blocks_out
    return result
