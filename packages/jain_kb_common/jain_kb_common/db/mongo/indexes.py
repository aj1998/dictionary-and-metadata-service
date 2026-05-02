from __future__ import annotations

import pymongo
from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all collection indexes. Safe to call on every startup (idempotent)."""

    # gatha_prakrit
    await db.gatha_prakrit.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
    await db.gatha_prakrit.create_index([
        ("shastra_natural_key", pymongo.ASCENDING),
        ("gatha_number", pymongo.ASCENDING),
    ])

    # gatha_sanskrit
    await db.gatha_sanskrit.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
    await db.gatha_sanskrit.create_index([
        ("shastra_natural_key", pymongo.ASCENDING),
        ("gatha_number", pymongo.ASCENDING),
    ])

    # gatha_hindi_chhand
    await db.gatha_hindi_chhand.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
    await db.gatha_hindi_chhand.create_index([
        ("gatha_natural_key", pymongo.ASCENDING),
        ("chhand_index", pymongo.ASCENDING),
    ])

    # gatha_word_meanings
    await db.gatha_word_meanings.create_index([("natural_key", pymongo.ASCENDING)], unique=True)

    # teeka_gatha_mapping
    await db.teeka_gatha_mapping.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
    await db.teeka_gatha_mapping.create_index([("teeka_natural_key", pymongo.ASCENDING)])
    await db.teeka_gatha_mapping.create_index([("gatha_natural_key", pymongo.ASCENDING)])

    # keyword_definitions
    await db.keyword_definitions.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
    await db.keyword_definitions.create_index([("keyword_id", pymongo.ASCENDING)])
    await db.keyword_definitions.create_index([("ingestion_run_id", pymongo.ASCENDING)])

    # topic_extracts
    await db.topic_extracts.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
    await db.topic_extracts.create_index([("topic_id", pymongo.ASCENDING)])
    await db.topic_extracts.create_index(
        [("blocks.text.text", pymongo.TEXT), ("heading.text", pymongo.TEXT)],
        default_language="none",
    )

    # raw_html_snapshots
    await db.raw_html_snapshots.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
    await db.raw_html_snapshots.create_index([("ingestion_run_id", pymongo.ASCENDING)])
    await db.raw_html_snapshots.create_index(
        [("fetched_at", pymongo.ASCENDING)],
        expireAfterSeconds=365 * 24 * 3600,
    )

    # ocr_pages (scaffolded — no data yet)
    await db.ocr_pages.create_index([("natural_key", pymongo.ASCENDING)], unique=True)
