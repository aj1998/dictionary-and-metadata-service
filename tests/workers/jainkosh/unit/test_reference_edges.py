"""Unit tests for reference_edges.build_reference_edges."""

from __future__ import annotations

from datetime import datetime

import pytest

from workers.ingestion.jainkosh.config import (
    DevanagariNormalizationConfig,
    JainkoshConfig,
    ReferenceEntityKeywordsConfig,
)
from workers.ingestion.jainkosh.models import Block, Reference, ResolvedField
from workers.ingestion.jainkosh.parse_reference import (
    PublisherRegistry,
    ShastraEntry,
    ShastraRegistry,
    parse_format_string,
)
from workers.ingestion.jainkosh.reference_edges import (
    _first_value,
    _pick_reference,
    build_reference_edges,
)


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _make_norm_config():
    return DevanagariNormalizationConfig(enabled=False, substitutions=[])


def _make_registry():
    """Three-entry stub registry: shastra / teeka / publication."""
    norm = _make_norm_config()
    registry = ShastraRegistry()
    from workers.ingestion.jainkosh.parse_reference import _normalise

    entries = [
        ShastraEntry(
            shastra_name="समयसार",
            alternate_names=[],
            short_form="",
            format_str="गाथा",
            format_groups=parse_format_string("गाथा"),
            publisher="",
            type="shastra",
        ),
        ShastraEntry(
            shastra_name="नियमसार",
            alternate_names=[],
            short_form="",
            format_str="गाथा",
            format_groups=parse_format_string("गाथा"),
            publisher="",
            type="teeka",
        ),
        ShastraEntry(
            shastra_name="कार्तिकेयानुप्रेक्षा",
            alternate_names=[],
            short_form="",
            format_str="गाथा",
            format_groups=parse_format_string("गाथा"),
            publisher="अनन्तकीर्ति ग्रन्थमाला",
            type="publication",
        ),
    ]
    for entry in entries:
        registry.entries.append(entry)
        registry._by_primary[_normalise(entry.shastra_name, norm)] = entry

    return registry


def _make_publisher_registry():
    pub = PublisherRegistry()
    pub._by_name["अनन्तकीर्ति ग्रन्थमाला"] = "1"
    return pub


def _make_config(registry=None, publisher_registry=None) -> JainkoshConfig:
    from workers.ingestion.jainkosh.config import load_config
    cfg = load_config()
    cfg.shastra_registry = registry or _make_registry()
    cfg.publisher_registry = publisher_registry or _make_publisher_registry()
    return cfg


def _rf(field: str, value) -> ResolvedField:
    return ResolvedField(field=field, value=value)


def _block(
    kind: str,
    shastra_name: str,
    resolved_fields: list[ResolvedField],
    teeka_name: str = "",
    inline_reference: bool = False,
    extra_refs: list[Reference] | None = None,
) -> Block:
    ref = Reference(
        text="test",
        inline_reference=inline_reference,
        shastra_name=shastra_name,
        teeka_name=teeka_name,
        resolved_fields=resolved_fields,
    )
    refs = [ref]
    if extra_refs:
        refs.extend(extra_refs)
    return Block(kind=kind, references=refs)


TOPIC_TARGET = {"label": "Topic", "key": "आत्मा:कोई-उपशीर्षक"}
KW_TARGET = {"label": "Keyword", "key": "आत्मा"}


# ---------------------------------------------------------------------------
# _pick_reference tests
# ---------------------------------------------------------------------------

def test_pick_reference_empty():
    assert _pick_reference([]) is None


def test_pick_reference_first_non_inline():
    r1 = Reference(text="a", inline_reference=True)
    r2 = Reference(text="b", inline_reference=False)
    r3 = Reference(text="c", inline_reference=False)
    assert _pick_reference([r1, r2, r3]) is r2


def test_pick_reference_all_inline():
    r1 = Reference(text="a", inline_reference=True)
    r2 = Reference(text="b", inline_reference=True)
    assert _pick_reference([r1, r2]) is r1


# ---------------------------------------------------------------------------
# _first_value tests
# ---------------------------------------------------------------------------

def test_first_value_found():
    rf = [_rf("गाथा", 6), _rf("पृष्ठ", 10)]
    assert _first_value(rf, ["गाथा", "श्लोक"]) == 6


