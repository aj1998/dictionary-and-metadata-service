from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_mongo_db, get_session
from ..schemas.common import Pagination, ShastraRef
from ..schemas.gathas import GathaDetail, GathaListResponse, GathaSummary
from ..services import gathas as svc

router = APIRouter(prefix="/v1", tags=["gathas"])

_CACHE_CONTROL = "public, max-age=60"

_ALL_INCLUDE = {"teeka_mapping", "teeka_sanskrit", "teeka_hindi", "teeka_bhaavarth", "kalashas"}


def _parse_include(include: str | None) -> set[str]:
    if not include:
        return set()
    return {v.strip() for v in include.split(",") if v.strip() in _ALL_INCLUDE}


@router.get("/gathas", response_model=GathaListResponse)
async def list_gathas(
    response: Response,
    shastra_id: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> GathaListResponse:
    items, total = await svc.list_gathas(session, limit, offset, shastra_id=shastra_id, q=q)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    from jain_kb_common.db.postgres.shastras import Shastra
    result = []
    shastra_cache: dict = {}
    for g in items:
        if g.shastra_id not in shastra_cache:
            s = await session.get(Shastra, g.shastra_id)
            shastra_cache[g.shastra_id] = s
        s = shastra_cache[g.shastra_id]
        if s is None:
            continue
        result.append(GathaSummary(
            id=g.id,
            natural_key=g.natural_key,
            gatha_number=g.gatha_number,
            shastra=ShastraRef(natural_key=s.natural_key, title=s.title),
            adhikaar=g.adhikaar,
            heading=g.heading,
        ))

    return GathaListResponse(
        pagination=Pagination(total=total, limit=limit, offset=offset),
        items=result,
    )


@router.get("/gathas/{ident}")
async def get_gatha(
    ident: str,
    response: Response,
    include: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> dict:
    gatha = await svc.get_by_ident(session, ident)
    if gatha is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Gatha '{ident}' not found"})

    inc = _parse_include(include)
    detail = await svc.get_detail(session, mongo, gatha, inc)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    shastra = detail["shastra"]
    out: dict = {
        "id": gatha.id,
        "natural_key": gatha.natural_key,
        "gatha_number": gatha.gatha_number,
        "shastra": ShastraRef(natural_key=shastra.natural_key, title=shastra.title).model_dump() if shastra else {"natural_key": "", "title": []},
        "adhikaar": gatha.adhikaar or [],
        "heading": gatha.heading or [],
        "prakrit": detail.get("prakrit"),
        "sanskrit": detail.get("sanskrit"),
        "hindi_chhand": detail.get("hindi_chhand", []),
        "word_meanings": detail.get("word_meanings"),
    }

    if "teeka_mapping" in inc:
        out["teeka_mapping"] = detail.get("teeka_mapping", [])
    if "teeka_sanskrit" in inc:
        out["teeka_sanskrit"] = detail.get("teeka_sanskrit", [])
    if "teeka_hindi" in inc:
        out["teeka_hindi"] = detail.get("teeka_hindi", [])
    if "teeka_bhaavarth" in inc:
        out["teeka_bhaavarth"] = detail.get("teeka_bhaavarth", [])
    if "kalashas" in inc:
        out["kalashas"] = detail.get("kalashas", [])

    return out
