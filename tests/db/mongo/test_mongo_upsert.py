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
from jain_kb_common.db.mongo.schemas import (
    GathaHindiChhand,
    GathaPrakrit,
    GathaSanskrit,
    GathaWordMeanings,
    KeywordDefinition,
    LangText,
    TeekaGathaMapping,
    TopicExtract,
)
from jain_kb_common.db.mongo.upserts import (
    stable_id,
    upsert_gatha_hindi_chhand,
    upsert_gatha_prakrit,
    upsert_gatha_sanskrit,
    upsert_gatha_word_meanings,
    upsert_keyword_definition,
    upsert_teeka_gatha_mapping,
    upsert_topic_extract,
)

MONGO_URL = os.environ.get("MONGO_URL", "")
_MONGO_AVAILABLE = bool(MONGO_URL)
skip_no_mongo = pytest.mark.skipif(not _MONGO_AVAILABLE, reason="MONGO_URL not set")

TEST_DB = "jain_kb_test"

@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[TEST_DB]
    await ensure_indexes(database)
    yield database
    # teardown: drop all test collections
    for col in await database.list_collection_names():
        await database.drop_collection(col)
    client.close()


# ---------------------------------------------------------------------------
# stable_id
# ---------------------------------------------------------------------------

def test_stable_id_deterministic():
    """Same natural_key always yields the same ObjectId."""
    nk = "pravachansaar:039:prakrit"
    assert stable_id(nk) == stable_id(nk)


def test_stable_id_different_keys():
    assert stable_id("a") != stable_id("b")


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------

def test_lang_text_nfc():
    # Devanagari NFC: U+0928 U+093C vs precomposed — both should NFC-normalize
    lt = LangText(lang="hin", script="Deva", text="ऩ")
    import unicodedata
    assert lt.text == unicodedata.normalize("NFC", "ऩ")


def test_gatha_prakrit_schema():
    doc = GathaPrakrit(
        natural_key="pravachansaar:039:prakrit",
        shastra_natural_key="pravachansaar",
        gatha_natural_key="pravachansaar:039",
        gatha_number="039",
        text=[LangText(lang="pra", script="Deva", text="जे णेव हि संजाया")],
        is_kalash=False,
    )
    assert doc.gatha_number == "039"


def test_keyword_definition_schema():
    kd = KeywordDefinition(
        natural_key="आत्मा",
        keyword_id="some-uuid",
        source_url="https://www.jainkosh.org/wiki/आत्मा",
    )
    assert kd.redirect_aliases == []


