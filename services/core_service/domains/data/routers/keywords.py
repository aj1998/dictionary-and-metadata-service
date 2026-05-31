from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_mongo_db, get_session, require_admin
from ..schemas.keywords import (
    AliasSummary,
    KeywordDetail,
    KeywordListResponse,
    KeywordSummary,
    KeywordUpdate,
    LetterCount,
)
from ..schemas.common import Pagination
from ..services import keywords as svc

router = APIRouter(prefix="/v1", tags=["keywords"])

_CACHE_CONTROL = "public, max-age=60"

# In-process letter cache: (data, expires_at)
_letter_cache: tuple[list[dict], float] | None = None
_LETTER_TTL = 3600.0


@router.get("/keywords/letters", response_model=list[LetterCount])
async def get_letter_index(
    response: Response,
    session: AsyncSession = Depends(get_session),
    request: Request = None,  # type: ignore[assignment]
) -> list[LetterCount]:
    global _letter_cache
    now = time.monotonic()
    if _letter_cache and _letter_cache[1] > now:
        data = _letter_cache[0]
    else:
        data = await svc.get_letter_counts(session)
        _letter_cache = (data, now + _LETTER_TTL)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return [LetterCount(**item) for item in data]


@router.get("/keywords", response_model=KeywordListResponse)
async def list_keywords(
    response: Response,
    q: str | None = Query(None),
    letter: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> KeywordListResponse:
    items, total = await svc.list_keywords(session, limit, offset, q=q, letter=letter)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return KeywordListResponse(
        pagination=Pagination(total=total, limit=limit, offset=offset),
        items=[
            KeywordSummary(
                id=kw.id,
                natural_key=kw.natural_key,
                display_text=kw.display_text,
                source_url=kw.source_url,
            )
            for kw in items
        ],
    )


@router.get("/keywords/{ident}", response_model=KeywordDetail)
async def get_keyword(
    ident: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> KeywordDetail:
    kw = await svc.get_by_ident(session, ident)
    if kw is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Keyword '{ident}' not found"})
    detail = await svc.get_detail(session, mongo, kw)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return KeywordDetail(
        id=kw.id,
        natural_key=kw.natural_key,
        display_text=kw.display_text,
        source_url=kw.source_url,
        aliases=[
            AliasSummary(id=a.id, alias_text=a.alias_text, source=a.source)
            for a in detail["aliases"]
        ],
        definition=detail["definition"],
    )


@router.patch("/admin/keywords/{ident}", response_model=KeywordDetail)
async def update_keyword(
    ident: str,
    body: KeywordUpdate,
    response: Response,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
    _: None = Depends(require_admin),
) -> KeywordDetail:
    kw = await svc.get_by_ident(session, ident)
    if kw is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Keyword '{ident}' not found"})

    patch: dict = {}
    if body.display_text is not None:
        patch["display_text"] = body.display_text
    if body.source_url is not None:
        patch["source_url"] = body.source_url

    if patch:
        kw = await svc.update_keyword(session, kw, patch)
        await session.commit()
        # bust letter cache
        global _letter_cache
        _letter_cache = None

    detail = await svc.get_detail(session, mongo, kw)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return KeywordDetail(
        id=kw.id,
        natural_key=kw.natural_key,
        display_text=kw.display_text,
        source_url=kw.source_url,
        aliases=[
            AliasSummary(id=a.id, alias_text=a.alias_text, source=a.source)
            for a in detail["aliases"]
        ],
        definition=detail["definition"],
    )
