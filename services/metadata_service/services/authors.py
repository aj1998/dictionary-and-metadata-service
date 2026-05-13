from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.authors import Author


async def get_by_ident(session: AsyncSession, ident: str) -> Author | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Author, uid)
    except ValueError:
        result = await session.execute(select(Author).where(Author.natural_key == ident))
        return result.scalar_one_or_none()


async def list_authors(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[Author], int]:
    total = await session.scalar(select(func.count()).select_from(Author))
    rows = await session.execute(select(Author).order_by(Author.natural_key).limit(limit).offset(offset))
    return list(rows.scalars()), int(total or 0)


async def create_author(session: AsyncSession, data: dict[str, Any]) -> Author:
    author = Author(**data)
    session.add(author)
    await session.flush()
    await session.refresh(author)
    return author


async def update_author(session: AsyncSession, author: Author, data: dict[str, Any]) -> Author:
    for k, v in data.items():
        setattr(author, k, v)
    await session.flush()
    await session.refresh(author)
    return author
