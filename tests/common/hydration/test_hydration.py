"""Unit tests for jain_kb_common.hydration — no DB required."""
from __future__ import annotations

import sys
import os

import pytest
import pytest_asyncio

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),  # repo root
)
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)

from jain_kb_common.hydration.definitions import hydrate_definitions_hi  # noqa: E402
from jain_kb_common.hydration.topic_extracts import (  # noqa: E402
    extract_references,
    hydrate_topic_extracts_hi,
)

# ---------------------------------------------------------------------------
# Minimal async mongo mock
# ---------------------------------------------------------------------------

def _make_mongo(docs: list[dict]) -> object:
    class FakeCursor:
        def __init__(self, data: list[dict]) -> None:
            self._iter = iter(data)

        def __aiter__(self) -> "FakeCursor":
            return self

        async def __anext__(self) -> dict:
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    class FakeCollection:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def find(self, query: dict, projection: dict | None = None) -> FakeCursor:
            nks = query.get("natural_key", {}).get("$in", [])
            filtered = [d for d in self._data if d.get("natural_key") in nks]
            return FakeCursor(filtered)

    class FakeDB:
        def __init__(self, data: list[dict]) -> None:
            self._data = data

        def __getitem__(self, _name: str) -> FakeCollection:
            return FakeCollection(self._data)

    return FakeDB(docs)


# ============================================================
# hydrate_definitions_hi tests
# ============================================================

_KW_NK = "आत्मा"

_DEF_DOC_MIXED = {
    "natural_key": _KW_NK,
    "page_sections": [{
        "definitions": [{
            "blocks": [
                {"kind": "hindi_text", "text_devanagari": "यह आत्मा का हिंदी विवरण है।"},
                {"kind": "sanskrit_text", "text_devanagari": "आत्मा संस्कृत पाठ।"},
                {"kind": "hindi_gatha", "text_devanagari": "आत्मा गाथा पाठ।"},
            ]
        }]
    }]
}

_DEF_DOC_LONG = {
    "natural_key": _KW_NK,
    "page_sections": [{
        "definitions": [{
            "blocks": [
                {"kind": "hindi_text", "text_devanagari": "अ" * 2000},
            ]
        }]
    }]
}

_DEF_DOC_MULTI = {
    "natural_key": _KW_NK,
    "page_sections": [{
        "definitions": [{
            "blocks": [
                {"kind": "hindi_text", "text_devanagari": "पहला हिंदी खंड।"},
                {"kind": "hindi_text", "text_devanagari": "दूसरा हिंदी खंड।"},
                {"kind": "hindi_text", "text_devanagari": "तीसरा हिंदी खंड।"},
            ]
        }]
    }]
}


@pytest.mark.asyncio
async def test_definitions_hi_only_hindi_blocks() -> None:
    """Only hindi_text and hindi_gatha blocks are returned; sanskrit_text excluded."""
    mongo = _make_mongo([_DEF_DOC_MIXED])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    blocks = result[_KW_NK]
    assert len(blocks) == 2
    texts = {b["text_hi"] for b in blocks}
    assert "यह आत्मा का हिंदी विवरण है।" in texts
    assert "आत्मा गाथा पाठ।" in texts
    assert not any("संस्कृत" in b["text_hi"] for b in blocks)


@pytest.mark.asyncio
async def test_definitions_truncation_with_ellipsis() -> None:
    """Text longer than 1500 chars is truncated and suffixed with '…'."""
    mongo = _make_mongo([_DEF_DOC_LONG])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    blocks = result[_KW_NK]
    assert len(blocks) == 1
    text = blocks[0]["text_hi"]
    assert text.endswith("…"), "truncated text must end with '…'"
    assert len(text) == 1501  # 1500 chars + one '…' character


@pytest.mark.asyncio
async def test_definitions_truncation_marker_only_once() -> None:
    """The '…' suffix is appended exactly once, not doubled."""
    mongo = _make_mongo([_DEF_DOC_LONG])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    text = result[_KW_NK][0]["text_hi"]
    assert text.count("…") == 1


@pytest.mark.asyncio
async def test_definitions_no_truncation_when_short() -> None:
    """Short text is returned as-is without the ellipsis marker."""
    mongo = _make_mongo([_DEF_DOC_MIXED])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    for block in result[_KW_NK]:
        assert "…" not in block["text_hi"]


@pytest.mark.asyncio
async def test_definitions_cap_per_keyword() -> None:
    """cap_per_keyword=1 returns only the first Hindi block."""
    mongo = _make_mongo([_DEF_DOC_MULTI])
    result = await hydrate_definitions_hi(mongo, [_KW_NK], cap_per_keyword=1)
    assert len(result[_KW_NK]) == 1
    assert result[_KW_NK][0]["text_hi"] == "पहला हिंदी खंड।"


@pytest.mark.asyncio
async def test_definitions_cap_zero_means_no_cap() -> None:
    """cap_per_keyword=0 returns all Hindi blocks."""
    mongo = _make_mongo([_DEF_DOC_MULTI])
    result = await hydrate_definitions_hi(mongo, [_KW_NK], cap_per_keyword=0)
    assert len(result[_KW_NK]) == 3


