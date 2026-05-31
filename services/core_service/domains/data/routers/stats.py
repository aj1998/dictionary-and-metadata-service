from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_session
from ..schemas.stats import ActivityRow, EntityCounts
from ..services import stats as svc

router = APIRouter(prefix="/v1", tags=["stats", "activity"])

logger = logging.getLogger(__name__)

_CACHE_CONTROL = "public, max-age=60"


@router.get("/stats/counts", response_model=EntityCounts)
async def get_stats_counts(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> EntityCounts:
    payload = await svc.get_entity_counts(session)
    logger.info("stats.counts fetched", extra={"counts": payload})
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return EntityCounts(**payload)


@router.get("/activity/recent", response_model=list[ActivityRow])
async def get_activity_recent(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> list[ActivityRow]:
    payload = await svc.get_recent_activity(session)
    logger.info("activity.recent fetched", extra={"count": len(payload)})
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return [ActivityRow(**row) for row in payload]
