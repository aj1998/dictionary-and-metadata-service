from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from jain_kb_common.db.mongo.collections import EXTRACT_MATCHES


async def get_by_natural_key(mongo: AsyncIOMotorDatabase, natural_key: str) -> dict | None:
    doc = await mongo[EXTRACT_MATCHES].find_one({"natural_key": natural_key})
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc
