from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


def stable_id(natural_key: str) -> ObjectId:
    """Deterministic ObjectId from natural_key — same key always produces same _id."""
    h = hashlib.sha1(natural_key.encode("utf-8")).digest()[:12]
    return ObjectId(h)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _upsert(db: AsyncIOMotorDatabase, collection: str, natural_key: str, doc: dict) -> ObjectId:
    _id = stable_id(natural_key)
    payload = {**doc, "natural_key": natural_key, "updated_at": _now()}
    payload.pop("_id", None)
    await db[collection].update_one(
        {"_id": _id},
        {"$set": payload, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    return _id


async def upsert_gatha_prakrit(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "gatha_prakrit", natural_key, doc)


async def upsert_gatha_sanskrit(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "gatha_sanskrit", natural_key, doc)


async def upsert_gatha_hindi_chhand(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "gatha_hindi_chhand", natural_key, doc)


async def upsert_gatha_word_meanings(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "gatha_word_meanings", natural_key, doc)


async def upsert_teeka_gatha_mapping(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "teeka_gatha_mapping", natural_key, doc)


async def upsert_keyword_definition(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "keyword_definitions", natural_key, doc)


async def upsert_topic_extract(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "topic_extracts", natural_key, doc)


async def upsert_raw_html_snapshot(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "raw_html_snapshots", natural_key, doc)
