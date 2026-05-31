from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_session
from ..schemas.common import AuthorSummary, ShastraRef
from ..services import browse as svc

router = APIRouter(prefix="/v1/browse", tags=["browse"])

_CACHE_CONTROL = "public, max-age=60"
_SHASTRAS_TTL = 3600.0

_shastras_cache: tuple[list[dict], float] | None = None


def _bust_shastras_cache() -> None:
    global _shastras_cache
    _shastras_cache = None


@router.get("/shastras")
async def list_shastras(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    global _shastras_cache
    now = time.monotonic()
    if _shastras_cache and _shastras_cache[1] > now:
        data = _shastras_cache[0]
    else:
        raw = await svc.list_shastras(session)
        data = []
        for item in raw:
            s = item["shastra"]
            author = item["author"]
            data.append({
                "natural_key": s.natural_key,
                "title": s.title,
                "author": {
                    "natural_key": author.natural_key,
                    "display_name": author.display_name,
                } if author else None,
                "total_gathas": item["total_gathas"],
                "total_teekas": item["total_teekas"],
            })
        _shastras_cache = (data, now + _SHASTRAS_TTL)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return data


@router.get("/shastras/{nk}/index")
async def get_shastra_index(
    nk: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await svc.get_shastra_index(session, nk)
    if result is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Shastra '{nk}' not found"})
    response.headers["Cache-Control"] = _CACHE_CONTROL
    s = result["shastra"]
    adhikaars = []
    for adh in result["adhikaars"]:
        adhikaars.append({
            "adhikaar": adh["adhikaar"],
            "gathas": [
                {
                    "natural_key": g["natural_key"],
                    "gatha_number": g["gatha_number"],
                    "heading": g["heading"],
                }
                for g in adh["gathas"]
            ],
        })
    return {
        "shastra": {"natural_key": s.natural_key, "title": s.title},
        "adhikaars": adhikaars,
    }


@router.get("/teekas/{nk}/index")
async def get_teeka_index(
    nk: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await svc.get_teeka_index(session, nk)
    if result is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Teeka '{nk}' not found"})
    response.headers["Cache-Control"] = _CACHE_CONTROL
    t = result["teeka"]
    s = result["shastra"]
    teekakar = result["teekakar"]
    return {
        "teeka": {
            "natural_key": t.natural_key,
            "teekakar": {"display_name": teekakar.display_name} if teekakar else None,
            "shastra": {"natural_key": s.natural_key, "title": s.title} if s else None,
        },
        "entries": result["entries"],
    }
