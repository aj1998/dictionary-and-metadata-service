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
async def test_gatha_stub_sanskrit_text_routes_to_gatha_sanskrit():
    """Gatha stub + sanskrit_text → gatha_sanskrit collection.

    For root "shastra"-type shastras whose primary verse is Sanskrit (e.g.
    तत्त्वार्थसूत्र), JainKosh extracts the sutra as a ``sanskrit_text`` block but
    emits a ``Gatha`` stub (the sutra *is* the gatha). The Sanskrit body lives
    in ``gatha_sanskrit``, so this combo must route there — not be dropped.
    """
    records = [
        _make_neo4j_record(
            stub_nk="तत्त्वार्थसूत्र:अध्याय:5:सूत्र:29",
            stub_labels=["Gatha"],
            shastra_natural_key="तत्त्वार्थसूत्र",
        )
    ]
    driver = _make_driver(records)
    expected_mongo_nk = "तत्त्वार्थसूत्र:अध्याय:5:सूत्र:29:sanskrit"
    mongo = _make_mongo({
        "gatha_sanskrit": {
            "natural_key": expected_mongo_nk,
            "text": [{"lang": "san", "text": "सत् द्रव्य-लक्षणम्"}],
        }
    })

    source = SourceBlock(
        kind="topic_extract",
        parent_natural_key="द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-लक्षण-सत्-तथा-उत्पादव्ययध्रौव्य",
        section_index=None,
        definition_index=None,
        block_index=0,
        block_kind="sanskrit_text",
        text_devanagari="सत् द्रव्यलक्षणम्।29।",
        reference_text="तत्त्वार्थसूत्र/5/29",
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    t = targets[0]
    assert t.collection == "gatha_sanskrit"
    assert t.natural_key == expected_mongo_nk
    assert t.lang == "san"
    assert t.stub_label == "Gatha"
    assert t.gatha_natural_key == "तत्त्वार्थसूत्र:अध्याय:5:सूत्र:29"
    assert t.text == "सत् द्रव्य-लक्षणम्"


@pytest.mark.asyncio
async def test_gatha_stub_emits_anvayartha_target_from_hindi_translation():
    """A Gatha verse target + a block with hindi_translation also yields a
    teeka_gatha_mapping (अन्वयार्थ) target matched against the Hindi side."""
    records = [
        _make_neo4j_record(
            stub_nk="तत्त्वार्थसूत्र:अध्याय:5:सूत्र:29",
            stub_labels=["Gatha"],
            shastra_natural_key="तत्त्वार्थसूत्र",
        )
    ]
    driver = _make_driver(records)
    mongo = _make_mongo({
        "gatha_sanskrit": {
            "natural_key": "तत्त्वार्थसूत्र:अध्याय:5:सूत्र:29:sanskrit",
            "text": [{"lang": "san", "text": "सत् द्रव्य-लक्षणम्"}],
        },
        "teeka_gatha_mapping": {
            "natural_key": "तत्त्वार्थसूत्र:सर्वार्थसिद्धि:अध्याय:5:सूत्र:29",
            "gatha_natural_key": "तत्त्वार्थसूत्र:अध्याय:5:सूत्र:29",
            "full_anyavaarth": "द्रव्य का लक्षण सत् है ॥२९॥",
        },
    })

    source = SourceBlock(
        kind="topic_extract",
        parent_natural_key="द्रव्य:...:द्रव्य-का-लक्षण-सत्",
        section_index=None,
        definition_index=None,
        block_index=0,
        block_kind="sanskrit_text",
        text_devanagari="सत् द्रव्यलक्षणम्।29।",
        reference_text="तत्त्वार्थसूत्र/5/29",
        references=[],
        hindi_translation="द्रव्य का लक्षण सत् है।",
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 2
    verse, anvay = targets
    assert verse.collection == "gatha_sanskrit"
    assert verse.source_text_kind == "devanagari"

    assert anvay.collection == "teeka_gatha_mapping"
    assert anvay.natural_key == "तत्त्वार्थसूत्र:सर्वार्थसिद्धि:अध्याय:5:सूत्र:29"
    assert anvay.gatha_natural_key == "तत्त्वार्थसूत्र:अध्याय:5:सूत्र:29"
    assert anvay.lang == "hin"
    assert anvay.text == "द्रव्य का लक्षण सत् है ॥२९॥"
    assert anvay.source_text_kind == "hindi_translation"
    assert anvay.match_block_kind == "hindi_text"


@pytest.mark.asyncio
async def test_gatha_stub_no_anvayartha_target_without_hindi_translation():
    """No teeka_gatha_mapping target when the block has no hindi_translation."""
    records = [
        _make_neo4j_record(
            stub_nk="समयसार:गाथा:1",
            stub_labels=["Gatha"],
            shastra_natural_key="समयसार",
        )
    ]
    driver = _make_driver(records)
    mongo = _make_mongo({
        "gatha_prakrit": {
            "natural_key": "समयसार:गाथा:1:prakrit",
            "text": [{"lang": "pra", "text": "णमो अरिहंताणं"}],
        },
        "teeka_gatha_mapping": {
            "natural_key": "समयसार:आत्मख्याति:1",
            "full_anyavaarth": "...",
        },
    })
    source = SourceBlock(
        kind="topic_extract",
        parent_natural_key="आत्मा",
        section_index=None,
        definition_index=None,
        block_index=0,
        block_kind="prakrit_gatha",
        text_devanagari="णमो अरिहंताणं",
        reference_text="समयसार गाथा 1",
        references=[],
        hindi_translation=None,
    )
    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    assert targets[0].collection == "gatha_prakrit"


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
async def test_compound_gatha_teeka_uses_full_compound_seg():
    """For a compound shastra (परमात्मप्रकाश), GathaTeeka Mongo NK must include
    the full compound suffix (अधिकार:1:गाथा:001), not just the trailing number."""
    shastra = "परमात्मप्रकाश"
    teeka_nk = f"{shastra}:टीका:0"
    gatha_nk = f"{shastra}:अधिकार:1:गाथा:001"
    records = [
        _make_neo4j_record(
            stub_nk=f"{teeka_nk}:अधिकार:1:गाथा:टीका:001",
            stub_labels=["GathaTeeka"],
            teeka_natural_key=teeka_nk,
            gatha_natural_key=gatha_nk,
            shastra_natural_key=shastra,
        )
    ]
    driver = _make_driver(records)
    expected_mongo_nk = f"{teeka_nk}:अधिकार:1:गाथा:001:टीका:san"
    mongo = _make_mongo({
        "gatha_teeka_sanskrit": {
            "natural_key": expected_mongo_nk,
            "text": [{"lang": "san", "text": "अथ"}],
        }
    })

    source = SourceBlock(
        kind="keyword_definition",
        parent_natural_key="आत्मा",
        section_index=0,
        definition_index=0,
        block_index=1,
        block_kind="sanskrit_text",
        text_devanagari="अथ",
        reference_text=None,
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    assert targets[0].natural_key == expected_mongo_nk
    assert targets[0].text == "अथ"


@pytest.mark.asyncio
async def test_compound_gatha_teeka_bhaavarth_uses_full_compound_seg():
    """For परमात्मप्रकाश, GathaTeekaBhaavarth Mongo NK must include the full
    compound suffix in front of :भावार्थ:hi."""
    shastra = "परमात्मप्रकाश"
    pub_nk = f"{shastra}:टीका:0:प्रकाशन:0"
    gatha_nk = f"{shastra}:अधिकार:2:गाथा:005"
    records = [
        _make_neo4j_record(
            stub_nk=f"{pub_nk}:अधिकार:2:गाथा:टीका:भावार्थ:005",
            stub_labels=["GathaTeekaBhaavarth"],
            publication_natural_key=pub_nk,
            gatha_natural_key=gatha_nk,
            shastra_natural_key=shastra,
        )
    ]
    driver = _make_driver(records)
    expected_mongo_nk = f"{pub_nk}:अधिकार:2:गाथा:005:भावार्थ:hi"
    mongo = _make_mongo({
        "gatha_teeka_bhaavarth_hindi": {
            "natural_key": expected_mongo_nk,
            "text": [{"lang": "hin", "text": "हिंदी भावार्थ"}],
        }
    })

    source = SourceBlock(
        kind="topic_extract",
        parent_natural_key=f"{shastra}:विषय:1",
        section_index=None,
        definition_index=None,
        block_index=0,
        block_kind="hindi_text",
        text_devanagari="हिंदी भावार्थ",
        reference_text=None,
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    assert targets[0].natural_key == expected_mongo_nk
    assert targets[0].text == "हिंदी भावार्थ"


@pytest.mark.asyncio
async def test_compound_gatha_zero_pad_fuzzy_fallback():
    """JainKosh emits stub NKs with raw values from citations (…:गाथा:12), but
    NJ ingestion zero-pads to 3 digits (…:गाथा:012). Resolver must find the
    padded Mongo doc when the unpadded stub NK misses."""
    shastra = "परमात्मप्रकाश"
    stub_nk = f"{shastra}:अधिकार:1:गाथा:12"
    padded_mongo_nk = f"{shastra}:अधिकार:1:गाथा:012:prakrit"
    records = [
        _make_neo4j_record(
            stub_nk=stub_nk,
            stub_labels=["Gatha"],
            shastra_natural_key=shastra,
        )
    ]
    driver = _make_driver(records)
    # Only the padded NK exists in Mongo. The first lookup (unpadded) misses;
    # the fuzzy fallback must hit.
    class _PaddedOnly:
        def __getitem__(self, name):
            class _Col:
                async def find_one(self, query):
                    if query.get("natural_key") == padded_mongo_nk:
                        return {"natural_key": padded_mongo_nk,
                                "text": [{"lang": "pra", "text": "अप्पा"}]}
                    return None
            return _Col()
    mongo = _PaddedOnly()

    source = SourceBlock(
        kind="topic_extract",
        parent_natural_key=f"{shastra}:विषय:1",
        section_index=None,
        definition_index=None,
        block_index=0,
        block_kind="prakrit_gatha",
        text_devanagari="अप्पा",
        reference_text=None,
        references=[],
    )

    targets = await resolve_targets(driver, mongo, source)
    assert len(targets) == 1
    assert targets[0].natural_key == padded_mongo_nk
    assert targets[0].status_hint is None
    assert targets[0].text == "अप्पा"


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
