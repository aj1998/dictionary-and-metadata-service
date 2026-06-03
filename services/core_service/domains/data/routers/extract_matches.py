from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from ....deps import get_mongo_db
from ..services import extract_matches as svc

router = APIRouter(prefix="/v1", tags=["extract-matches"])

_CACHE_CONTROL = "public, max-age=60"


@router.get("/extract-matches/{natural_key:path}")
async def get_extract_match(
    natural_key: str,
    response: Response,
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> dict:
    doc = await svc.get_by_natural_key(mongo, natural_key)
    if doc is None:
        raise HTTPException(
            404,
            detail={"code": "not_found", "message": f"Extract match '{natural_key}' not found"},
        )
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return doc