def test_first_value_alias():
    rf = [_rf("श्लोक", 29)]
    assert _first_value(rf, ["गाथा", "श्लोक", "सूत्र"]) == 29


def test_first_value_not_int():
    rf = [_rf("गाथा", "5-6")]
    assert _first_value(rf, ["गाथा"]) is None


def test_first_value_missing():
    rf = [_rf("पृष्ठ", 5)]
    assert _first_value(rf, ["गाथा", "श्लोक"]) is None


# ---------------------------------------------------------------------------
# shastra-type gatha edges
# ---------------------------------------------------------------------------

def test_shastra_sanskrit_gatha_gatha_edge():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 6)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    e = edges[0]
    assert e["type"] == "MENTIONS_TOPIC"
    assert e["from"] == {"label": "Gatha", "key": "समयसार:गाथा:6"}
    assert e["to"] == TOPIC_TARGET
    assert e["props"]["weight"] == 1.0
    assert e["props"]["source"] == "jainkosh"
    assert "pankti" not in e["props"]


def test_shastra_any_block_kind_uses_gatha():
    cfg = _make_config()
    for kind in ("sanskrit_text", "prakrit_text", "hindi_text", "hindi_gatha"):
        b = _block(kind, "समयसार", [_rf("गाथा", 10)])
        edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
        assert len(edges) == 1
        assert edges[0]["from"]["label"] == "Gatha"
        assert edges[0]["from"]["key"] == "समयसार:गाथा:10"


def test_shastra_keyword_alias_shlok():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("श्लोक", 29)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["key"] == "समयसार:गाथा:29"


# ---------------------------------------------------------------------------
# teeka-type gatha edges
# ---------------------------------------------------------------------------

def test_teeka_gatha_kind_uses_gatha():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "नियमसार", [_rf("गाथा", 6)], teeka_name="आत्मख्याती")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Gatha", "key": "नियमसार:गाथा:6"}


def test_teeka_text_kind_uses_gathateeka():
    cfg = _make_config()
    b = _block("sanskrit_text", "नियमसार", [_rf("गाथा", 6)], teeka_name="आत्मख्याती")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "GathaTeeka", "key": "नियमसार:आत्मख्याती:गाथा:टीका:6"}


def test_teeka_hindi_text_uses_gathateeka():
    cfg = _make_config()
    b = _block("hindi_text", "नियमसार", [_rf("गाथा", 6)], teeka_name="आत्मख्याती")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "GathaTeeka"


def test_teeka_missing_teeka_name_falls_back_to_default(caplog):
    cfg = _make_config()
    b = _block("sanskrit_text", "नियमसार", [_rf("गाथा", 6)], teeka_name="")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "GathaTeeka"
    assert edges[0]["from"]["key"] == "नियमसार:टीका:गाथा:टीका:6"


# ---------------------------------------------------------------------------
# publication-type edges
# ---------------------------------------------------------------------------

