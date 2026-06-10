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
    Block,
    BlockRef,
    Definition,
    DefinitionItem,
    GathaHindiChhand,
    GathaPrakrit,
    GathaSanskrit,
    GathaWordMeanings,
    KeywordDefinition,
    KeywordPageSection,
    LangText,
    PageSection,
    TeekaGathaMapping,
    TopicExtract,
)
from jain_kb_common.db.mongo.schemas import (
    BhaavarthShortFontDoc,
    BhaavarthShortFontEntry,
    BhaavarthShortFontOccurrence,
    KalashBhaavarthShortFontDoc,
    TableDoc,
)
from jain_kb_common.db.mongo.upserts import (
    stable_id,
    upsert_gatha_hindi_chhand,
    upsert_gatha_prakrit,
    upsert_gatha_sanskrit,
    upsert_gatha_teeka_bhaavarth_hindi,
    upsert_gatha_teeka_bhaavarth_shortfont,
    upsert_gatha_teeka_hindi,
    upsert_gatha_teeka_sanskrit,
    upsert_gatha_word_meanings,
    upsert_kalash_bhaavarth_hindi,
    upsert_kalash_bhaavarth_shortfont,
    upsert_kalash_hindi,
    upsert_kalash_sanskrit,
    upsert_kalash_word_meanings,
    upsert_keyword_definition,
    upsert_table,
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


def test_keyword_definition_with_definitions():
    """KeywordDefinition uses KeywordPageSection with DefinitionItem blocks."""
    kd = KeywordDefinition(
        natural_key="आत्मा",
        keyword_id="uuid-001",
        source_url="https://www.jainkosh.org/wiki/आत्मा",
        page_sections=[
            KeywordPageSection(
                section_index=0,
                section_kind="siddhantkosh",
                h2_text="सिद्धांतकोष से",
                definitions=[
                    DefinitionItem(
                        definition_index=1,
                        blocks=[
                            {
                                "kind": "sanskrit_text",
                                "text_devanagari": "आत्मा द्वादशांगम् आत्मपरिणामत्वात।",
                                "hindi_translation": "द्वादशांग का नाम आत्मा है।",
                                "references": [{"text": "धवला पुस्तक 13/5,5,50/282/9"}],
                            },
                            {"kind": "see_also", "target_keyword": "जीव", "target_url": "/wiki/जीव"},
                        ],
                    )
                ],
            )
        ],
        redirect_aliases=["आतम", "आत्मन्"],
    )
    assert len(kd.page_sections) == 1
    sec = kd.page_sections[0]
    assert not hasattr(sec, "subsections")
    assert len(sec.definitions) == 1
    defn = sec.definitions[0]
    assert defn.definition_index == 1
    assert len(defn.blocks) == 2
    assert defn.blocks[0]["kind"] == "sanskrit_text"
    assert defn.blocks[0]["text_devanagari"] == "आत्मा द्वादशांगम् आत्मपरिणामत्वात।"
    assert len(defn.blocks[0]["references"]) == 1
    assert defn.blocks[1]["kind"] == "see_also"
    assert defn.blocks[1]["target_keyword"] == "जीव"


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
        "page_sections": [
            {
                "section_index": 0,
                "section_kind": "siddhantkosh",
                "heading": [{"lang": "hin", "script": "Deva", "text": "सिद्धांतकोष से"}],
                "definitions": [
                    {
                        "definition_index": 1,
                        "blocks": [
                            {
                                "kind": "sanskrit_text",
                                "text_devanagari": "आत्मा द्वादशांगम्",
                                "hindi_translation": "द्वादशांग का नाम आत्मा है।",
                                "references": [
                                    {"text": "धवला पुस्तक 1/1/1", "raw_html": None}
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
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
    sec = stored["page_sections"][0]
    assert "subsections" not in sec
    assert sec["definitions"][0]["definition_index"] == 1
    assert sec["definitions"][0]["blocks"][0]["text_devanagari"] == "आत्मा द्वादशांगम्"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_topic_extract_idempotent(db):
    nk = "jainkosh:आत्मा:बहिरात्मादि-3-भेद"
    doc = {
        "topic_id": "uuid-222",
        "source": "jainkosh",
        "source_url": "https://www.jainkosh.org/wiki/आत्मा#बहिरात्मादि_3_भेद",
        "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
        "blocks": [
            {
                "kind": "hindi_text",
                "text_devanagari": "बहिरात्मा की परिभाषा",
                "hindi_translation": None,
                "references": [],
            }
        ],
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


# ---------------------------------------------------------------------------
# New collections: gatha_teeka_*
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_teeka_sanskrit_idempotent(db):
    nk = "pravachansaar:amritchandra:गाथा:टीका:039:sanskrit"
    doc = {
        "gatha_teeka_natural_key": "pravachansaar:amritchandra:गाथा:टीका:039",
        "teeka_natural_key": "pravachansaar:amritchandra",
        "gatha_natural_key": "pravachansaar:039",
        "text": [{"lang": "san", "script": "Deva", "text": "तत्त्वार्थसूत्रम्"}],
    }
    id1 = await upsert_gatha_teeka_sanskrit(db, natural_key=nk, doc=doc)
    id2 = await upsert_gatha_teeka_sanskrit(db, natural_key=nk, doc={**doc, "text": [{"lang": "san", "script": "Deva", "text": "updated"}]})
    assert id1 == id2
    count = await db.gatha_teeka_sanskrit.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.gatha_teeka_sanskrit.find_one({"_id": id1})
    assert stored["text"][0]["text"] == "updated"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_teeka_hindi_idempotent(db):
    nk = "pravachansaar:amritchandra:गाथा:टीका:039:hindi"
    doc = {
        "gatha_teeka_natural_key": "pravachansaar:amritchandra:गाथा:टीका:039",
        "teeka_natural_key": "pravachansaar:amritchandra",
        "gatha_natural_key": "pravachansaar:039",
        "text": [{"lang": "hin", "script": "Deva", "text": "हिंदी टीका v1"}],
    }
    id1 = await upsert_gatha_teeka_hindi(db, natural_key=nk, doc=doc)
    id2 = await upsert_gatha_teeka_hindi(db, natural_key=nk, doc={**doc, "text": [{"lang": "hin", "script": "Deva", "text": "हिंदी टीका v2"}]})
    assert id1 == id2
    stored = await db.gatha_teeka_hindi.find_one({"_id": id1})
    assert stored["text"][0]["text"] == "हिंदी टीका v2"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_teeka_bhaavarth_hindi_idempotent(db):
    nk = "pravachansaar:amritchandra:jzb:गाथा:टीका:भावार्थ:039"
    doc = {
        "gatha_teeka_natural_key": "pravachansaar:amritchandra:गाथा:टीका:039",
        "publication_natural_key": "pravachansaar:amritchandra:jzb",
        "text": [{"lang": "hin", "script": "Deva", "text": "भावार्थ v1"}],
    }
    id1 = await upsert_gatha_teeka_bhaavarth_hindi(db, natural_key=nk, doc=doc)
    id2 = await upsert_gatha_teeka_bhaavarth_hindi(db, natural_key=nk, doc={**doc, "text": [{"lang": "hin", "script": "Deva", "text": "भावार्थ v2"}]})
    assert id1 == id2
    count = await db.gatha_teeka_bhaavarth_hindi.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.gatha_teeka_bhaavarth_hindi.find_one({"_id": id1})
    assert stored["text"][0]["text"] == "भावार्थ v2"


# ---------------------------------------------------------------------------
# New collections: kalash_*
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_kalash_sanskrit_idempotent(db):
    nk = "pravachansaar:amritchandra:कलश:001:sanskrit"
    doc = {
        "kalash_natural_key": "pravachansaar:amritchandra:कलश:001",
        "teeka_natural_key": "pravachansaar:amritchandra",
        "kalash_number": "001",
        "text": [{"lang": "san", "script": "Deva", "text": "कलश संस्कृत v1"}],
    }
    id1 = await upsert_kalash_sanskrit(db, natural_key=nk, doc=doc)
    id2 = await upsert_kalash_sanskrit(db, natural_key=nk, doc={**doc, "text": [{"lang": "san", "script": "Deva", "text": "कलश संस्कृत v2"}]})
    assert id1 == id2
    stored = await db.kalash_sanskrit.find_one({"_id": id1})
    assert stored["text"][0]["text"] == "कलश संस्कृत v2"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_kalash_hindi_idempotent(db):
    nk = "pravachansaar:amritchandra:कलश:001:hindi"
    doc = {
        "kalash_natural_key": "pravachansaar:amritchandra:कलश:001",
        "teeka_natural_key": "pravachansaar:amritchandra",
        "kalash_number": "001",
        "text": [{"lang": "hin", "script": "Deva", "text": "कलश हिंदी v1"}],
    }
    id1 = await upsert_kalash_hindi(db, natural_key=nk, doc=doc)
    id2 = await upsert_kalash_hindi(db, natural_key=nk, doc={**doc, "text": [{"lang": "hin", "script": "Deva", "text": "कलश हिंदी v2"}]})
    assert id1 == id2
    stored = await db.kalash_hindi.find_one({"_id": id1})
    assert stored["text"][0]["text"] == "कलश हिंदी v2"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_kalash_word_meanings_idempotent(db):
    nk = "pravachansaar:amritchandra:कलश:001:word_meanings"
    id1 = await upsert_kalash_word_meanings(
        db,
        natural_key=nk,
        kalash_natural_key="pravachansaar:amritchandra:कलश:001",
        teeka_natural_key="pravachansaar:amritchandra",
        kalash_number="001",
        entries=[{"source_word": "स्वानुभूत्या", "meaning": "स्वानुभूति से", "position": 1}],
    )
    id2 = await upsert_kalash_word_meanings(
        db,
        natural_key=nk,
        kalash_natural_key="pravachansaar:amritchandra:कलश:001",
        teeka_natural_key="pravachansaar:amritchandra",
        kalash_number="001",
        entries=[
            {"source_word": "स्वानुभूत्या", "meaning": "स्वानुभूति से", "position": 1},
            {"source_word": "चकासते", "meaning": "प्रकाशित होते हैं", "position": 2},
        ],
    )
    assert id1 == id2
    count = await db.kalash_word_meanings.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.kalash_word_meanings.find_one({"_id": id1})
    assert len(stored["entries"]) == 2
    assert stored["kalash_natural_key"] == "pravachansaar:amritchandra:कलश:001"


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_kalash_bhaavarth_hindi_idempotent(db):
    nk = "pravachansaar:amritchandra:jzb:कलश:भावार्थ:001"
    doc = {
        "kalash_natural_key": "pravachansaar:amritchandra:कलश:001",
        "publication_natural_key": "pravachansaar:amritchandra:jzb",
        "kalash_number": "001",
        "text": [{"lang": "hin", "script": "Deva", "text": "कलश भावार्थ v1"}],
    }
    id1 = await upsert_kalash_bhaavarth_hindi(db, natural_key=nk, doc=doc)
    id2 = await upsert_kalash_bhaavarth_hindi(db, natural_key=nk, doc={**doc, "text": [{"lang": "hin", "script": "Deva", "text": "कलश भावार्थ v2"}]})
    assert id1 == id2
    count = await db.kalash_bhaavarth_hindi.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.kalash_bhaavarth_hindi.find_one({"_id": id1})
    assert stored["text"][0]["text"] == "कलश भावार्थ v2"


# ---------------------------------------------------------------------------
# tables collection
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_table_doc_idempotent(db):
    nk = "table:jainkosh:आत्मा:01"
    doc = {
        "source": "jainkosh",
        "parent_natural_key": "आत्मा",
        "parent_kind": "keyword",
        "seq": 1,
        "raw_html": "<table><tr><th>भेद</th></tr><tr><td>बहिरात्मा</td></tr></table>",
        "cells": [["भेद"], ["बहिरात्मा"]],
        "header_rows": 1,
        "caption": [{"lang": "hi", "script": "devanagari", "text": "भेद"}],
        "plaintext": "भेद बहिरात्मा",
    }
    id1 = await upsert_table(db, natural_key=nk, doc=doc)
    id2 = await upsert_table(db, natural_key=nk, doc={**doc, "plaintext": "updated plaintext"})

    assert id1 == id2
    assert id1 == stable_id(nk)
    count = await db.tables.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.tables.find_one({"_id": id1})
    assert stored["plaintext"] == "updated plaintext"
    assert stored["parent_natural_key"] == "आत्मा"


def test_table_doc_schema():
    doc = TableDoc(
        natural_key="table:jainkosh:आत्मा:01",
        source="jainkosh",
        parent_natural_key="आत्मा",
        parent_kind="keyword",
        seq=1,
        raw_html="<table></table>",
    )
    assert doc.cells == []
    assert doc.header_rows == 0
    assert doc.mentioned_keyword_natural_keys == []


# ---------------------------------------------------------------------------
# gatha_teeka_bhaavarth_shortfont collection
# ---------------------------------------------------------------------------

def _sf_entry_dict(n=1):
    return {
        "marker_number": n,
        "marker_devanagari": str(n),
        "anchor_text": "मोक्ष-मार्ग",
        "meaning": "मोक्ष का विस्तार",
        "is_definition": True,
        "occurrences": [{"start_offset": 10, "end_offset": 20}],
    }


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_teeka_bhaavarth_shortfont_round_trip(db):
    nk = "समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:161:shortfont"
    doc = {
        "bhaavarth_natural_key": "समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:161",
        "publication_natural_key": "समयसार:आत्मख्याति:0",
        "gatha_natural_key": "समयसार:गाथा:161",
        "gatha_number": "161",
        "entries": [_sf_entry_dict(1), _sf_entry_dict(2)],
    }
    id1 = await upsert_gatha_teeka_bhaavarth_shortfont(db, natural_key=nk, doc=doc)
    updated_doc = {**doc, "entries": [_sf_entry_dict(1), _sf_entry_dict(2), _sf_entry_dict(3)]}
    id2 = await upsert_gatha_teeka_bhaavarth_shortfont(db, natural_key=nk, doc=updated_doc)

    assert id1 == id2
    assert id1 == stable_id(nk)
    count = await db.gatha_teeka_bhaavarth_shortfont.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.gatha_teeka_bhaavarth_shortfont.find_one({"_id": id1})
    assert stored["gatha_number"] == "161"
    assert len(stored["entries"]) == 3


@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_gatha_teeka_bhaavarth_shortfont_unique_nk_constraint(db):
    nk = "समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:1:shortfont"
    doc = {
        "bhaavarth_natural_key": "समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:1",
        "publication_natural_key": "समयसार:आत्मख्याति:0",
        "gatha_natural_key": "समयसार:गाथा:1",
        "gatha_number": "1",
        "entries": [_sf_entry_dict()],
    }
    id1 = await upsert_gatha_teeka_bhaavarth_shortfont(db, natural_key=nk, doc=doc)
    id2 = await upsert_gatha_teeka_bhaavarth_shortfont(db, natural_key=nk, doc=doc)
    assert id1 == id2
    assert await db.gatha_teeka_bhaavarth_shortfont.count_documents({"natural_key": nk}) == 1


# ---------------------------------------------------------------------------
# kalash_bhaavarth_shortfont collection
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_upsert_kalash_bhaavarth_shortfont_round_trip(db):
    nk = "समयसार:आत्मख्याति:कलश:4:shortfont"
    doc = {
        "kalash_natural_key": "समयसार:आत्मख्याति:कलश:4",
        "teeka_natural_key": "समयसार:आत्मख्याति",
        "kalash_number": "4",
        "entries": [_sf_entry_dict()],
    }
    id1 = await upsert_kalash_bhaavarth_shortfont(db, natural_key=nk, doc=doc)
    id2 = await upsert_kalash_bhaavarth_shortfont(db, natural_key=nk, doc={**doc, "entries": []})

    assert id1 == id2
    count = await db.kalash_bhaavarth_shortfont.count_documents({"natural_key": nk})
    assert count == 1
    stored = await db.kalash_bhaavarth_shortfont.find_one({"_id": id1})
    assert stored["kalash_number"] == "4"
    assert stored["entries"] == []


# ---------------------------------------------------------------------------
# Pydantic schemas for shortfont
# ---------------------------------------------------------------------------

def test_bhaavarth_shortfont_doc_schema():
    doc = BhaavarthShortFontDoc(
        natural_key="समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:161:shortfont",
        bhaavarth_natural_key="समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:161",
        publication_natural_key="समयसार:आत्मख्याति:0",
        gatha_natural_key="समयसार:गाथा:161",
        gatha_number="161",
        entries=[
            BhaavarthShortFontEntry(
                marker_number=4,
                marker_devanagari="४",
                anchor_text="मोक्ष-मार्ग-प्रपंच-सूचक",
                meaning="मोक्ष का विस्तार बतलाने वाली",
                is_definition=True,
                occurrences=[BhaavarthShortFontOccurrence(start_offset=1284, end_offset=1308)],
            )
        ],
    )
    assert doc.gatha_number == "161"
    assert doc.entries[0].marker_number == 4
    assert doc.entries[0].occurrences[0].start_offset == 1284


def test_kalash_bhaavarth_shortfont_doc_schema():
    doc = KalashBhaavarthShortFontDoc(
        natural_key="समयसार:आत्मख्याति:कलश:4:shortfont",
        kalash_natural_key="समयसार:आत्मख्याति:कलश:4",
        teeka_natural_key="समयसार:आत्मख्याति",
        kalash_number="4",
        entries=[],
    )
    assert doc.kalash_number == "4"
    assert doc.entries == []
