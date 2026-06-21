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
    count_displayable_extract_blocks,
    extract_references,
    hydrate_topic_extracts_hi,
    main_reference_for_block,
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

        def aggregate(self, pipeline: list[dict]) -> FakeCursor:
            # Minimal interpreter for count_displayable_extract_blocks' pipeline:
            # match $in → count displayable blocks per doc → group total.
            # Mirrors the intended semantics (real $filter expr is covered by the
            # query/core-service endpoint tests against a real Mongo).
            from jain_kb_common.hydration.blocks import EXCLUDED_BLOCK_KINDS
            nks = pipeline[0]["$match"]["natural_key"]["$in"]
            rows = []
            for d in self._data:
                if d.get("natural_key") not in nks:
                    continue
                n = 0
                for b in d.get("blocks", []):
                    if b.get("kind", "") in EXCLUDED_BLOCK_KINDS:
                        continue
                    if (b.get("text_devanagari") or "") or (b.get("hindi_translation") or ""):
                        n += 1
                rows.append({"_id": d["natural_key"], "total": n})
            return FakeCursor(rows)

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
                # Sanskrit verse: original in text_devanagari, Hindi meaning in hindi_translation.
                {"kind": "sanskrit_text", "text_devanagari": "आत्मसंस्कृतम्।", "hindi_translation": "आत्मा का संस्कृत अर्थ।"},
                # see_also is a pointer with no usable text → excluded.
                {"kind": "see_also", "text_devanagari": "", "target_keyword": "मोक्ष"},
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
async def test_definitions_include_translations_exclude_see_also() -> None:
    """Hindi prose + the Hindi meaning of sanskrit/prakrit verse are returned;
    the raw sanskrit and the see_also pointer are not."""
    mongo = _make_mongo([_DEF_DOC_MIXED])
    result = await hydrate_definitions_hi(mongo, [_KW_NK])
    blocks = result[_KW_NK]
    assert len(blocks) == 2  # hindi_text + sanskrit translation; see_also dropped
    texts = {b["text_hi"] for b in blocks}
    assert "यह आत्मा का हिंदी विवरण है।" in texts
    assert "आत्मा का संस्कृत अर्थ।" in texts  # hindi_translation, not the raw verse
    assert not any("आत्मसंस्कृतम्" in t for t in texts), "raw sanskrit leaked instead of its translation"


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
        # Sanskrit verse: original in text_devanagari, Hindi meaning in hindi_translation.
        {"kind": "sanskrit_text", "text_devanagari": "द्रव्यं स्वतन्त्रम्।", "hindi_translation": "द्रव्य स्वतंत्र है।", "references": []},
        # Prakrit gatha likewise carries its Hindi meaning in hindi_translation.
        {"kind": "prakrit_gatha", "text_devanagari": "दव्वं सतंतं।", "hindi_translation": "जो है सो है।", "references": []},
        # see_also is a pointer with no usable text → excluded.
        {"kind": "see_also", "text_devanagari": "", "target_keyword": "गुण", "references": []},
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
async def test_extracts_include_translations_exclude_see_also() -> None:
    """Hindi prose + the Hindi meaning of sanskrit/prakrit verse are returned;
    the raw sanskrit verse and the see_also pointer are not."""
    mongo = _make_mongo([_EXTRACT_DOC_MIXED])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    blocks = result[_TOPIC_NK]
    texts = [b["text_hi"] for b in blocks]
    assert len(blocks) == 3  # hindi_text + sanskrit translation + gatha translation; see_also dropped
    assert any("द्रव्य का हिंदी" in t for t in texts)
    assert any("द्रव्य स्वतंत्र है।" in t for t in texts)  # sanskrit translation
    assert any("जो है सो है" in t for t in texts)  # gatha translation
    assert not any("द्रव्यं स्वतन्त्रम्" in t for t in texts), "raw sanskrit leaked instead of its translation"


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
    # idx0 hindi_text, idx1 sanskrit (translation), idx2 prakrit_gatha (translation), idx3 see_also
    result = await hydrate_topic_extracts_hi(
        mongo, [_TOPIC_NK], block_index_per_topic={_TOPIC_NK: 2}
    )
    blocks = result[_TOPIC_NK]
    assert len(blocks) == 1
    assert blocks[0]["block_index"] == 2
    assert "जो है सो है" in blocks[0]["text_hi"]


