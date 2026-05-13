from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.anuyogas import Anuyoga
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.shastras import Shastra, ShastrasAnuyoga


class ShastraDetail(TypedDict):
    shastra: Shastra
    author: Author | None
    anuyogas: list[Anuyoga]
    total_gathas: int
    total_teekas: int


async def get_by_ident(session: AsyncSession, ident: str) -> Shastra | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Shastra, uid)
    except ValueError:
        result = await session.execute(select(Shastra).where(Shastra.natural_key == ident))
        return result.scalar_one_or_none()


async def get_detail(session: AsyncSession, shastra: Shastra) -> ShastraDetail:
    author: Author | None = None
    if shastra.author_id:
        author = await session.get(Author, shastra.author_id)

    anuyoga_rows = await session.execute(
        select(Anuyoga)
        .join(ShastrasAnuyoga, ShastrasAnuyoga.anuyoga_id == Anuyoga.id)
        .where(ShastrasAnuyoga.shastra_id == shastra.id)
    )
    anuyogas = list(anuyoga_rows.scalars())

    total_gathas = await session.scalar(
        text("SELECT COUNT(*) FROM gathas WHERE shastra_id = :sid").bindparams(sid=shastra.id)
    ) or 0
    total_teekas = await session.scalar(
        text("SELECT COUNT(*) FROM teekas WHERE shastra_id = :sid").bindparams(sid=shastra.id)
    ) or 0

    return ShastraDetail(
        shastra=shastra,
        author=author,
        anuyogas=anuyogas,
        total_gathas=int(total_gathas),
        total_teekas=int(total_teekas),
    )


async def list_shastras(
    session: AsyncSession,
    limit: int,
    offset: int,
    author_id: uuid.UUID | None = None,
    anuyoga: str | None = None,
    q: str | None = None,
) -> tuple[list[Shastra], int]:
    stmt = select(Shastra)
    cnt_stmt = select(func.count()).select_from(Shastra)

    if author_id is not None:
        stmt = stmt.where(Shastra.author_id == author_id)
        cnt_stmt = cnt_stmt.where(Shastra.author_id == author_id)

    if anuyoga is not None:
        anuyoga_sub = (
            select(ShastrasAnuyoga.shastra_id)
            .join(Anuyoga, Anuyoga.id == ShastrasAnuyoga.anuyoga_id)
            .where(Anuyoga.kind == anuyoga)
        )
        stmt = stmt.where(Shastra.id.in_(anuyoga_sub))
        cnt_stmt = cnt_stmt.where(Shastra.id.in_(anuyoga_sub))

    if q is not None:
        trgm = text("shastra_title_trgm(:q, title)").bindparams(q=q)
        # Use a safe jsonb cast for pg_trgm similarity on JSON text
        # Cast title JSONB to text and use similarity
        like_filter = text(
            "title::text ILIKE :pattern"
        ).bindparams(pattern=f"%{q}%")
        stmt = stmt.where(like_filter)
        cnt_stmt = cnt_stmt.where(like_filter)

    total = await session.scalar(cnt_stmt)
    rows = await session.execute(stmt.order_by(Shastra.natural_key).limit(limit).offset(offset))
    return list(rows.scalars()), int(total or 0)


async def get_author_for(session: AsyncSession, shastra: Shastra) -> Author | None:
    if not shastra.author_id:
        return None
    return await session.get(Author, shastra.author_id)


async def get_anuyogas_for(session: AsyncSession, shastra: Shastra) -> list[Anuyoga]:
    rows = await session.execute(
        select(Anuyoga)
        .join(ShastrasAnuyoga, ShastrasAnuyoga.anuyoga_id == Anuyoga.id)
        .where(ShastrasAnuyoga.shastra_id == shastra.id)
    )
    return list(rows.scalars())


async def create_shastra(
    session: AsyncSession, data: dict[str, Any], anuyoga_ids: list[uuid.UUID]
) -> Shastra:
    shastra = Shastra(**data)
    session.add(shastra)
    await session.flush()
    for aid in anuyoga_ids:
        session.add(ShastrasAnuyoga(shastra_id=shastra.id, anuyoga_id=aid))
    await session.flush()
    await session.refresh(shastra)
    return shastra


async def update_shastra(
    session: AsyncSession,
    shastra: Shastra,
    data: dict[str, Any],
    anuyoga_ids: list[uuid.UUID] | None,
) -> Shastra:
    for k, v in data.items():
        setattr(shastra, k, v)
    if anuyoga_ids is not None:
        await session.execute(
            ShastrasAnuyoga.__table__.delete().where(  # type: ignore[attr-defined]
                ShastrasAnuyoga.shastra_id == shastra.id
            )
        )
        for aid in anuyoga_ids:
            session.add(ShastrasAnuyoga(shastra_id=shastra.id, anuyoga_id=aid))
    await session.flush()
    await session.refresh(shastra)
    return shastra
