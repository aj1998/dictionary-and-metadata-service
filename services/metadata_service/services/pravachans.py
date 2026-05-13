from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.anuyogas import Anuyoga
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.pravachans import Pravachan
from jain_kb_common.db.postgres.shastras import Shastra, ShastrasAnuyoga


async def get_by_ident(session: AsyncSession, ident: str) -> Pravachan | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Pravachan, uid)
    except ValueError:
        result = await session.execute(
            select(Pravachan).where(Pravachan.natural_key == ident)
        )
        return result.scalar_one_or_none()


async def get_shastra_for(session: AsyncSession, p: Pravachan) -> Shastra | None:
    if not p.shastra_id:
        return None
    return await session.get(Shastra, p.shastra_id)


async def get_shastra_author(session: AsyncSession, shastra: Shastra) -> Author | None:
    if not shastra.author_id:
        return None
    return await session.get(Author, shastra.author_id)


async def get_shastra_anuyogas(session: AsyncSession, shastra: Shastra) -> list[Anuyoga]:
    rows = await session.execute(
        select(Anuyoga)
        .join(ShastrasAnuyoga, ShastrasAnuyoga.anuyoga_id == Anuyoga.id)
        .where(ShastrasAnuyoga.shastra_id == shastra.id)
    )
    return list(rows.scalars())


async def get_speaker_for(session: AsyncSession, p: Pravachan) -> Author | None:
    if not p.speaker_id:
        return None
    return await session.get(Author, p.speaker_id)


async def list_pravachans(
    session: AsyncSession,
    limit: int,
    offset: int,
    shastra_id: uuid.UUID | None = None,
    speaker_id: uuid.UUID | None = None,
) -> tuple[list[Pravachan], int]:
    stmt = select(Pravachan)
    cnt_stmt = select(func.count()).select_from(Pravachan)
    if shastra_id is not None:
        stmt = stmt.where(Pravachan.shastra_id == shastra_id)
        cnt_stmt = cnt_stmt.where(Pravachan.shastra_id == shastra_id)
    if speaker_id is not None:
        stmt = stmt.where(Pravachan.speaker_id == speaker_id)
        cnt_stmt = cnt_stmt.where(Pravachan.speaker_id == speaker_id)
    total = await session.scalar(cnt_stmt)
    rows = await session.execute(
        stmt.order_by(Pravachan.natural_key).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


async def create_pravachan(session: AsyncSession, data: dict[str, Any]) -> Pravachan:
    p = Pravachan(**data)
    session.add(p)
    await session.flush()
    await session.refresh(p)
    return p


async def update_pravachan(
    session: AsyncSession, p: Pravachan, data: dict[str, Any]
) -> Pravachan:
    for k, v in data.items():
        setattr(p, k, v)
    await session.flush()
    await session.refresh(p)
    return p
