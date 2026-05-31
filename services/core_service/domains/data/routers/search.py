from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_session
from ..services import search as svc

router = APIRouter(prefix="/v1", tags=["search"])

_CACHE_CONTROL = "public, max-age=60"
_VALID_TYPES = {"keyword", "topic", "gatha", "kalasha"}


@router.get("/search")
async def search(
    response: Response,
    q: str = Query(..., min_length=2),
    types: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if types is not None:
        type_set = {t.strip() for t in types.split(",") if t.strip()}
        invalid = type_set - _VALID_TYPES
        if invalid:
            raise HTTPException(422, detail={"code": "validation_error", "message": f"Invalid types: {invalid}"})
    else:
        type_set = set(_VALID_TYPES)

    items = await svc.search(session, q, type_set, limit)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return {"query": q, "items": items}
