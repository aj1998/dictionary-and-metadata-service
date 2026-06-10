from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from .collections import (
    EXTRACT_MATCHES,
    GATHA_TEEKA_BHAAVARTH_SHORTFONT,
    KALASH_BHAAVARTH_SHORTFONT,
    KALASH_WORD_MEANINGS,
    TABLES,
)


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


async def upsert_gatha_word_meanings(
    db: AsyncIOMotorDatabase,
    *,
    natural_key: str,
    doc: dict,
    full_anyavaarth: str | None = None,
) -> ObjectId:
    if full_anyavaarth is not None:
        doc = {**doc, "full_anyavaarth": full_anyavaarth}
    return await _upsert(db, "gatha_word_meanings", natural_key, doc)


async def upsert_teeka_gatha_mapping(
    db: AsyncIOMotorDatabase,
    *,
    natural_key: str,
    doc: dict,
    full_anyavaarth: str | None = None,
    is_related: list[str] | None = None,
) -> ObjectId:
    if full_anyavaarth is not None:
        doc = {**doc, "full_anyavaarth": full_anyavaarth}
    if is_related is not None:
        doc = {**doc, "is_related": is_related}
    return await _upsert(db, "teeka_gatha_mapping", natural_key, doc)


async def upsert_keyword_definition(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "keyword_definitions", natural_key, doc)


async def upsert_topic_extract(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "topic_extracts", natural_key, doc)


async def upsert_raw_html_snapshot(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "raw_html_snapshots", natural_key, doc)


async def upsert_gatha_teeka_sanskrit(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "gatha_teeka_sanskrit", natural_key, doc)


async def upsert_gatha_teeka_hindi(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "gatha_teeka_hindi", natural_key, doc)


async def upsert_gatha_teeka_bhaavarth_hindi(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "gatha_teeka_bhaavarth_hindi", natural_key, doc)


async def upsert_kalash_sanskrit(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "kalash_sanskrit", natural_key, doc)


async def upsert_kalash_hindi(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "kalash_hindi", natural_key, doc)


async def upsert_kalash_bhaavarth_hindi(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, "kalash_bhaavarth_hindi", natural_key, doc)


async def upsert_kalash_word_meanings(
    db: AsyncIOMotorDatabase,
    *,
    natural_key: str,
    kalash_natural_key: str,
    teeka_natural_key: str,
    kalash_number: str,
    entries: list[dict],
    ingestion_run_id: str | None = None,
) -> ObjectId:
    doc = {
        "kalash_natural_key": kalash_natural_key,
        "teeka_natural_key": teeka_natural_key,
        "kalash_number": kalash_number,
        "entries": entries,
        "ingestion_run_id": ingestion_run_id,
    }
    return await _upsert(db, KALASH_WORD_MEANINGS, natural_key, doc)


async def upsert_gatha_teeka_bhaavarth_shortfont(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, GATHA_TEEKA_BHAAVARTH_SHORTFONT, natural_key, doc)


async def upsert_kalash_bhaavarth_shortfont(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, KALASH_BHAAVARTH_SHORTFONT, natural_key, doc)


async def upsert_table(db: AsyncIOMotorDatabase, *, natural_key: str, doc: dict) -> ObjectId:
    return await _upsert(db, TABLES, natural_key, doc)


async def upsert_extract_match(
    db: AsyncIOMotorDatabase,
    *,
    natural_key: str,
    doc: dict,
) -> ObjectId:
    return await _upsert(db, EXTRACT_MATCHES, natural_key, doc)
