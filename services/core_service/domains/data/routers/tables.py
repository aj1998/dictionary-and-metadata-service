from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_mongo_db, get_session
from ..schemas.tables import TableResponse, TableSummary
from ..services import tables as svc

router = APIRouter(prefix="/v1", tags=["tables"])
logger = logging.getLogger(__name__)

_CACHE_CONTROL = "public, max-age=60"


@router.get("/tables/{natural_key}", response_model=TableResponse)
async def get_table(
    natural_key: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> TableResponse:
    table = await svc.get_table_response(session, mongo, natural_key=natural_key)
    if table is None:
        raise HTTPException(
            404, detail={"code": "not_found", "message": f"Table '{natural_key}' not found"}
        )
    logger.info("GET /v1/tables/%s → 200", natural_key)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return table


@router.get("/tables", response_model=list[TableSummary])
async def list_tables_for_parent(
    response: Response,
    parent_natural_key: str = Query(...),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> list[TableSummary]:
    summaries = await svc.list_table_summaries(
        session, mongo, parent_natural_key=parent_natural_key
    )
    logger.info(
        "GET /v1/tables?parent_natural_key=%s → %d items",
        parent_natural_key, len(summaries),
    )
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return summaries
