from __future__ import annotations

import asyncio
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import TOPIC_EXTRACTS
from jain_kb_common.db.postgres.keywords import Keyword
from jain_kb_common.db.postgres.topics import Topic


async def get_by_ident(session: AsyncSession, ident: str) -> Topic | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Topic, uid)
    except ValueError:
        result = await session.execute(
            select(Topic).where(Topic.natural_key == ident)
        )
        return result.scalar_one_or_none()


async def list_topics(
    session: AsyncSession,
    limit: int,
    offset: int,
    q: str | None = None,
    parent_keyword_id: uuid.UUID | None = None,
    source: str | None = None,
    is_leaf: bool | None = None,
) -> tuple[list[Topic], int]:
    stmt = select(Topic)
    cnt = select(func.count()).select_from(Topic)

    if q is not None:
        filter_expr = Topic.display_text.cast(
            type_=None
        )
        # use raw text ILIKE on JSONB cast
        from sqlalchemy import text as sa_text
        ilike_filter = sa_text("display_text::text ILIKE :pat").bindparams(pat=f"%{q}%")
        stmt = stmt.where(ilike_filter)
        cnt = cnt.where(ilike_filter)

    if parent_keyword_id is not None:
        stmt = stmt.where(Topic.parent_keyword_id == parent_keyword_id)
        cnt = cnt.where(Topic.parent_keyword_id == parent_keyword_id)

    if source is not None:
        stmt = stmt.where(Topic.source == source)
        cnt = cnt.where(Topic.source == source)

    if is_leaf is not None:
        stmt = stmt.where(Topic.is_leaf == is_leaf)
        cnt = cnt.where(Topic.is_leaf == is_leaf)

    total = await session.scalar(cnt)
    rows = await session.execute(
        stmt.order_by(Topic.natural_key).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


async def get_extracts(mongo: AsyncIOMotorDatabase, topic: Topic) -> list[dict]:
    cursor = mongo[TOPIC_EXTRACTS].find({"natural_key": topic.natural_key})
    docs = await cursor.to_list(None)
    for d in docs:
        d.pop("_id", None)
    return docs


async def get_detail(session: AsyncSession, mongo: AsyncIOMotorDatabase, topic: Topic) -> dict:
    parent_keyword: Keyword | None = None
    parent_topic: Topic | None = None

    tasks_pg = []
    if topic.parent_keyword_id:
        tasks_pg.append(session.get(Keyword, topic.parent_keyword_id))
    else:
        tasks_pg.append(_noop())

    if topic.parent_topic_id:
        tasks_pg.append(session.get(Topic, topic.parent_topic_id))
    else:
        tasks_pg.append(_noop())

    extracts_task = get_extracts(mongo, topic)
    pg_result, extracts = await asyncio.gather(
        asyncio.gather(*tasks_pg),
        extracts_task,
    )
    parent_keyword = pg_result[0]
    parent_topic = pg_result[1]

    return {
        "topic": topic,
        "parent_keyword": parent_keyword,
        "parent_topic": parent_topic,
        "extracts": extracts,
    }


async def _noop():
    return None
