from __future__ import annotations

import asyncio
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import (
    KALASH_BHAAVARTH_HINDI,
    KALASH_HINDI,
    KALASH_SANSKRIT,
)
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.kalashas import Kalash
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.teekas import Teeka


async def get_by_ident(session: AsyncSession, ident: str) -> Kalash | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Kalash, uid)
    except ValueError:
        result = await session.execute(
            select(Kalash).where(Kalash.natural_key == ident)
        )
        return result.scalar_one_or_none()


async def list_kalashas(
    session: AsyncSession,
    limit: int,
    offset: int,
    teeka_id: str | None = None,
) -> tuple[list[Kalash], int]:
    stmt = select(Kalash)
    cnt = select(func.count()).select_from(Kalash)

    if teeka_id is not None:
        try:
            tid = uuid.UUID(teeka_id)
            stmt = stmt.where(Kalash.teeka_id == tid)
            cnt = cnt.where(Kalash.teeka_id == tid)
        except ValueError:
            teeka_row = await session.execute(
                select(Teeka).where(Teeka.natural_key == teeka_id)
            )
            t = teeka_row.scalar_one_or_none()
            if t:
                stmt = stmt.where(Kalash.teeka_id == t.id)
                cnt = cnt.where(Kalash.teeka_id == t.id)
            else:
                return [], 0

    total = await session.scalar(cnt)
    rows = await session.execute(
        stmt.order_by(Kalash.natural_key).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


def _strip_id(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


async def get_detail(
    session: AsyncSession,
    mongo: AsyncIOMotorDatabase,
    kalash: Kalash,
    include: set[str],
) -> dict:
    teeka = await session.get(Teeka, kalash.teeka_id)
    shastra = None
    teekakar = None
    if teeka:
        shastra_task = session.get(Shastra, teeka.shastra_id)
        teekakar_task = session.get(Author, teeka.teekakar_id) if teeka.teekakar_id else _noop()
        shastra, teekakar = await asyncio.gather(shastra_task, teekakar_task)

    mongo_tasks = []
    mongo_keys = []

    if "sanskrit" in include:
        mongo_keys.append("sanskrit")
        mongo_tasks.append(
            mongo[KALASH_SANSKRIT].find_one({"natural_key": f"{kalash.natural_key}:sanskrit"})
        )
    if "hindi" in include:
        mongo_keys.append("hindi")
        mongo_tasks.append(
            mongo[KALASH_HINDI].find_one({"natural_key": f"{kalash.natural_key}:hindi"})
        )
    if "bhaavarth" in include:
        mongo_keys.append("bhaavarth")
        mongo_tasks.append(
            mongo[KALASH_BHAAVARTH_HINDI].find(
                {"kalash_natural_key": kalash.natural_key}
            ).to_list(None)
        )

    mongo_results = await asyncio.gather(*mongo_tasks) if mongo_tasks else []

    out: dict = {
        "kalash": kalash,
        "teeka": teeka,
        "shastra": shastra,
        "teekakar": teekakar,
        "bhaavarth": [],
    }
    for key, result in zip(mongo_keys, mongo_results):
        if key == "bhaavarth":
            out["bhaavarth"] = [_strip_id(d) for d in (result or [])]
        else:
            out[key] = _strip_id(result)

    return out


async def _noop():
    return None