@pytest.mark.asyncio
async def test_definitions_source_natural_key_present() -> None:
    """Each block has source_natural_key == the keyword's natural_key."""
    mongo = _make_mongo([_DEF_DOC_MIXED])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    for block in result[_KW_NK]:
        assert block["source_natural_key"] == _KW_NK


@pytest.mark.asyncio
async def test_definitions_block_index_monotone() -> None:
    """block_index increases across returned Hindi blocks."""
    mongo = _make_mongo([_DEF_DOC_MULTI])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    indices = [b["block_index"] for b in result[_KW_NK]]
    assert indices == sorted(indices)
    assert len(set(indices)) == len(indices)  # unique


@pytest.mark.asyncio
async def test_definitions_missing_keyword_not_in_result() -> None:
    """If a keyword has no Mongo doc, it does not appear in the result."""
    mongo = _make_mongo([])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    assert _KW_NK not in result


# ============================================================
# hydrate_topic_extracts_hi tests
# ============================================================

_TOPIC_NK = "द्रव्य/स्वतंत्रता/लक्षण"

_EXTRACT_DOC_MIXED = {
    "natural_key": _TOPIC_NK,
    "blocks": [
        {"kind": "hindi_text", "text_devanagari": "द्रव्य का हिंदी विवरण।", "references": []},
        {"kind": "sanskrit_text", "text_devanagari": "द्रव्यं स्वतन्त्रम्।", "references": []},
        {"kind": "hindi_gatha", "text_devanagari": "जो है सो है।", "references": []},
    ],
}

_EXTRACT_DOC_LONG = {
    "natural_key": _TOPIC_NK,
    "blocks": [
        {"kind": "hindi_text", "text_devanagari": "क" * 2000, "references": []},
    ],
}

_EXTRACT_DOC_MULTI = {
    "natural_key": _TOPIC_NK,
    "blocks": [
        {"kind": "hindi_text", "text_devanagari": "पहला।", "references": []},
        {"kind": "hindi_gatha", "text_devanagari": "दूसरा।", "references": []},
        {"kind": "hindi_text", "text_devanagari": "तीसरा।", "references": []},
    ],
}

_EXTRACT_DOC_WITH_REFS = {
    "natural_key": _TOPIC_NK,
    "blocks": [
        {
            "kind": "hindi_text",
            "text_devanagari": "संदर्भ सहित पाठ।",
            "references": [
                {
                    "resolved_fields": [
                        {"field": "shastra", "value": "samaysaar"},
                        {"field": "gatha_number", "value": "6"},
                    ]
                }
            ],
        },
        {
            "kind": "hindi_text",
            "text_devanagari": "दूसरे संदर्भ के साथ।",
            "references": [
                {
                    "resolved_fields": [
                        {"field": "shastra", "value": "pravachansaar"},
                        {"field": "gatha_number", "value": "12"},
                    ]
                }
            ],
        },
    ],
}


@pytest.mark.asyncio
async def test_extracts_hi_only_hindi_blocks() -> None:
    """Sanskrit blocks must not appear in topic extracts."""
    mongo = _make_mongo([_EXTRACT_DOC_MIXED])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    blocks = result[_TOPIC_NK]
    texts = [b["text_hi"] for b in blocks]
    assert any("द्रव्य का हिंदी" in t for t in texts)
    assert any("जो है सो है" in t for t in texts)
    assert not any("द्रव्यं स्वतन्त्रम्" in t for t in texts), "Sanskrit block leaked"


@pytest.mark.asyncio
async def test_extracts_truncation_with_ellipsis() -> None:
    """Long text is truncated to 1500 chars with '…' suffix."""
    mongo = _make_mongo([_EXTRACT_DOC_LONG])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    text = result[_TOPIC_NK][0]["text_hi"]
    assert text.endswith("…")
    assert len(text) == 1501


@pytest.mark.asyncio
async def test_extracts_truncation_marker_only_once() -> None:
    """'…' appended exactly once on truncation."""
    mongo = _make_mongo([_EXTRACT_DOC_LONG])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    assert result[_TOPIC_NK][0]["text_hi"].count("…") == 1


@pytest.mark.asyncio
async def test_extracts_cap_per_topic() -> None:
    """cap_per_topic=1 keeps only the first Hindi block."""
    mongo = _make_mongo([_EXTRACT_DOC_MULTI])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK], cap_per_topic=1)
    assert len(result[_TOPIC_NK]) == 1
    assert result[_TOPIC_NK][0]["text_hi"] == "पहला।"


@pytest.mark.asyncio
async def test_extracts_cap_zero_means_no_cap() -> None:
    """cap_per_topic=0 returns all Hindi blocks."""
    mongo = _make_mongo([_EXTRACT_DOC_MULTI])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK], cap_per_topic=0)
    assert len(result[_TOPIC_NK]) == 3