@pytest.mark.asyncio
async def test_extracts_block_index_per_topic_excluded_kind_skipped() -> None:
    """block_index_per_topic pointing to a no-text block (see_also) returns empty."""
    mongo = _make_mongo([_EXTRACT_DOC_MIXED])
    # Index 3 is see_also — must be filtered
    result = await hydrate_topic_extracts_hi(
        mongo, [_TOPIC_NK], block_index_per_topic={_TOPIC_NK: 3}
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


# ---------------------------------------------------------------------------
# main_reference_for_block tests
# ---------------------------------------------------------------------------

_BLOCK_WITH_MIXED_REFS = {
    "kind": "hindi_text",
    "text_devanagari": "बहुसंदर्भ पाठ।",
    "references": [
        # inline ref first — must be skipped in favour of the non-inline one
        {
            "shastra_name": "समाधिशतक",
            "teeka_name": "",
            "inline_reference": True,
            "resolved_fields": [{"field": "गाथा", "value": 4}],
        },
        # first non-inline resolved ref → the "main" reference
        {
            "shastra_name": "मोक्ष पाहुड़",
            "teeka_name": "",
            "inline_reference": False,
            "resolved_fields": [{"field": "गाथा", "value": 8}],
        },
        # another non-inline ref — not the main one
        {
            "shastra_name": "द्रव्यसंग्रह",
            "teeka_name": "टीका",
            "inline_reference": False,
            "resolved_fields": [{"field": "गाथा", "value": 57}, {"field": "पृष्ठ", "value": 267}],
        },
    ],
}


def test_main_reference_picks_first_non_inline() -> None:
    """main_reference_for_block returns pick_refs_to_show()[0] with full fields."""
    mr = main_reference_for_block(_BLOCK_WITH_MIXED_REFS)
    assert mr is not None
    assert mr["shastra_name"] == "मोक्ष पाहुड़"
    assert mr["teeka_name"] is None  # empty teeka normalised to None
    assert mr["resolved_fields"] == [{"field": "गाथा", "value": 8}]


def test_main_reference_none_when_no_refs() -> None:
    assert main_reference_for_block({"kind": "hindi_text", "references": []}) is None


def test_main_reference_keeps_all_resolved_fields() -> None:
    """All resolved_fields (incl. पुस्तक/पृष्ठ/पंक्ति) are preserved — filtering
    is the presentation layer's job, not the hydrator's."""
    block = {
        "kind": "hindi_text",
        "references": [
            {
                "shastra_name": "धवला",
                "teeka_name": "",
                "inline_reference": False,
                "resolved_fields": [
                    {"field": "पुस्तक", "value": 13},
                    {"field": "धवलासूत्र", "value": 50},
                    {"field": "पृष्ठ", "value": 282},
                    {"field": "पंक्ति", "value": 11},
                ],
            }
        ],
    }
    mr = main_reference_for_block(block)
    assert [f["field"] for f in mr["resolved_fields"]] == ["पुस्तक", "धवलासूत्र", "पृष्ठ", "पंक्ति"]


@pytest.mark.asyncio
async def test_extracts_include_main_reference() -> None:
    """hydrate_topic_extracts_hi attaches main_reference per block."""
    mongo = _make_mongo([_EXTRACT_DOC_WITH_REFS])
    result = await hydrate_topic_extracts_hi(mongo, [_TOPIC_NK])
    for block in result[_TOPIC_NK]:
        assert "main_reference" in block


# ---------------------------------------------------------------------------
# count_displayable_extract_blocks tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_count_displayable_excludes_see_also_and_table() -> None:
    """Only modal-renderable blocks count: see_also/table and text-less blocks
    are excluded so a pointer-only topic counts 0 (no false 'पढ़ें')."""
    docs = [
        {  # 2 displayable (hindi_text + sanskrit translation), see_also dropped
            "natural_key": "त1",
            "blocks": [
                {"kind": "hindi_text", "text_devanagari": "पाठ।"},
                {"kind": "sanskrit_text", "text_devanagari": "श्लोक।", "hindi_translation": "अर्थ।"},
                {"kind": "see_also", "text_devanagari": "", "target_keyword": "x"},
            ],
        },
        {  # all see_also → 0 (the बहिरात्मा-style container)
            "natural_key": "त2",
            "blocks": [
                {"kind": "see_also", "text_devanagari": "", "target_keyword": "a"},
                {"kind": "see_also", "text_devanagari": "", "target_keyword": "b"},
            ],
        },
    ]
    mongo = _make_mongo(docs)
    counts = await count_displayable_extract_blocks(mongo, ["त1", "त2"])
    assert counts["त1"] == 2
    assert counts["त2"] == 0


@pytest.mark.asyncio
async def test_count_displayable_empty_input() -> None:
    assert await count_displayable_extract_blocks(_make_mongo([]), []) == {}


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


# ============================================================
# hydrate_tables_for_parent / hydrate_table_full tests
# ============================================================

from jain_kb_common.hydration.tables import (  # noqa: E402
    hydrate_tables_for_parent,
    hydrate_table_full,
)
from unittest.mock import AsyncMock, MagicMock  # noqa: E402


def _make_pg_with_rows(rows: list) -> object:
    """Minimal async SQLAlchemy session mock."""

    class FakeResult:
        def __init__(self, data):
            self._data = data

        def scalars(self):
            return self

        def scalar_one_or_none(self):
            return self._data[0] if self._data else None

        def __iter__(self):
            return iter(self._data)

    class FakeSession:
        async def execute(self, stmt):
            return FakeResult(rows)

    return FakeSession()


def _make_mongo_tables(docs: list[dict]) -> object:
    class FakeCollection:
        def __init__(self, data):
            self._data = data

        async def find_one(self, query):
            nk = query.get("natural_key")
            for d in self._data:
                if d.get("natural_key") == nk:
                    return dict(d)
            return None

    class FakeDB:
        def __init__(self, data):
            self._data = data

        def __getitem__(self, _name):
            return FakeCollection(self._data)

    return FakeDB(docs)


class FakeTableRow:
    """Minimal PG Table row substitute for hydration tests."""

    def __init__(self, natural_key, seq, parent_natural_key="parent:topic",
                 parent_kind="Topic", source="jainkosh", source_url=None,
                 caption=None, row_id="00000000-0000-0000-0000-000000000001"):
        self.natural_key = natural_key
        self.seq = seq
        self.parent_natural_key = parent_natural_key
        self.parent_kind = parent_kind
        self.source = source
        self.source_url = source_url
        self.caption = caption or []
        self.id = row_id

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, v):
        self._source = v