def test_publication_gatha_kind_uses_gatha():
    cfg = _make_config()
    b = _block("prakrit_gatha", "कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 6)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "Gatha"


def test_publication_sanskrit_text_uses_gathateeka():
    cfg = _make_config()
    b = _block("sanskrit_text", "कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 6)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "GathaTeeka"
    assert edges[0]["from"]["key"] == "कार्तिकेयानुप्रेक्षा:जयसेन:गाथा:टीका:6"


def test_publication_hindi_text_two_edges():
    cfg = _make_config()
    b = _block("hindi_text", "कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 6)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 2
    labels = {e["from"]["label"] for e in edges}
    assert labels == {"GathaTeeka", "GathaTeekaBhaavarth"}
    gt_edge = next(e for e in edges if e["from"]["label"] == "GathaTeekaBhaavarth")
    assert gt_edge["from"]["key"] == "कार्तिकेयानुप्रेक्षा:जयसेन:1:गाथा:टीका:भावार्थ:6"


# ---------------------------------------------------------------------------
# Kalash edges
# ---------------------------------------------------------------------------

def test_teeka_kalash_gatha_kind():
    cfg = _make_config()
    b = _block("prakrit_gatha", "नियमसार", [_rf("कलश", 3)], teeka_name="आत्मख्याती")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Kalash", "key": "नियमसार:आत्मख्याती:कलश:3"}


def test_publication_kalash_hindi_text():
    cfg = _make_config()
    b = _block("hindi_text", "कार्तिकेयानुप्रेक्षा", [_rf("कलश", 3)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "KalashBhaavarth", "key": "कार्तिकेयानुप्रेक्षा:जयसेन:1:कलश:भावार्थ:3"}


def test_teeka_kalash_sanskrit_text_kind():
    """teeka + sanskrit_text with कलश ref should emit Kalash (same key as *_gatha)."""
    cfg = _make_config()
    b = _block("sanskrit_text", "नियमसार", [_rf("कलश", 2)], teeka_name="आत्मख्याति")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Kalash", "key": "नियमसार:आत्मख्याति:कलश:2"}


def test_teeka_kalash_prakrit_text_kind():
    """teeka + prakrit_text with कलश ref should emit Kalash."""
    cfg = _make_config()
    b = _block("prakrit_text", "नियमसार", [_rf("कलश", 5)], teeka_name="आत्मख्याति")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Kalash", "key": "नियमसार:आत्मख्याति:कलश:5"}


def test_publication_kalash_sanskrit_text_kind():
    """publication + sanskrit_text with कलश ref → Kalash (same key as *_gatha).
    समयसार is registered as 'publication' but kalash verses appear as sanskrit_text blocks.
    """
    cfg = _make_config()
    b = _block("sanskrit_text", "कार्तिकेयानुप्रेक्षा", [_rf("कलश", 2)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Kalash", "key": "कार्तिकेयानुप्रेक्षा:जयसेन:कलश:2"}


def test_shastra_no_kalash_edge():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("कलश", 3)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


# ---------------------------------------------------------------------------
# Page edges
# ---------------------------------------------------------------------------

def test_publication_page_edge():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "कार्तिकेयानुप्रेक्षा", [_rf("पृष्ठ", 98)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Page", "key": "कार्तिकेयानुप्रेक्षा:जयसेन:1:पृष्ठ:98"}


def test_shastra_no_page_edge():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("पृष्ठ", 10)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_teeka_no_page_edge():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "नियमसार", [_rf("पृष्ठ", 10)], teeka_name="आत्मख्याती")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


# ---------------------------------------------------------------------------
# Composability: multiple edges from same block
# ---------------------------------------------------------------------------

def test_gatha_and_page_from_same_block():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 5), _rf("पृष्ठ", 98)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 2
    labels = {e["from"]["label"] for e in edges}
    assert "Gatha" in labels
    assert "Page" in labels


# ---------------------------------------------------------------------------
# पंक्ति surfaces as props.pankti
# ---------------------------------------------------------------------------

def test_pankti_in_props():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 6), _rf("पंक्ति", 5)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["props"]["pankti"] == 5


# ---------------------------------------------------------------------------
# Skip rules
# ---------------------------------------------------------------------------

def test_no_shastra_name_returns_empty():
    cfg = _make_config()
    ref = Reference(text="test", shastra_name=None)
    b = Block(kind="sanskrit_gatha", references=[ref])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_unknown_shastra_name_returns_empty():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "अज्ञात", [_rf("गाथा", 6)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_no_references_returns_empty():
    cfg = _make_config()
    b = Block(kind="sanskrit_gatha", references=[])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_no_gatha_value_returns_empty():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [])  # no resolved_fields
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_see_also_block_emits_no_ref_edges():
    cfg = _make_config()
    b = Block(kind="see_also", target_keyword="आत्मा")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


# ---------------------------------------------------------------------------
# CONTAINS_DEFINITION edge type
# ---------------------------------------------------------------------------

def test_contains_definition_edge_type():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 6)])
    edges = build_reference_edges(b, target=KW_TARGET, edge_type="CONTAINS_DEFINITION", config=cfg)
    assert len(edges) == 1
    assert edges[0]["type"] == "CONTAINS_DEFINITION"
    assert edges[0]["to"] == KW_TARGET


# ---------------------------------------------------------------------------
# Multiple references: picks first non-inline
# ---------------------------------------------------------------------------

def test_multiple_refs_picks_first_non_inline():
    """Non-inline ref is main; inline ref is processed as remaining (shastra → Gatha)."""
    cfg = _make_config()
    inline_ref = Reference(text="inline", inline_reference=True, shastra_name="समयसार",
                           resolved_fields=[_rf("गाथा", 99)])
    non_inline_ref = Reference(text="non-inline", inline_reference=False, shastra_name="समयसार",
                               resolved_fields=[_rf("गाथा", 6)])
    b = Block(kind="sanskrit_gatha", references=[inline_ref, non_inline_ref])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 2
    keys = {e["from"]["key"] for e in edges}
    assert "समयसार:गाथा:6" in keys   # main
    assert "समयसार:गाथा:99" in keys  # inline (shastra → same Gatha logic)


def test_all_inline_refs_picks_first():
    """First inline is main; second inline is processed as remaining (shastra → Gatha)."""
    cfg = _make_config()
    r1 = Reference(text="a", inline_reference=True, shastra_name="समयसार",
                   resolved_fields=[_rf("गाथा", 1)])
    r2 = Reference(text="b", inline_reference=True, shastra_name="समयसार",
                   resolved_fields=[_rf("गाथा", 2)])
    b = Block(kind="sanskrit_gatha", references=[r1, r2])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 2
    keys = {e["from"]["key"] for e in edges}
    assert "समयसार:गाथा:1" in keys  # main
    assert "समयसार:गाथा:2" in keys  # remaining inline


# ---------------------------------------------------------------------------
# Inline (non-main) reference edges
# ---------------------------------------------------------------------------


def _make_inline_ref(shastra_name, resolved_fields, teeka_name=""):
    return Reference(
        text="inline_test",
        inline_reference=True,
        shastra_name=shastra_name,
        teeka_name=teeka_name,
        resolved_fields=resolved_fields,
    )


def _main_no_fields(shastra_name="समयसार"):
    """Non-inline main ref with no resolved fields → emits no edges."""
    return Reference(text="main", inline_reference=False, shastra_name=shastra_name, resolved_fields=[])


def test_inline_shastra_gatha_emits_gatha():
    """Inline shastra ref emits Gatha — same as main, no block-kind difference."""
    cfg = _make_config()
    inline = _make_inline_ref("समयसार", [_rf("गाथा", 7)])
    b = Block(kind="hindi_text", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Gatha", "key": "समयसार:गाथा:7"}


def test_inline_teeka_gatha_kind_emits_gatha():
    """Inline teeka ref emits plain Gatha — _emit_inline_only_edges ignores shastra type for gatha."""
    cfg = _make_config()
    inline = _make_inline_ref("नियमसार", [_rf("गाथा", 6)], teeka_name="आत्मख्याती")
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Gatha", "key": "नियमसार:गाथा:6"}


def test_inline_teeka_text_kind_emits_gatha():
    """Inline teeka ref in text-kind block emits plain Gatha."""
    cfg = _make_config()
    inline = _make_inline_ref("नियमसार", [_rf("गाथा", 6)], teeka_name="आत्मख्याती")
    b = Block(kind="sanskrit_text", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "Gatha"


def test_inline_teeka_kalash_no_block_kind_check():
    """Inline teeka ref with kalash emits Kalash regardless of block kind."""
    cfg = _make_config()
    inline = _make_inline_ref("नियमसार", [_rf("कलश", 3)], teeka_name="आत्मख्याती")
    # Use hindi_text — for main teeka this would not emit Kalash, but inline should
    b = Block(kind="hindi_text", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Kalash", "key": "नियमसार:आत्मख्याती:कलश:3"}


def test_inline_publication_gatha_emits_gatha():
    """Inline publication ref emits plain Gatha — shastra type ignored for gatha in inline path."""
    cfg = _make_config()
    inline = _make_inline_ref("कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 6)], teeka_name="जयसेन")
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    e = edges[0]
    assert e["from"]["label"] == "Gatha"
    assert e["from"]["key"] == "कार्तिकेयानुप्रेक्षा:गाथा:6"


def test_inline_publication_kalash_emits_kalash():
    """Inline publication ref with kalash emits Kalash (same key as teeka — no BhaaVarth in inline path)."""
    cfg = _make_config()
    inline = _make_inline_ref("कार्तिकेयानुप्रेक्षा", [_rf("कलश", 3)], teeka_name="जयसेन")
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Kalash", "key": "कार्तिकेयानुप्रेक्षा:जयसेन:कलश:3"}


def test_inline_publication_page_emits_page():
    """Inline publication ref with page emits Page edge."""
    cfg = _make_config()
    inline = _make_inline_ref("कार्तिकेयानुप्रेक्षा", [_rf("पृष्ठ", 50)], teeka_name="जयसेन")
    b = Block(kind="hindi_text", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Page", "key": "कार्तिकेयानुप्रेक्षा:जयसेन:1:पृष्ठ:50"}


def test_inline_teeka_missing_teeka_name_emits_gatha():
    """Inline teeka ref with missing teeka_name still emits plain Gatha (inline path ignores shastra type)."""
    cfg = _make_config()
    inline = _make_inline_ref("नियमसार", [_rf("गाथा", 6)], teeka_name="")
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "Gatha"
    assert edges[0]["from"]["key"] == "नियमसार:गाथा:6"


def test_inline_shastra_no_kalash_edge():
    """Inline shastra ref with kalash emits nothing (same rule as main shastra)."""
    cfg = _make_config()
    inline = _make_inline_ref("समयसार", [_rf("कलश", 3)])
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_inline_shastra_no_page_edge():
    """Inline shastra ref with page emits nothing (publication only)."""
    cfg = _make_config()
    inline = _make_inline_ref("समयसार", [_rf("पृष्ठ", 10)])
    b = Block(kind="hindi_text", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_inline_unknown_shastra_skipped():
    """Inline ref with unknown shastra_name emits nothing."""
    cfg = _make_config()
    inline = _make_inline_ref("अज्ञात", [_rf("गाथा", 5)])
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_inline_no_shastra_name_skipped():
    """Inline ref with shastra_name=None emits nothing."""
    cfg = _make_config()
    inline = Reference(text="inline", inline_reference=True, shastra_name=None,
                       resolved_fields=[_rf("गाथा", 5)])
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []


def test_multiple_inline_refs_all_processed():
    """All remaining refs (inline or not) after main are processed."""
    cfg = _make_config()
    main = Reference(text="main", inline_reference=False, shastra_name="समयसार",
                     resolved_fields=[_rf("गाथा", 1)])
    inline1 = _make_inline_ref("नियमसार", [_rf("गाथा", 10)], teeka_name="त.प्र.")
    inline2 = _make_inline_ref("कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 20)], teeka_name="जयसेन")
    b = Block(kind="hindi_text", references=[main, inline1, inline2])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    # main (shastra/hindi_text) → Gatha(1)
    # inline1 (teeka/inline) → Gatha(10) — inline path emits plain Gatha for all shastra types
    # inline2 (publication/inline) → Gatha(20) — same
    assert len(edges) == 3
    labels = {e["from"]["label"] for e in edges}
    assert labels == {"Gatha"}


def test_inline_publication_pankti_in_props():
    """Inline publication ref with pankti surfaces pankti in edge props."""
    cfg = _make_config()
    inline = _make_inline_ref("कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 6), _rf("पंक्ति", 3)], teeka_name="जयसेन")
    b = Block(kind="hindi_gatha", references=[_main_no_fields(), inline])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["props"]["pankti"] == 3


# ---------------------------------------------------------------------------
# Phase 4: compound NK resolution tests
# ---------------------------------------------------------------------------

def _make_registry_with_parmatma():
    """Registry with समयसार (legacy shastra) and परमात्मप्रकाश (compound publication)."""
    norm = _make_norm_config()
    registry = ShastraRegistry()
    from workers.ingestion.jainkosh.parse_reference import _normalise

    entries = [
        ShastraEntry(
            shastra_name="समयसार",
            alternate_names=[],
            short_form="",
            format_str="गाथा",
            format_groups=parse_format_string("गाथा"),
            publisher="",
            type="shastra",
        ),
        ShastraEntry(
            shastra_name="परमात्मप्रकाश",
            alternate_names=[],
            short_form="प.प्र./मू.",
            format_str="अधिकार/परमात्मप्रकाशगाथा",
            format_groups=parse_format_string("अधिकार/परमात्मप्रकाशगाथा"),
            publisher="राजचन्द्र ग्रन्थमाला",
            type="publication",
        ),
        ShastraEntry(
            shastra_name="परमात्मप्रकाशटीका",
            alternate_names=[],
            short_form="",
            format_str="अधिकार/परमात्मप्रकाशगाथा",
            format_groups=parse_format_string("अधिकार/परमात्मप्रकाशगाथा"),
            publisher="",
            type="teeka",
        ),
    ]
    for entry in entries:
        registry.entries.append(entry)
        registry._by_primary[_normalise(entry.shastra_name, norm)] = entry
        registry._by_exact_name[entry.shastra_name] = entry

    return registry


def _make_config_compound() -> JainkoshConfig:
    """Config backed by real shastra.json so परमात्मप्रकाश compound fields are live."""
    from workers.ingestion.jainkosh.config import load_config
    cfg = load_config()
    # Replace registry with one that includes परमात्मप्रकाश
    cfg.shastra_registry = _make_registry_with_parmatma()
    pub = PublisherRegistry()
    pub._by_name["राजचन्द्र ग्रन्थमाला"] = "pub1"
    cfg.publisher_registry = pub
    return cfg


def test_compound_gatha_nk_for_parmatmaprakash_single_ref():
    """`अधिकार=1, परमात्मप्रकाशगाथा=19` → `परमात्मप्रकाश:अधिकार:1:गाथा:19`."""
    cfg = _make_config_compound()
    b = _block(
        "hindi_gatha",
        "परमात्मप्रकाश",
        [_rf("अधिकार", 1), _rf("परमात्मप्रकाशगाथा", 19)],
    )
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Gatha", "key": "परमात्मप्रकाश:अधिकार:1:गाथा:19"}


def test_compound_gatha_nk_range_expansion():
    """`अधिकार=1, परमात्मप्रकाशगाथा=19,20,21` resolves to three separate Gatha NKs."""
    from workers.ingestion.jainkosh.models import Reference
    cfg = _make_config_compound()

    # Simulate three separate resolved references (each expanded gatha value)
    # Each gets its own edge via separate block/reference objects.
    results = []
    for g_val in (19, 20, 21):
        b = _block(
            "hindi_gatha",
            "परमात्मप्रकाश",
            [_rf("अधिकार", 1), _rf("परमात्मप्रकाशगाथा", g_val)],
        )
        edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
        results.extend(edges)

    nks = {e["from"]["key"] for e in results}
    assert nks == {
        "परमात्मप्रकाश:अधिकार:1:गाथा:19",
        "परमात्मप्रकाश:अधिकार:1:गाथा:20",
        "परमात्मप्रकाश:अधिकार:1:गाथा:21",
    }


def test_legacy_gatha_nk_unchanged_for_samaysar():
    """`(स.सा./मू./8)` still produces `समयसार:गाथा:8` (legacy unchanged)."""
    cfg = _make_config_compound()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 8)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Gatha", "key": "समयसार:गाथा:8"}


def test_gatha_teeka_nk_compound():
    """Teeka-layer reference for compound shastra inserts टीका before last value."""
    cfg = _make_config_compound()
    # block_kind="sanskrit_text" → GathaTeeka path for publication type
    b = _block(
        "sanskrit_text",
        "परमात्मप्रकाश",
        [_rf("अधिकार", 1), _rf("परमात्मप्रकाशगाथा", 19)],
        teeka_name="टीका",
    )
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    e = edges[0]
    assert e["from"]["label"] == "GathaTeeka"
    assert e["from"]["key"] == "परमात्मप्रकाश:टीका:अधिकार:1:गाथा:टीका:19"


def test_missing_field_returns_no_edge(caplog):
    """Malformed ref (missing अधिकार for compound shastra) → no edge + warning logged."""
    import logging
    cfg = _make_config_compound()
    # Only परमात्मप्रकाशगाथा provided, अधिकार missing → build_compound_suffix returns None
    b = _block(
        "hindi_gatha",
        "परमात्मप्रकाश",
        [_rf("परमात्मप्रकाशगाथा", 19)],  # missing अधिकार
    )
    with caplog.at_level(logging.WARNING):
        edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []
    assert any("parser.reference.compound.missing_field" in r.message for r in caplog.records)