@pytest.mark.asyncio
async def test_extracts_block_index_per_topic_slicing() -> None:
    """block_index_per_topic slices to only that absolute block index."""
    mongo = _make_mongo([_EXTRACT_DOC_MIXED])
    # Block 0 = hindi_text (idx=0), Block 1 = sanskrit (idx=1, skipped), Block 2 = hindi_gatha (idx=2)
    result = await hydrate_topic_extracts_hi(
        mongo, [_TOPIC_NK], block_index_per_topic={_TOPIC_NK: 2}
    )
    blocks = result[_TOPIC_NK]
    assert len(blocks) == 1
    assert blocks[0]["block_index"] == 2
    assert "जो है सो है" in blocks[0]["text_hi"]


@pytest.mark.asyncio
async def test_extracts_block_index_per_topic_non_hindi_skipped() -> None:
    """block_index_per_topic pointing to a sanskrit block returns empty."""
    mongo = _make_mongo([_EXTRACT_DOC_MIXED])
    # Index 1 is sanskrit_text — must be filtered
    result = await hydrate_topic_extracts_hi(
        mongo, [_TOPIC_NK], block_index_per_topic={_TOPIC_NK: 1}
    )
    assert result.get(_TOPIC_NK, []) == []


@pytest.mark.asyncio
async def test_extracts_per_block_references_inline() -> None:
    """Each block dict includes a 'references' key."""
    mongo = _make_mongo([_EXTRACT_DOC_WITH_REFS])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    for block in result[_TOPIC_NK]:
        assert "references" in block, "references key missing from block"


@pytest.mark.asyncio
async def test_extracts_references_populated_correctly() -> None:
    """References are extracted per block, not mixed across blocks."""
    mongo = _make_mongo([_EXTRACT_DOC_WITH_REFS])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    blocks = result[_TOPIC_NK]
    assert len(blocks) == 2
    # First block refs samaysaar:6
    assert blocks[0]["references"][0]["shastra_natural_key"] == "samaysaar"
    assert blocks[0]["references"][0]["gatha_number"] == 6
    # Second block refs pravachansaar:12
    assert blocks[1]["references"][0]["shastra_natural_key"] == "pravachansaar"
    assert blocks[1]["references"][0]["gatha_number"] == 12


@pytest.mark.asyncio
async def test_extracts_missing_topic_not_in_result() -> None:
    """Topic not in Mongo is absent from result dict."""
    mongo = _make_mongo([])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    assert _TOPIC_NK not in result


# ============================================================
# extract_references tests (pure function)
# ============================================================

def test_extract_references_basic() -> None:
    """Reference fields are correctly extracted from resolved_fields."""
    blocks = [
        {
            "references": [{
                "resolved_fields": [
                    {"field": "shastra", "value": "samaysaar"},
                    {"field": "gatha_number", "value": "6"},
                    {"field": "teeka", "value": "amritchandra_atmakhyati"},
                    {"field": "page_number", "value": "42"},
                ]
            }]
        }
    ]
    refs = extract_references(blocks)
    assert len(refs) == 1
    assert refs[0]["shastra_natural_key"] == "samaysaar"
    assert refs[0]["gatha_number"] == 6
    assert refs[0]["teeka_natural_key"] == "amritchandra_atmakhyati"
    assert refs[0]["page_number"] == 42


def test_extract_references_deduplication() -> None:
    """Duplicate references across blocks appear only once."""
    ref_payload = {
        "resolved_fields": [
            {"field": "shastra", "value": "samaysaar"},
            {"field": "gatha_number", "value": "6"},
        ]
    }
    blocks = [
        {"references": [ref_payload]},
        {"references": [ref_payload]},
    ]
    refs = extract_references(blocks)
    assert len(refs) == 1


def test_extract_references_document_order() -> None:
    """References appear in document order (first occurrence wins)."""
    blocks = [
        {"references": [{"resolved_fields": [{"field": "shastra", "value": "a"}]}]},
        {"references": [{"resolved_fields": [{"field": "shastra", "value": "b"}]}]},
    ]
    refs = extract_references(blocks)
    assert [r["shastra_natural_key"] for r in refs] == ["a", "b"]


def test_extract_references_empty_string_fields_become_none() -> None:
    """Empty string shastra / teeka are normalised to None."""
    blocks = [
        {"references": [{"resolved_fields": [{"field": "shastra", "value": ""}]}]},
    ]
    refs = extract_references(blocks)
    # All-None key → nothing to store
    assert refs == []


def test_extract_references_partial_fields() -> None:
    """References with only some fields populated are handled."""
    blocks = [
        {"references": [{"resolved_fields": [{"field": "gatha_number", "value": "3"}]}]},
    ]
    refs = extract_references(blocks)
    assert len(refs) == 1
    assert refs[0]["gatha_number"] == 3
    assert refs[0]["shastra_natural_key"] is None
    assert refs[0]["teeka_natural_key"] is None
    assert refs[0]["page_number"] is None


def test_extract_references_no_references_key() -> None:
    """Blocks without 'references' key are silently skipped."""
    blocks = [{"kind": "hindi_text", "text_devanagari": "कुछ पाठ।"}]
    refs = extract_references(blocks)
    assert refs == []


def test_extract_references_empty_blocks() -> None:
    """Empty block list returns empty list."""
    assert extract_references([]) == []
