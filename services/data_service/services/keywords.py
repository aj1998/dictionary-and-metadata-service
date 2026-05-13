from __future__ import annotations

import asyncio
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import KEYWORD_DEFINITIONS
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


async def get_definition(mongo: AsyncIOMotorDatabase, keyword: Keyword) -> dict | None:
    if not keyword.definition_doc_ids:
        return None
    doc = await mongo[KEYWORD_DEFINITIONS].find_one({"natural_key": keyword.natural_key})
    if doc is None:
        return None
    doc.pop("_id", None)
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
