from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.authors import Author

logger = logging.getLogger(__name__)

_FUZZY_MIN_SIMILARITY = 0.25
_FUZZY_HARD_CAP = 50


async def get_by_ident(session: AsyncSession, ident: str) -> Author | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Author, uid)
    except ValueError:
        result = await session.execute(select(Author).where(Author.natural_key == ident))
        return result.scalar_one_or_none()


async def list_authors(
    session: AsyncSession, limit: int, offset: int, q: str | None = None
) -> tuple[list[Author], int]:
    stmt = select(Author)
    cnt_stmt = select(func.count()).select_from(Author)
    if q is not None:
        like_filter = text("natural_key ILIKE :pattern OR display_name::text ILIKE :pattern").bindparams(
            pattern=f"%{q}%"
        )
        stmt = stmt.where(like_filter)
        cnt_stmt = cnt_stmt.where(like_filter)
    total = await session.scalar(cnt_stmt)
    rows = await session.execute(stmt.order_by(Author.natural_key).limit(limit).offset(offset))
    return list(rows.scalars()), int(total or 0)


async def fuzzy_search_authors(
    session: AsyncSession,
    q: str,
    limit: int,
    min_similarity: float = _FUZZY_MIN_SIMILARITY,
) -> list[tuple[Author, float]]:
    """pg_trgm similarity search over natural_key and display_name JSONB text."""
    capped = min(limit, _FUZZY_HARD_CAP)
    sql = text("""
        WITH ranked AS (
            SELECT
                id,
                GREATEST(
                    similarity(natural_key, :q),
                    similarity(display_name::text, :q)
                ) AS sim
            FROM authors
        )
        SELECT id::text AS id, sim FROM ranked
        WHERE sim >= :min_sim
        ORDER BY sim DESC
        LIMIT :limit
    """)
    rows = list(await session.execute(sql, {"q": q, "min_sim": min_similarity, "limit": capped}))
    logger.debug("fuzzy_search_authors q=%r min_sim=%.2f → %d rows", q, min_similarity, len(rows))
    if not rows:
        return []
    id_to_sim = {uuid.UUID(row.id): float(row.sim) for row in rows}
    id_order = [uuid.UUID(row.id) for row in rows]
    author_rows = await session.execute(select(Author).where(Author.id.in_(id_order)))
    author_map = {a.id: a for a in author_rows.scalars()}
    return [(author_map[aid], id_to_sim[aid]) for aid in id_order if aid in author_map]


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
