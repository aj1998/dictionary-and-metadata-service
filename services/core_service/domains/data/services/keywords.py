from __future__ import annotations

import asyncio
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import EXTRACT_MATCHES, KEYWORD_DEFINITIONS
from jain_kb_common.db.postgres.keywords import Keyword, KeywordAlias


async def get_by_ident(session: AsyncSession, ident: str) -> Keyword | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Keyword, uid)
    except ValueError:
        result = await session.execute(
            select(Keyword).where(Keyword.natural_key == ident)
        )
        return result.scalar_one_or_none()


async def list_keywords(
    session: AsyncSession,
    limit: int,
    offset: int,
    q: str | None = None,
    letter: str | None = None,
) -> tuple[list[Keyword], int]:
    stmt = select(Keyword)
    cnt = select(func.count()).select_from(Keyword)

    if letter is not None:
        like = f"{letter}%"
        stmt = stmt.where(Keyword.display_text.like(like))
        cnt = cnt.where(Keyword.display_text.like(like))

    if q is not None:
        alias_sub = select(KeywordAlias.keyword_id).where(
            KeywordAlias.alias_text.ilike(f"%{q}%")
        )
        filter_expr = or_(
            Keyword.display_text.ilike(f"%{q}%"),
            Keyword.id.in_(alias_sub),
        )
        stmt = stmt.where(filter_expr)
        cnt = cnt.where(filter_expr)

    total = await session.scalar(cnt)
    rows = await session.execute(
        stmt.order_by(Keyword.display_text).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


async def get_aliases(session: AsyncSession, keyword: Keyword) -> list[KeywordAlias]:
    rows = await session.execute(
        select(KeywordAlias).where(KeywordAlias.keyword_id == keyword.id)
    )
    return list(rows.scalars())


async def get_letter_counts(session: AsyncSession) -> list[dict]:
    rows = await session.execute(
        text(
            "SELECT substring(display_text, 1, 1) AS letter, COUNT(*) AS count "
            "FROM keywords GROUP BY letter ORDER BY letter"
        )
    )
    return [{"letter": r.letter, "count": r.count} for r in rows]


async def _hydrate_match_natural_keys(mongo: AsyncIOMotorDatabase, natural_key: str, definition: dict) -> None:
    """Inject match_natural_keys into each matched block of the definition doc (in-place)."""
    # Include matched + unmatched + target_missing so the UI can render
    # grey-coloured links for refs whose target gatha is known but whose
    # text didn't match (so users can still navigate to the gatha).
    cursor = mongo[EXTRACT_MATCHES].find(
        {
            "source.parent_natural_key": natural_key,
            "source.kind": "keyword_definition",
        },
        {"natural_key": 1, "source.section_index": 1, "source.definition_index": 1, "source.block_index": 1},
    )
    async for match in cursor:
        s_idx = match["source"]["section_index"]
        d_idx = match["source"]["definition_index"]
        b_idx = match["source"]["block_index"]
        try:
            # page_sections is a list; find by section_index field
            section = next((s for s in definition.get("page_sections", []) if s.get("section_index") == s_idx), None)
            if section is None:
                continue
            defn = next((d for d in section.get("definitions", []) if d.get("definition_index") == d_idx), None)
            if defn is None:
                continue
            blocks = defn.get("blocks", [])
            if b_idx < len(blocks):
                block = blocks[b_idx]
                if "match_natural_keys" not in block:
                    block["match_natural_keys"] = []
                block["match_natural_keys"].append(match["natural_key"])
        except (KeyError, IndexError, TypeError):
            continue


async def get_definition(mongo: AsyncIOMotorDatabase, keyword: Keyword) -> dict | None:
    doc = await mongo[KEYWORD_DEFINITIONS].find_one({"natural_key": keyword.natural_key})
    if doc is None:
        return None
    doc.pop("_id", None)
    await _hydrate_match_natural_keys(mongo, keyword.natural_key, doc)
    return doc


async def get_detail(session: AsyncSession, mongo: AsyncIOMotorDatabase, keyword: Keyword) -> dict:
    aliases_task = get_aliases(session, keyword)
    definition_task = get_definition(mongo, keyword)
    aliases, definition = await asyncio.gather(aliases_task, definition_task)
    return {"keyword": keyword, "aliases": aliases, "definition": definition}


async def update_keyword(session: AsyncSession, keyword: Keyword, data: dict) -> Keyword:
    for k, v in data.items():
        setattr(keyword, k, v)
    await session.flush()
    await session.refresh(keyword)
    return keyword