_PARENT_NK = "द्रव्य:षट्द्रव्य"
_TABLE_NK = "table:jainkosh:द्रव्य:षट्द्रव्य:01"

_MONGO_DOC = {
    "natural_key": _TABLE_NK,
    "raw_html": "<table></table>",
    "cells": [["a", "b"]],
    "header_rows": 1,
    "plaintext": "a b",
    "mentioned_keyword_natural_keys": ["द्रव्य"],
    "mentioned_topic_natural_keys": [],
}


@pytest.mark.asyncio
async def test_hydrate_tables_for_parent_returns_summaries() -> None:
    rows = [
        FakeTableRow(_TABLE_NK, seq=1, parent_natural_key=_PARENT_NK),
        FakeTableRow("table:jainkosh:द्रव्य:षट्द्रव्य:02", seq=2, parent_natural_key=_PARENT_NK),
    ]
    pg = _make_pg_with_rows(rows)
    mongo = _make_mongo_tables([])
    result = await hydrate_tables_for_parent(pg, mongo, parent_natural_key=_PARENT_NK)
    assert len(result) == 2
    assert result[0].natural_key == _TABLE_NK
    assert result[0].seq == 1
    assert result[1].seq == 2


@pytest.mark.asyncio
async def test_hydrate_tables_for_parent_empty() -> None:
    pg = _make_pg_with_rows([])
    mongo = _make_mongo_tables([])
    result = await hydrate_tables_for_parent(pg, mongo, parent_natural_key="nonexistent")
    assert result == []


@pytest.mark.asyncio
async def test_hydrate_table_full_merges_pg_and_mongo() -> None:
    row = FakeTableRow(_TABLE_NK, seq=1, parent_natural_key=_PARENT_NK)
    pg = _make_pg_with_rows([row])
    mongo = _make_mongo_tables([_MONGO_DOC])
    result = await hydrate_table_full(pg, mongo, natural_key=_TABLE_NK)
    assert result is not None
    assert result.natural_key == _TABLE_NK
    assert result.raw_html == "<table></table>"
    assert result.cells == [["a", "b"]]
    assert result.header_rows == 1
    assert result.plaintext == "a b"
    assert result.mentioned_keyword_natural_keys == ["द्रव्य"]


@pytest.mark.asyncio
async def test_hydrate_table_full_returns_none_when_pg_missing() -> None:
    pg = _make_pg_with_rows([])
    mongo = _make_mongo_tables([_MONGO_DOC])
    result = await hydrate_table_full(pg, mongo, natural_key="nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_hydrate_table_full_empty_cells_when_mongo_missing() -> None:
    row = FakeTableRow(_TABLE_NK, seq=1, parent_natural_key=_PARENT_NK)
    pg = _make_pg_with_rows([row])
    mongo = _make_mongo_tables([])
    result = await hydrate_table_full(pg, mongo, natural_key=_TABLE_NK)
    assert result is not None
    assert result.cells == []
    assert result.raw_html == ""