# ---------------------------------------------------------------------------
# Round-trip upserts (require MONGO_URL)
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_prakrit_idempotent(db):
    nk = "pravachansaar:039:prakrit"
    doc = {
        "shastra_natural_key": "pravachansaar",
        "gatha_natural_key": "pravachansaar:039",
        "gatha_number": "039",
        "text": [{"lang": "pra", "script": "Deva", "text": "जे णेव हि संजाया"}],
        "is_kalash": False,
    }
    id1 = await upsert_gatha_prakrit(db, natural_key=nk, doc=doc)

    doc2 = {**doc, "text": [{"lang": "pra", "script": "Deva", "text": "updated text"}]}
    id2 = await upsert_gatha_prakrit(db, natural_key=nk, doc=doc2)

    assert id1 == id2
    count = await db.gatha_prakrit.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.gatha_prakrit.find_one({"_id": id1})
    assert stored["text"][0]["text"] == "updated text"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_sanskrit_idempotent(db):
    nk = "pravachansaar:039:sanskrit"
    doc = {
        "shastra_natural_key": "pravachansaar",
        "gatha_natural_key": "pravachansaar:039",
        "gatha_number": "039",
        "text": [{"lang": "san", "script": "Deva", "text": "यदा यदा हि"}],
    }
    id1 = await upsert_gatha_sanskrit(db, natural_key=nk, doc=doc)
    id2 = await upsert_gatha_sanskrit(db, natural_key=nk, doc={**doc, "text": [{"lang": "san", "script": "Deva", "text": "updated"}]})
    assert id1 == id2
    count = await db.gatha_sanskrit.count_documents({"natural_key": nk})
    assert count == 1


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_hindi_chhand_idempotent(db):
    nk = "pravachansaar:039:chhand:01"
    doc = {
        "gatha_natural_key": "pravachansaar:039",
        "chhand_index": 1,
        "chhand_type": "harigeet",
        "text": [{"lang": "hin", "script": "Deva", "text": "हरिगीत पाठ"}],
    }
    id1 = await upsert_gatha_hindi_chhand(db, natural_key=nk, doc=doc)
    id2 = await upsert_gatha_hindi_chhand(db, natural_key=nk, doc={**doc, "chhand_type": "chaupai"})
    assert id1 == id2
    stored = await db.gatha_hindi_chhand.find_one({"_id": id1})
    assert stored["chhand_type"] == "chaupai"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_word_meanings_idempotent(db):
    nk = "pravachansaar:039:word_meanings:prakrit"
    doc = {
        "gatha_natural_key": "pravachansaar:039",
        "source_language": "pra",
        "entries": [
            {
                "source_word": [{"lang": "pra", "script": "Deva", "text": "णेव"}],
                "meanings": [{"lang": "hin", "script": "Deva", "text": "नहीं"}],
                "position": 1,
            }
        ],
    }
    id1 = await upsert_gatha_word_meanings(db, natural_key=nk, doc=doc)
    doc2 = {**doc, "entries": doc["entries"] + [
        {
            "source_word": [{"lang": "pra", "script": "Deva", "text": "हि"}],
            "meanings": [{"lang": "hin", "script": "Deva", "text": "निश्चय से"}],
            "position": 2,
        }
    ]}
    id2 = await upsert_gatha_word_meanings(db, natural_key=nk, doc=doc2)
    assert id1 == id2
    count = await db.gatha_word_meanings.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.gatha_word_meanings.find_one({"_id": id1})
    assert len(stored["entries"]) == 2


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_teeka_gatha_mapping_idempotent(db):
    nk = "pravachansaar:amritchandra:039"
    doc = {
        "teeka_natural_key": "pravachansaar:amritchandra",
        "gatha_natural_key": "pravachansaar:039",
        "anvayartha": [{"lang": "hin", "script": "Deva", "text": "उन द्रव्य-जातियों की"}],
    }
    id1 = await upsert_teeka_gatha_mapping(db, natural_key=nk, doc=doc)
    doc2 = {**doc, "anvayartha": [{"lang": "hin", "script": "Deva", "text": "updated anvayartha"}]}
    id2 = await upsert_teeka_gatha_mapping(db, natural_key=nk, doc=doc2)
    assert id1 == id2
    stored = await db.teeka_gatha_mapping.find_one({"_id": id1})
    assert stored["anvayartha"][0]["text"] == "updated anvayartha"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_keyword_definition_idempotent(db):
    nk = "आत्मा"
    doc = {
        "keyword_id": "uuid-111",
        "source_url": "https://www.jainkosh.org/wiki/आत्मा",
        "page_sections": [],
        "redirect_aliases": ["आतम"],
    }
    id1 = await upsert_keyword_definition(db, natural_key=nk, doc=doc)
    doc2 = {**doc, "redirect_aliases": ["आतम", "आत्मन्"]}
    id2 = await upsert_keyword_definition(db, natural_key=nk, doc=doc2)
    assert id1 == id2
    count = await db.keyword_definitions.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.keyword_definitions.find_one({"_id": id1})
    assert stored["redirect_aliases"] == ["आतम", "आत्मन्"]


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_topic_extract_idempotent(db):
    nk = "jainkosh:आत्मा:बहिरात्मादि-3-भेद"
    doc = {
        "topic_id": "uuid-222",
        "source": "jainkosh",
        "source_url": "https://www.jainkosh.org/wiki/आत्मा#बहिरात्मादि_3_भेद",
        "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
        "blocks": [],
        "extracted_keyword_natural_keys": ["आत्मा"],
    }
    id1 = await upsert_topic_extract(db, natural_key=nk, doc=doc)
    doc2 = {**doc, "extracted_keyword_natural_keys": ["आत्मा", "बहिरात्मा"]}
    id2 = await upsert_topic_extract(db, natural_key=nk, doc=doc2)
    assert id1 == id2
    stored = await db.topic_extracts.find_one({"_id": id1})
    assert "बहिरात्मा" in stored["extracted_keyword_natural_keys"]


@skip_no_mongo
@pytest.mark.asyncio
async def test_created_at_not_overwritten_on_reupsert(db):
    """created_at must stay from first insert; updated_at must change."""
    nk = "test:timestamps"
    doc = {"gatha_natural_key": "x:001", "source_language": "pra", "entries": []}
    await upsert_gatha_word_meanings(db, natural_key=nk, doc=doc)
    stored1 = await db.gatha_word_meanings.find_one({"natural_key": nk})
    created_at1 = stored1["created_at"]
    updated_at1 = stored1["updated_at"]

    import asyncio
    await asyncio.sleep(0.01)

    await upsert_gatha_word_meanings(db, natural_key=nk, doc={**doc, "source_language": "san"})
    stored2 = await db.gatha_word_meanings.find_one({"natural_key": nk})
    assert stored2["created_at"] == created_at1
    assert stored2["updated_at"] >= updated_at1
