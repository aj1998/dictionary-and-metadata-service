from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.postgres.ingestion import IngestionRun
from jain_kb_common.db.postgres.keywords import Keyword
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.topics import Topic


async def get_entity_counts(session: AsyncSession) -> dict:
    shastras = int(await session.scalar(select(func.count()).select_from(Shastra)) or 0)
    gathas = int(await session.scalar(select(func.count()).select_from(Gatha)) or 0)
    topics = int(await session.scalar(select(func.count()).select_from(Topic)) or 0)
    keywords = int(await session.scalar(select(func.count()).select_from(Keyword)) or 0)
    return {
        "shastras": shastras,
        "gathas": gathas,
        "topics": topics,
        "keywords": keywords,
    }


async def get_recent_activity(session: AsyncSession, limit: int = 10) -> list[dict]:
    rows = await session.execute(
        select(IngestionRun)
        .order_by(desc(IngestionRun.finished_at), desc(IngestionRun.started_at), desc(IngestionRun.created_at))
        .limit(limit)
    )

    items: list[dict] = []
    for run in rows.scalars():
        run_at = _run_timestamp(run.finished_at, run.started_at, run.created_at)
        entities_touched = _entities_touched(run.stats)
        items.append(
            {
                "id": str(run.id),
                "run_at": run_at,
                "source": str(run.source.value),
                "entities_touched": entities_touched,
            }
        )
    return items


def _run_timestamp(*times: object) -> str:
    for value in times:
        if isinstance(value, datetime):
            return value.isoformat()
    return datetime.utcnow().isoformat() + "Z"


def _entities_touched(stats: object) -> int:
    if not isinstance(stats, dict):
        return 0
    value = stats.get("entities_touched")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
