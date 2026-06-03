"""Unit tests for target_resolver — Neo4j mocked."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from workers.matching.source_iter import SourceBlock
from workers.matching.target_resolver import resolve_targets


def _make_neo4j_record(**kwargs) -> dict:
    defaults = {
        "stub_nk": None,
        "stub_labels": [],
        "teeka_natural_key": None,
        "gatha_natural_key": None,
        "publication_natural_key": None,
        "kalash_number": None,
        "shastra_natural_key": None,
    }
    defaults.update(kwargs)
    return defaults


def _make_driver(records: list[dict]) -> MagicMock:
    """Build a fake AsyncDriver whose session.run returns the given records."""
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=records)

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=mock_session)
    return mock_driver


def _make_mongo(docs: dict[str, dict | None]) -> MagicMock:
    """
    Build a fake Motor db where db[collection].find_one(query) returns docs[collection].
    """
    mongo = MagicMock()

    async def _find_one(query):
        col = _current_col[0]
        return docs.get(col)

    _current_col = [None]

    class _Col:
        def __init__(self, name):
            self._name = name

        async def find_one(self, query):
            return docs.get(self._name)

    class _DB:
        def __getitem__(self, name):
            return _Col(name)

        def __getattr__(self, name):
            return _Col(name)

    return _DB()


@pytest.mark.asyncio
async def test_gatha_stub_routes_to_gatha_prakrit():
    """Gatha stub + prakrit_gatha block_kind → gatha_prakrit collection."""
    records = [
        _make_neo4j_record(
            stub_nk="samaysar:गाथा:1",
            stub_labels=["Gatha"],
            shastra_natural_key="samaysar",
        )
    ]
    driver = _make_driver(records)
    mongo = _make_mongo({
        "gatha_prakrit": {
            "natural_key": "samaysar:गाथा:1:prakrit",
            "text": [{"lang": "pra", "text": "णमो अरिहंताणं"}],
        }
    })

    source = SourceBlock(
        kind="keyword_definition",
        parent_natural_key="आत्मा",
        section_index=0,
        definition_index=0,
        block_index=0,
        block_kind="prakrit_gatha",
        text_devanagari="णमो अरिहंताणं",
        reference_text="समयसार गाथा 1",
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    t = targets[0]
    assert t.collection == "gatha_prakrit"
    assert t.natural_key == "samaysar:गाथा:1:prakrit"
    assert t.lang == "pra"
    assert t.stub_label == "Gatha"
    assert t.status_hint is None
    assert t.text == "णमो अरिहंताणं"


@pytest.mark.asyncio
async def test_gatha_teeka_stub_routes_to_teeka_sanskrit():
    """GathaTeeka stub + sanskrit_text → gatha_teeka_sanskrit collection."""
    records = [
        _make_neo4j_record(
            stub_nk="samaysar:amritchandra:गाथा:टीका:1",
            stub_labels=["GathaTeeka"],
            teeka_natural_key="samaysar:amritchandra",
            gatha_natural_key="samaysar:गाथा:1",
            shastra_natural_key="samaysar",
        )
    ]
    driver = _make_driver(records)
    expected_mongo_nk = "samaysar:amritchandra:1:टीका:san"
    mongo = _make_mongo({
        "gatha_teeka_sanskrit": {
            "natural_key": expected_mongo_nk,
            "text": [{"lang": "san", "text": "अथ तत्त्वार्थ"}],
        }
    })

    source = SourceBlock(
        kind="keyword_definition",
        parent_natural_key="आत्मा",
        section_index=0,
        definition_index=0,
        block_index=1,
        block_kind="sanskrit_text",
        text_devanagari="अथ तत्त्वार्थ",
        reference_text="समयसार टीका 1",
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    t = targets[0]
    assert t.collection == "gatha_teeka_sanskrit"
    assert t.natural_key == expected_mongo_nk
    assert t.lang == "san"
    assert t.text == "अथ तत्त्वार्थ"


@pytest.mark.asyncio
async def test_page_stub_skipped():
    """Page label → target skipped in v1."""
    records = [
        _make_neo4j_record(
            stub_nk="samaysar:amritchandra:jzb:पृष्ठ:5",
            stub_labels=["Page"],
        )
    ]
    driver = _make_driver(records)
    mongo = _make_mongo({})

    source = SourceBlock(
        kind="keyword_definition",
        parent_natural_key="आत्मा",
        section_index=0,
        definition_index=0,
        block_index=0,
        block_kind="hindi_text",
        text_devanagari="कोई पाठ",
        reference_text="ref",
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert targets == []


@pytest.mark.asyncio
async def test_target_missing_when_mongo_doc_absent():
    """When Mongo doc doesn't exist, Target has status_hint='target_missing'."""
    records = [
        _make_neo4j_record(
            stub_nk="samaysar:गाथा:99",
            stub_labels=["Gatha"],
            shastra_natural_key="samaysar",
        )
    ]
    driver = _make_driver(records)
    # Mongo returns None (doc not found)
    mongo = _make_mongo({"gatha_prakrit": None})

    source = SourceBlock(
        kind="topic_extract",
        parent_natural_key="samaysar:topic:1",
        section_index=None,
        definition_index=None,
        block_index=0,
        block_kind="prakrit_gatha",
        text_devanagari="णमो",
        reference_text="ref",
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    assert targets[0].status_hint == "target_missing"
    assert targets[0].text is None


@pytest.mark.asyncio
async def test_unknown_block_kind_stub_combo_skipped():
    """If (stub_label, block_kind) not in routing table → skip with WARNING."""
    records = [
        _make_neo4j_record(
            stub_nk="samaysar:गाथा:1",
            stub_labels=["Gatha"],
            shastra_natural_key="samaysar",
        )
    ]
    driver = _make_driver(records)
    mongo = _make_mongo({})

    source = SourceBlock(
        kind="keyword_definition",
        parent_natural_key="आत्मा",
        section_index=0,
        definition_index=0,
        block_index=0,
        block_kind="hindi_text",   # Gatha + hindi_text → not in routing table
        text_devanagari="हिंदी पाठ",
        reference_text="ref",
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert targets == []


@pytest.mark.asyncio
async def test_no_neo4j_records_returns_empty():
    """When Neo4j returns no stubs, resolve_targets returns []."""
    driver = _make_driver([])
    mongo = _make_mongo({})

    source = SourceBlock(
        kind="keyword_definition",
        parent_natural_key="आत्मा",
        section_index=0,
        definition_index=0,
        block_index=0,
        block_kind="sanskrit_text",
        text_devanagari="some text",
        reference_text=None,
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert targets == []
