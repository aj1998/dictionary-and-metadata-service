from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.hydration.tables import (
    TableResponse,
    TableSummary,
    hydrate_table_full,
    hydrate_tables_for_parent,
)

logger = logging.getLogger(__name__)


async def get_table_response(
    session: AsyncSession,
    mongo: AsyncIOMotorDatabase,
    *,
    natural_key: str,
) -> TableResponse | None:
    return await hydrate_table_full(session, mongo, natural_key=natural_key)


async def list_table_summaries(
    session: AsyncSession,
    mongo: AsyncIOMotorDatabase,
    *,
    parent_natural_key: str,
) -> list[TableSummary]:
    return await hydrate_tables_for_parent(session, mongo, parent_natural_key=parent_natural_key)
