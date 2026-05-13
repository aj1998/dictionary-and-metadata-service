from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.publications import Publication
from jain_kb_common.db.postgres.teekas import Teeka


async def get_by_ident(session: AsyncSession, ident: str) -> Publication | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Publication, uid)
    except ValueError:
        result = await session.execute(
            select(Publication).where(Publication.natural_key == ident)
        )
        return result.scalar_one_or_none()


async def list_publications(
    session: AsyncSession,
    limit: int,
    offset: int,
    teeka_id: uuid.UUID | None = None,
    publisher_id: str | None = None,
) -> tuple[list[Publication], int]:
    stmt = select(Publication)
    cnt_stmt = select(func.count()).select_from(Publication)
    if teeka_id is not None:
        stmt = stmt.where(Publication.teeka_id == teeka_id)
        cnt_stmt = cnt_stmt.where(Publication.teeka_id == teeka_id)
    if publisher_id is not None:
        stmt = stmt.where(Publication.publisher_id == publisher_id)
        cnt_stmt = cnt_stmt.where(Publication.publisher_id == publisher_id)
    total = await session.scalar(cnt_stmt)
    rows = await session.execute(
        stmt.order_by(Publication.natural_key).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


async def list_by_teeka(
    session: AsyncSession, teeka_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Publication], int]:
    return await list_publications(session, limit, offset, teeka_id=teeka_id)


async def get_teeka_for(session: AsyncSession, pub: Publication) -> Teeka | None:
    return await session.get(Teeka, pub.teeka_id)


async def create_publication(session: AsyncSession, data: dict[str, Any]) -> Publication:
    pub = Publication(**data)
    session.add(pub)
    await session.flush()
    await session.refresh(pub)
    return pub


async def update_publication(
    session: AsyncSession, pub: Publication, data: dict[str, Any]
) -> Publication:
    for k, v in data.items():
        setattr(pub, k, v)
    await session.flush()
    await session.refresh(pub)
    return pub
