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
            shastra_name="धवला",
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


def test_teeka_missing_teeka_name_returns_empty(caplog):
    import logging
    cfg = _make_config()
    b = _block("sanskrit_text", "नियमसार", [_rf("गाथा", 6)], teeka_name="")
    with caplog.at_level(logging.WARNING):
        edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert edges == []
    assert "missing_teeka_for_edge" in caplog.text


# ---------------------------------------------------------------------------
# publication-type edges
# ---------------------------------------------------------------------------

def test_publication_gatha_kind_uses_gatha():
    cfg = _make_config()
    b = _block("prakrit_gatha", "धवला", [_rf("गाथा", 6)], teeka_name="जयधवला")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "Gatha"


def test_publication_sanskrit_text_uses_gathateeka():
    cfg = _make_config()
    b = _block("sanskrit_text", "धवला", [_rf("गाथा", 6)], teeka_name="जयधवला")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"]["label"] == "GathaTeeka"
    assert edges[0]["from"]["key"] == "धवला:जयधवला:गाथा:टीका:6"


def test_publication_hindi_text_two_edges():
    cfg = _make_config()
    b = _block("hindi_text", "धवला", [_rf("गाथा", 6)], teeka_name="जयधवला")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 2
    labels = {e["from"]["label"] for e in edges}
    assert labels == {"GathaTeeka", "GathaTeekaBhaavarth"}
    gt_edge = next(e for e in edges if e["from"]["label"] == "GathaTeekaBhaavarth")
    assert gt_edge["from"]["key"] == "धवला:जयधवला:1:गाथा:टीका:भावार्थ:6"


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
    b = _block("hindi_text", "धवला", [_rf("कलश", 3)], teeka_name="जयधवला")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "KalashBhaavarth", "key": "धवला:जयधवला:1:कलश:भावार्थ:3"}


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
    b = _block("sanskrit_gatha", "धवला", [_rf("पृष्ठ", 98)], teeka_name="जयधवला")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["from"] == {"label": "Page", "key": "धवला:जयधवला:1:पृष्ठ:98"}


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
    b = _block("sanskrit_gatha", "धवला", [_rf("गाथा", 5), _rf("पृष्ठ", 98)], teeka_name="जयधवला")
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
    cfg = _make_config()
    inline_ref = Reference(text="inline", inline_reference=True, shastra_name="समयसार",
                           resolved_fields=[_rf("गाथा", 99)])
    non_inline_ref = Reference(text="non-inline", inline_reference=False, shastra_name="समयसार",
                               resolved_fields=[_rf("गाथा", 6)])
    b = Block(kind="sanskrit_gatha", references=[inline_ref, non_inline_ref])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert "6" in edges[0]["from"]["key"]


def test_all_inline_refs_picks_first():
    cfg = _make_config()
    r1 = Reference(text="a", inline_reference=True, shastra_name="समयसार",
                   resolved_fields=[_rf("गाथा", 1)])
    r2 = Reference(text="b", inline_reference=True, shastra_name="समयसार",
                   resolved_fields=[_rf("गाथा", 2)])
    b = Block(kind="sanskrit_gatha", references=[r1, r2])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert "गाथा:1" in edges[0]["from"]["key"]
