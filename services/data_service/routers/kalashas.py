from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_mongo_db, get_session
from ..schemas.common import AuthorSummary, Pagination, ShastraRef
from ..schemas.kalashas import (
    KalashDetail,
    KalashListResponse,
    KalashSummary,
    KalashWMEntryResponse,
    KalashWordMeaningsResponse,
    TeekaInfo,
    TeekaInfoDetail,
)
from ..services import kalashas as svc

router = APIRouter(prefix="/v1", tags=["kalashas"])

_CACHE_CONTROL = "public, max-age=60"

_ALL_INCLUDE = {"sanskrit", "hindi", "bhaavarth"}
_DEFAULT_INCLUDE = _ALL_INCLUDE


def _parse_include(include: str | None) -> set[str]:
    if include is None:
        return set(_DEFAULT_INCLUDE)
    return {v.strip() for v in include.split(",") if v.strip() in _ALL_INCLUDE}


@router.get("/kalashas", response_model=KalashListResponse)
async def list_kalashas(
    response: Response,
    teeka_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> KalashListResponse:
    items, total = await svc.list_kalashas(session, limit, offset, teeka_id=teeka_id)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    from jain_kb_common.db.postgres.teekas import Teeka
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.authors import Author

    result = []
    teeka_cache: dict = {}
    for k in items:
        if k.teeka_id not in teeka_cache:
            t = await session.get(Teeka, k.teeka_id)
            if t:
                s = await session.get(Shastra, t.shastra_id)
                tk_author = await session.get(Author, t.teekakar_id) if t.teekakar_id else None
                teeka_cache[k.teeka_id] = (t, s, tk_author)
            else:
                teeka_cache[k.teeka_id] = (None, None, None)
        t, s, tk_author = teeka_cache[k.teeka_id]
        if t is None or s is None:
            continue
        teeka_info = TeekaInfo(
            natural_key=t.natural_key,
            shastra=ShastraRef(natural_key=s.natural_key, title=s.title),
            teekakar=AuthorSummary(
                natural_key=tk_author.natural_key,
                display_name=tk_author.display_name,
            ) if tk_author else None,
        )
        result.append(KalashSummary(
            id=k.id,
            natural_key=k.natural_key,
            kalash_number=k.kalash_number,
            teeka=teeka_info,
        ))

    return KalashListResponse(
        pagination=Pagination(total=total, limit=limit, offset=offset),
        items=result,
    )


@router.get("/kalashas/{ident}/word_meanings", response_model=KalashWordMeaningsResponse)
async def get_kalash_word_meanings(
    ident: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> KalashWordMeaningsResponse:
    result = await svc.get_word_meanings(session, mongo, ident)
    if result is None:
        raise HTTPException(
            404,
            detail={"code": "not_found", "message": f"No word meanings found for kalash {ident}"},
        )
    kalash = result["kalash"]
    doc = result["doc"]
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return KalashWordMeaningsResponse(
        kalash_id=kalash.id,
        kalash_natural_key=doc.get("kalash_natural_key", kalash.natural_key),
        teeka_natural_key=doc.get("teeka_natural_key", ""),
        kalash_number=doc.get("kalash_number", kalash.kalash_number),
        entries=[
            KalashWMEntryResponse(
                source_word=e["source_word"],
                meaning=e["meaning"],
                position=e["position"],
            )
            for e in doc.get("entries", [])
        ],
    )


@router.get("/kalashas/{ident}", response_model=KalashDetail)
async def get_kalash(
    ident: str,
    response: Response,
    include: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> KalashDetail:
    kalash = await svc.get_by_ident(session, ident)
    if kalash is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Kalash '{ident}' not found"})

    inc = _parse_include(include)
    detail = await svc.get_detail(session, mongo, kalash, inc)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    teeka = detail["teeka"]
    shastra = detail["shastra"]
    teekakar = detail["teekakar"]

    teeka_info = TeekaInfoDetail(
        id=teeka.id,
        natural_key=teeka.natural_key,
        shastra=ShastraRef(natural_key=shastra.natural_key, title=shastra.title) if shastra else ShastraRef(natural_key="", title=[]),
        teekakar=AuthorSummary(
            natural_key=teekakar.natural_key,
            display_name=teekakar.display_name,
        ) if teekakar else None,
    )

    return KalashDetail(
        id=kalash.id,
        natural_key=kalash.natural_key,
        kalash_number=kalash.kalash_number,
        teeka=teeka_info,
        sanskrit=detail.get("sanskrit"),
        hindi=detail.get("hindi"),
        bhaavarth=detail.get("bhaavarth", []),
    )
