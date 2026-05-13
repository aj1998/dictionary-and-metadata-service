from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_session, require_admin
from ..schemas.books import BookCreate, BookListResponse, BookResponse, BookUpdate
from ..schemas.common import AnuyogaSummary, AuthorSummary, Pagination, ShastraSummary
from ..services import books as svc

router = APIRouter(prefix="/v1", tags=["books"])


def _limit_offset(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset


async def _build_book_response(session, book) -> BookResponse:  # type: ignore[no-untyped-def]
    shastra = await svc.get_shastra_for(session, book)
    shastra_summary = None
    if shastra:
        shastra_author = await svc.get_shastra_author(session, shastra)
        shastra_anuyogas = await svc.get_shastra_anuyogas(session, shastra)
        shastra_summary = ShastraSummary(
            id=shastra.id,
            natural_key=shastra.natural_key,
            title=shastra.title,
            author=AuthorSummary(
                id=shastra_author.id,
                natural_key=shastra_author.natural_key,
                display_name=shastra_author.display_name,
                kind=shastra_author.kind,
            ) if shastra_author else None,
            anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in shastra_anuyogas],
        )
    book_anuyogas = await svc.get_anuyogas_for(session, book)
    return BookResponse(
        id=book.id,
        natural_key=book.natural_key,
        title=book.title,
        shastra=shastra_summary,
        anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in book_anuyogas],
        publisher=book.publisher,
        translator=book.translator,
        editor=book.editor,
        public_url=book.public_url,
        publisher_url=book.publisher_url,
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


@router.get("/books", response_model=BookListResponse)
async def list_books(
    shastra_id: uuid.UUID | None = None,
    anuyoga: str | None = None,
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> BookListResponse:
    limit, offset = lo
    books, total = await svc.list_books(session, limit, offset, shastra_id, anuyoga)
    items = [await _build_book_response(session, b) for b in books]
    return BookListResponse(
        items=items,
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.get("/books/{ident}", response_model=BookResponse)
async def get_book(
    ident: str,
    session: AsyncSession = Depends(get_session),
) -> BookResponse:
    book = await svc.get_by_ident(session, ident)
    if book is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Book '{ident}' not found"})
    return await _build_book_response(session, book)


@router.post("/admin/books", response_model=BookResponse, status_code=201)
async def create_book(
    body: BookCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> BookResponse:
    try:
        book = await svc.create_book(
            session,
            {
                "natural_key": body.natural_key,
                "title": [lt.model_dump() for lt in body.title],
                "shastra_id": body.shastra_id,
                "publisher": [lt.model_dump() for lt in body.publisher] if body.publisher else None,
                "translator": [lt.model_dump() for lt in body.translator] if body.translator else None,
                "editor": [lt.model_dump() for lt in body.editor] if body.editor else None,
                "public_url": body.public_url,
                "publisher_url": body.publisher_url,
            },
            body.anuyoga_ids,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, detail={"code": "conflict", "message": "natural_key already exists"})
    return await _build_book_response(session, book)


@router.patch("/admin/books/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: str,
    body: BookUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> BookResponse:
    book = await svc.get_by_ident(session, book_id)
    if book is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Book not found"})
    patch: dict = {}
    if body.title is not None:
        patch["title"] = [lt.model_dump() for lt in body.title]
    if body.shastra_id is not None:
        patch["shastra_id"] = body.shastra_id
    if body.publisher is not None:
        patch["publisher"] = [lt.model_dump() for lt in body.publisher]
    if body.translator is not None:
        patch["translator"] = [lt.model_dump() for lt in body.translator]
    if body.editor is not None:
        patch["editor"] = [lt.model_dump() for lt in body.editor]
    if body.public_url is not None:
        patch["public_url"] = body.public_url
    if body.publisher_url is not None:
        patch["publisher_url"] = body.publisher_url
    book = await svc.update_book(session, book, patch, body.anuyoga_ids)
    await session.commit()
    return await _build_book_response(session, book)
