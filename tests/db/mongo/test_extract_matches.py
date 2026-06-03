"""Tests for extract_matches collection: upsert idempotency, indexes, stable _id."""

from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)

from motor.motor_asyncio import AsyncIOMotorClient

from jain_kb_common.db.mongo.indexes import ensure_indexes
from jain_kb_common.db.mongo.upserts import stable_id, upsert_extract_match

MONGO_URL = os.environ.get("MONGO_URL", "")
_MONGO_AVAILABLE = bool(MONGO_URL)
skip_no_mongo = pytest.mark.skipif(not _MONGO_AVAILABLE, reason="MONGO_URL not set")

TEST_DB = "jain_kb_extract_matches_test"


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[TEST_DB]
    await ensure_indexes(database)
    yield database
    for col in await database.list_collection_names():
        await database.drop_collection(col)
    client.close()


def _sample_doc(run_id: str = "run-001") -> dict:
    return {
        "source": {
            "kind": "keyword_definition",
            "parent_natural_key": "आत्मा",
            "section_index": 0,
            "definition_index": 0,
            "block_index": 2,
            "block_kind": "sanskrit_text",
            "text_devanagari": "आत्मा द्वादशांगम्",
            "reference_text": "धवला पुस्तक 13/5,5,50/282/9",
        },
        "target": {
            "collection": "gatha_teeka_sanskrit",
            "natural_key": "samaysar:amritchandra:39:टीका:san",
            "stub_label": "GathaTeeka",
            "shastra_natural_key": "samaysar",
            "gatha_natural_key": "samaysar:गाथा:39",
            "lang": "san",
        },
        "match": {
            "status": "matched",
            "method": "exact_normalized",
            "score": 0.97,
            "char_start": 100,
            "char_end": 150,
            "threshold": 0.80,
        },
        "matcher_version": "1.0.0",
        "ingestion_run_id": run_id,
    }


# ---------------------------------------------------------------------------
# stable_id round-trip
# ---------------------------------------------------------------------------

def test_stable_id_deterministic():
    nk = "match:keyword_definition:आत्मा:s0:d0:b2:target:samaysar:amritchandra:39:टीका:san"
    assert stable_id(nk) == stable_id(nk)


def test_stable_id_different_natural_keys():
    nk1 = "match:keyword_definition:आत्मा:s0:d0:b2:target:a"
    nk2 = "match:keyword_definition:आत्मा:s0:d0:b2:target:b"
    assert stable_id(nk1) != stable_id(nk2)


# ---------------------------------------------------------------------------
# Upsert idempotency (requires MONGO_URL)
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_extract_match_idempotent(db):
    nk = "match:keyword_definition:आत्मा:s0:d0:b2:target:samaysar:amritchandra:39:टीका:san"
    doc = _sample_doc()

    id1 = await upsert_extract_match(db, natural_key=nk, doc=doc)
    doc2 = {**doc, "matcher_version": "1.1.0"}
    id2 = await upsert_extract_match(db, natural_key=nk, doc=doc2)

    assert id1 == id2
    count = await db.extract_matches.count_documents({"natural_key": nk})
    assert count == 1

    stored = await db.extract_matches.find_one({"_id": id1})
    assert stored["matcher_version"] == "1.1.0"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_extract_match_stable_id(db):
    nk = "match:keyword_definition:आत्मा:s0:d0:b2:target:test"
    doc = _sample_doc()

    _id = await upsert_extract_match(db, natural_key=nk, doc=doc)
    expected = stable_id(nk)
    assert _id == expected


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_different_natural_keys_different_docs(db):
    nk1 = "match:keyword_definition:आत्मा:s0:d0:b0:target:a"
    nk2 = "match:keyword_definition:आत्मा:s0:d0:b1:target:b"
    doc = _sample_doc()

    id1 = await upsert_extract_match(db, natural_key=nk1, doc=doc)
    id2 = await upsert_extract_match(db, natural_key=nk2, doc=doc)

    assert id1 != id2
    count = await db.extract_matches.count_documents({})
    assert count == 2


# ---------------------------------------------------------------------------
# Index presence
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_extract_matches_indexes_present(db):
    index_info = await db.extract_matches.index_information()
    index_keys = {
        tuple(sorted(v["key"]))
        for v in index_info.values()
    }
    # natural_key unique index
    assert ("natural_key", 1) in {k[0] for v in index_info.values() for k in [v["key"]]}
    # status index
    status_keys = [v["key"] for v in index_info.values()]
    assert any(k == [("match.status", 1)] for k in status_keys)
    # target.natural_key index
    assert any(k == [("target.natural_key", 1)] for k in status_keys)
