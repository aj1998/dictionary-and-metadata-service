from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.anuyogas import Anuyoga

from ..deps import get_session
from ..schemas.anuyogas import AnuyogaResponse

router = APIRouter(prefix="/v1", tags=["anuyogas"])


@router.get("/anuyogas", response_model=list[AnuyogaResponse])
async def list_anuyogas(
    session: AsyncSession = Depends(get_session),
) -> list[AnuyogaResponse]:
    rows = await session.execute(select(Anuyoga).order_by(Anuyoga.kind))
    return [AnuyogaResponse.model_validate(a, from_attributes=True) for a in rows.scalars()]
