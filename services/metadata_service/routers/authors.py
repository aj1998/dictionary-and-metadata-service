from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_session, require_admin
from ..schemas.authors import AuthorCreate, AuthorListResponse, AuthorResponse, AuthorUpdate
from ..schemas.common import Pagination
from ..services import authors as svc

router = APIRouter(prefix="/v1", tags=["authors"])


def _limit_offset(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset


@router.get("/authors", response_model=AuthorListResponse)
async def list_authors(
    q: str | None = None,
    fuzzy: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> AuthorListResponse:
    limit, offset = lo
    if fuzzy and q is not None:
        results = await svc.fuzzy_search_authors(session, q, limit)
        items = [
            AuthorResponse.model_validate(a, from_attributes=True).model_copy(update={"similarity": sim})
            for a, sim in results
        ]
        return AuthorListResponse(
            items=items,
            pagination=Pagination(total=len(items), limit=min(limit, 50), offset=0),
        )
    authors, total = await svc.list_authors(session, limit, offset, q)
    return AuthorListResponse(
        items=[AuthorResponse.model_validate(a, from_attributes=True) for a in authors],
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.get("/authors/{ident}", response_model=AuthorResponse)
async def get_author(
    ident: str,
    session: AsyncSession = Depends(get_session),
) -> AuthorResponse:
    author = await svc.get_by_ident(session, ident)
    if author is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Author '{ident}' not found"})
    return AuthorResponse.model_validate(author, from_attributes=True)


@router.post("/admin/authors", response_model=AuthorResponse, status_code=201)
async def create_author(
    body: AuthorCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> AuthorResponse:
    try:
        author = await svc.create_author(
            session,
            {
                "natural_key": body.natural_key,
                "display_name": [lt.model_dump() for lt in body.display_name],
                "kind": body.kind,
                "bio": [lt.model_dump() for lt in body.bio] if body.bio else None,
            },
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, detail={"code": "conflict", "message": "natural_key already exists"})
    return AuthorResponse.model_validate(author, from_attributes=True)


@router.patch("/admin/authors/{author_id}", response_model=AuthorResponse)
async def update_author(
    author_id: str,
    body: AuthorUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> AuthorResponse:
    author = await svc.get_by_ident(session, author_id)
    if author is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Author not found"})
    patch: dict = {}
    if body.display_name is not None:
        patch["display_name"] = [lt.model_dump() for lt in body.display_name]
    if body.kind is not None:
        patch["kind"] = body.kind
    if body.bio is not None:
        patch["bio"] = [lt.model_dump() for lt in body.bio]
    author = await svc.update_author(session, author, patch)
    await session.commit()
    return AuthorResponse.model_validate(author, from_attributes=True)
