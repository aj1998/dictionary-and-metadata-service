"""End-to-end orchestrator tests using in-memory fixtures."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

MONGO_URL = os.environ.get("MONGO_URL", "")
skip_no_mongo = pytest.mark.skipif(not MONGO_URL, reason="MONGO_URL not set")


def _make_driver_with_stubs(stub_records_by_call: list[list[dict]]) -> MagicMock:
    """Return driver that cycles through stub_records_by_call on each session.run()."""
    call_idx = [0]

    async def _data():
        idx = call_idx[0]
        if idx < len(stub_records_by_call):
            result = stub_records_by_call[idx]
            call_idx[0] += 1
            return result
        return []

    mock_result = MagicMock()
    mock_result.data = _data

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=mock_session)
    return mock_driver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_KEYWORD_DOC = {
    "natural_key": "आत्मा",
    "page_sections": [
        {
            "section_index": 0,
            "section_kind": "siddhantkosh",
            "definitions": [
                {
                    "definition_index": 0,
                    "blocks": [
                        {
                            "kind": "prakrit_gatha",
                            "text_devanagari": "जे णेव हि संजाया",
                            "references": [
                                {
                                    "text": "समयसार गाथा 1",
                                    "resolved_fields": [{"field": "gatha", "value": 1}],
                                    "shastra_name": "समयसार",
                                    "inline_reference": False,
                                }
                            ],
                        },
                        {
                            "kind": "sanskrit_text",
                            "text_devanagari": "यद्यपि",
                            "references": [
                                {
                                    "text": "समयसार टीका 1",
                                    "resolved_fields": [{"field": "gatha", "value": 1}],
                                    "shastra_name": "समयसार",
                                    "inline_reference": False,
                                }
                            ],
                        },
                        {
                            "kind": "hindi_text",
                            "text_devanagari": "यद्यपि भावार्थ",
                            "references": [
                                {
                                    "text": "समयसार भावार्थ 1",
                                    "resolved_fields": [{"field": "gatha", "value": 1}],
                                    "shastra_name": "समयसार",
                                    "inline_reference": False,
                                }
                            ],
                        },
                    ],
                }
            ],
        }
    ],
}

_GATHA_PRAKRIT_DOC = {
    "natural_key": "samaysar:गाथा:1:prakrit",
    "text": [{"lang": "pra", "text": "जे णेव हि संजाया णिच्चयणयेण"}],
}

_GATHA_TEEKA_SANSKRIT_DOC = {
    "natural_key": "samaysar:amritchandra:1:टीका:san",
    "text": [{"lang": "san", "text": "यद्यपि ये जायन्ते"}],
}

_GATHA_TEEKA_BHAAVARTH_DOC = {
    "natural_key": "samaysar:amritchandra:jzb:1:भावार्थ:hi",
    "text": [{"lang": "hin", "text": "यद्यपि भावार्थ विस्तृत"}],
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_mongo
@pytest.mark.asyncio
async def test_orchestrator_matches_three_blocks():
    """1 keyword_definition with 3 eligible blocks → 3 matched rows."""
    from motor.motor_asyncio import AsyncIOMotorClient

    from jain_kb_common.db.mongo.indexes import ensure_indexes
    from workers.matching.orchestrator import match_all

    client = AsyncIOMotorClient(MONGO_URL)
    db = client["jain_kb_orchestrator_test"]

    try:
        await ensure_indexes(db)

        # Seed keyword_definitions
        await db.keyword_definitions.insert_one(dict(_KEYWORD_DOC))

        # Seed NJ target docs
        await db.gatha_prakrit.insert_one(dict(_GATHA_PRAKRIT_DOC))
        await db.gatha_teeka_sanskrit.insert_one(dict(_GATHA_TEEKA_SANSKRIT_DOC))
        await db.gatha_teeka_bhaavarth_hindi.insert_one(dict(_GATHA_TEEKA_BHAAVARTH_DOC))

        # Neo4j driver returns stubs for each of the 3 blocks
        neo4j_stub_results = [
            # block 0 (prakrit_gatha) → Gatha stub
            [{"stub_nk": "samaysar:गाथा:1", "stub_labels": ["Gatha"],
              "teeka_natural_key": None, "gatha_natural_key": None,
              "publication_natural_key": None, "kalash_number": None,
              "shastra_natural_key": "samaysar"}],
            # block 1 (sanskrit_text) → GathaTeeka stub
            [{"stub_nk": "samaysar:amritchandra:गाथा:टीका:1", "stub_labels": ["GathaTeeka"],
              "teeka_natural_key": "samaysar:amritchandra",
              "gatha_natural_key": "samaysar:गाथा:1",
              "publication_natural_key": None, "kalash_number": None,
              "shastra_natural_key": "samaysar"}],
            # block 2 (hindi_text) → GathaTeekaBhaavarth stub
            [{"stub_nk": "samaysar:amritchandra:jzb:गाथा:टीका:भावार्थ:1", "stub_labels": ["GathaTeekaBhaavarth"],
              "teeka_natural_key": None,
              "gatha_natural_key": "samaysar:गाथा:1",
              "publication_natural_key": "samaysar:amritchandra:jzb",
              "kalash_number": None,
              "shastra_natural_key": "samaysar"}],
        ]
        driver = _make_driver_with_stubs(neo4j_stub_results)

        run_id = uuid4()
        stats = await match_all(db, driver, run_id=run_id)

        assert stats.blocks_processed == 3
        assert stats.edges_attempted == 3
        total = stats.matched + stats.unmatched + stats.target_missing
        assert total == 3

        count = await db.extract_matches.count_documents({"ingestion_run_id": str(run_id)})
        assert count == 3

    finally:
        for col in await db.list_collection_names():
            await db.drop_collection(col)
        client.close()


@skip_no_mongo
@pytest.mark.asyncio
async def test_orchestrator_idempotent():
    """Re-running orchestrator on same fixture leaves row count unchanged."""
    from motor.motor_asyncio import AsyncIOMotorClient

    from jain_kb_common.db.mongo.indexes import ensure_indexes
    from workers.matching.orchestrator import match_all

    client = AsyncIOMotorClient(MONGO_URL)
    db = client["jain_kb_orchestrator_idem_test"]

    try:
        await ensure_indexes(db)
        await db.keyword_definitions.insert_one(dict(_KEYWORD_DOC))
        await db.gatha_prakrit.insert_one(dict(_GATHA_PRAKRIT_DOC))
        await db.gatha_teeka_sanskrit.insert_one(dict(_GATHA_TEEKA_SANSKRIT_DOC))
        await db.gatha_teeka_bhaavarth_hindi.insert_one(dict(_GATHA_TEEKA_BHAAVARTH_DOC))

        def _stub_results():
            return [
                [{"stub_nk": "samaysar:गाथा:1", "stub_labels": ["Gatha"],
                  "teeka_natural_key": None, "gatha_natural_key": None,
                  "publication_natural_key": None, "kalash_number": None,
                  "shastra_natural_key": "samaysar"}],
                [{"stub_nk": "samaysar:amritchandra:गाथा:टीका:1", "stub_labels": ["GathaTeeka"],
                  "teeka_natural_key": "samaysar:amritchandra",
                  "gatha_natural_key": "samaysar:गाथा:1",
                  "publication_natural_key": None, "kalash_number": None,
                  "shastra_natural_key": "samaysar"}],
                [{"stub_nk": "samaysar:amritchandra:jzb:गाथा:टीका:भावार्थ:1", "stub_labels": ["GathaTeekaBhaavarth"],
                  "teeka_natural_key": None,
                  "gatha_natural_key": "samaysar:गाथा:1",
                  "publication_natural_key": "samaysar:amritchandra:jzb",
                  "kalash_number": None,
                  "shastra_natural_key": "samaysar"}],
            ]

        run1 = uuid4()
        await match_all(db, _make_driver_with_stubs(_stub_results()), run_id=run1)
        count_after_first = await db.extract_matches.count_documents({})

        run2 = uuid4()
        await match_all(db, _make_driver_with_stubs(_stub_results()), run_id=run2)
        count_after_second = await db.extract_matches.count_documents({})

        assert count_after_first == count_after_second

    finally:
        for col in await db.list_collection_names():
            await db.drop_collection(col)
        client.close()
