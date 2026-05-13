from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.anuyogas import Anuyoga
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.books import Book, BookAnuyoga
from jain_kb_common.db.postgres.shastras import Shastra, ShastrasAnuyoga


async def get_by_ident(session: AsyncSession, ident: str) -> Book | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Book, uid)
    except ValueError:
        result = await session.execute(select(Book).where(Book.natural_key == ident))
        return result.scalar_one_or_none()


async def get_anuyogas_for(session: AsyncSession, book: Book) -> list[Anuyoga]:
    rows = await session.execute(
        select(Anuyoga)
        .join(BookAnuyoga, BookAnuyoga.anuyoga_id == Anuyoga.id)
        .where(BookAnuyoga.book_id == book.id)
    )
    return list(rows.scalars())


async def get_shastra_for(session: AsyncSession, book: Book) -> Shastra | None:
    if not book.shastra_id:
        return None
    return await session.get(Shastra, book.shastra_id)


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


async def list_books(
    session: AsyncSession,
    limit: int,
    offset: int,
    shastra_id: uuid.UUID | None = None,
    anuyoga: str | None = None,
) -> tuple[list[Book], int]:
    stmt = select(Book)
    cnt_stmt = select(func.count()).select_from(Book)
    if shastra_id is not None:
        stmt = stmt.where(Book.shastra_id == shastra_id)
        cnt_stmt = cnt_stmt.where(Book.shastra_id == shastra_id)
    if anuyoga is not None:
        anuyoga_sub = (
            select(BookAnuyoga.book_id)
            .join(Anuyoga, Anuyoga.id == BookAnuyoga.anuyoga_id)
            .where(Anuyoga.kind == anuyoga)
        )
        stmt = stmt.where(Book.id.in_(anuyoga_sub))
        cnt_stmt = cnt_stmt.where(Book.id.in_(anuyoga_sub))
    total = await session.scalar(cnt_stmt)
    rows = await session.execute(stmt.order_by(Book.natural_key).limit(limit).offset(offset))
    return list(rows.scalars()), int(total or 0)


async def create_book(
    session: AsyncSession, data: dict[str, Any], anuyoga_ids: list[uuid.UUID]
) -> Book:
    book = Book(**data)
    session.add(book)
    await session.flush()
    for aid in anuyoga_ids:
        session.add(BookAnuyoga(book_id=book.id, anuyoga_id=aid))
    await session.flush()
    await session.refresh(book)
    return book


async def update_book(
    session: AsyncSession,
    book: Book,
    data: dict[str, Any],
    anuyoga_ids: list[uuid.UUID] | None,
) -> Book:
    for k, v in data.items():
        setattr(book, k, v)
    if anuyoga_ids is not None:
        await session.execute(
            BookAnuyoga.__table__.delete().where(  # type: ignore[attr-defined]
                BookAnuyoga.book_id == book.id
            )
        )
        for aid in anuyoga_ids:
            session.add(BookAnuyoga(book_id=book.id, anuyoga_id=aid))
    await session.flush()
    await session.refresh(book)
    return book
