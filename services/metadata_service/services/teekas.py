from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.anuyogas import Anuyoga
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.shastras import Shastra, ShastrasAnuyoga
from jain_kb_common.db.postgres.teekas import Teeka


class TeekaDetail(TypedDict):
    teeka: Teeka
    shastra: Shastra | None
    shastra_author: Author | None
    shastra_anuyogas: list[Anuyoga]
    teekakar: Author | None
    total_publications: int


async def get_by_ident(session: AsyncSession, ident: str) -> Teeka | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Teeka, uid)
    except ValueError:
        result = await session.execute(select(Teeka).where(Teeka.natural_key == ident))
        return result.scalar_one_or_none()


async def get_detail(session: AsyncSession, teeka: Teeka) -> TeekaDetail:
    shastra: Shastra | None = None
    shastra_author: Author | None = None
    shastra_anuyogas: list[Anuyoga] = []
    if teeka.shastra_id:
        shastra = await session.get(Shastra, teeka.shastra_id)
        if shastra:
            if shastra.author_id:
                shastra_author = await session.get(Author, shastra.author_id)
            rows = await session.execute(
                select(Anuyoga)
                .join(ShastrasAnuyoga, ShastrasAnuyoga.anuyoga_id == Anuyoga.id)
                .where(ShastrasAnuyoga.shastra_id == shastra.id)
            )
            shastra_anuyogas = list(rows.scalars())

    teekakar: Author | None = None
    if teeka.teekakar_id:
        teekakar = await session.get(Author, teeka.teekakar_id)

    total_publications = await session.scalar(
        text("SELECT COUNT(*) FROM publications WHERE teeka_id = :tid").bindparams(tid=teeka.id)
    ) or 0

    return TeekaDetail(
        teeka=teeka,
        shastra=shastra,
        shastra_author=shastra_author,
        shastra_anuyogas=shastra_anuyogas,
        teekakar=teekakar,
        total_publications=int(total_publications),
    )


async def list_teekas(
    session: AsyncSession,
    limit: int,
    offset: int,
    shastra_id: uuid.UUID | None = None,
    teekakar_id: uuid.UUID | None = None,
) -> tuple[list[Teeka], int]:
    stmt = select(Teeka)
    cnt_stmt = select(func.count()).select_from(Teeka)
    if shastra_id is not None:
        stmt = stmt.where(Teeka.shastra_id == shastra_id)
        cnt_stmt = cnt_stmt.where(Teeka.shastra_id == shastra_id)
    if teekakar_id is not None:
        stmt = stmt.where(Teeka.teekakar_id == teekakar_id)
        cnt_stmt = cnt_stmt.where(Teeka.teekakar_id == teekakar_id)
    total = await session.scalar(cnt_stmt)
    rows = await session.execute(stmt.order_by(Teeka.natural_key).limit(limit).offset(offset))
    return list(rows.scalars()), int(total or 0)


async def list_by_shastra(
    session: AsyncSession, shastra_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Teeka], int]:
    return await list_teekas(session, limit, offset, shastra_id=shastra_id)


async def create_teeka(session: AsyncSession, data: dict[str, Any]) -> Teeka:
    teeka = Teeka(**data)
    session.add(teeka)
    await session.flush()
    await session.refresh(teeka)
    return teeka


async def update_teeka(session: AsyncSession, teeka: Teeka, data: dict[str, Any]) -> Teeka:
    for k, v in data.items():
        setattr(teeka, k, v)
    await session.flush()
    await session.refresh(teeka)
    return teeka
