"""Tests for §1–3 of query_and_ingestion_improvements.md:
block_index, mention_path, source_natural_key, section_index, definition_index on reference edges.
Also covers the updated _dedupe keying in envelope.py (§8).
"""

from __future__ import annotations

import pytest

from workers.ingestion.jainkosh.config import (
    DevanagariNormalizationConfig,
    JainkoshConfig,
)
from datetime import datetime

from workers.ingestion.jainkosh.models import (
    Block,
    Definition,
    Nav,
    PageSection,
    Reference,
    ResolvedField,
    Subsection,
)
from workers.ingestion.jainkosh.parse_reference import (
    PublisherRegistry,
    ShastraEntry,
    ShastraRegistry,
    parse_format_string,
)
from workers.ingestion.jainkosh.reference_edges import build_reference_edges


# ---------------------------------------------------------------------------
# Shared helpers (duplicated from test_reference_edges.py to stay self-contained)
# ---------------------------------------------------------------------------

def _make_config() -> JainkoshConfig:
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_reference import _normalise

    norm = DevanagariNormalizationConfig(enabled=False, substitutions=[])
    registry = ShastraRegistry()
    for entry in [
        ShastraEntry(
            shastra_name="समयसार", alternate_names=[], short_form="",
            format_str="गाथा", format_groups=parse_format_string("गाथा"),
            publisher="", type="shastra",
        ),
        ShastraEntry(
            shastra_name="नियमसार", alternate_names=[], short_form="",
            format_str="गाथा", format_groups=parse_format_string("गाथा"),
            publisher="", type="teeka",
        ),
        ShastraEntry(
            shastra_name="कार्तिकेयानुप्रेक्षा", alternate_names=[], short_form="",
            format_str="गाथा", format_groups=parse_format_string("गाथा"),
            publisher="अनन्तकीर्ति ग्रन्थमाला", type="publication",
        ),
    ]:
        registry.entries.append(entry)
        registry._by_primary[_normalise(entry.shastra_name, norm)] = entry

    pub = PublisherRegistry()
    pub._by_name["अनन्तकीर्ति ग्रन्थमाला"] = "1"

    cfg = load_config()
    cfg.shastra_registry = registry
    cfg.publisher_registry = pub
    return cfg


def _rf(field: str, value) -> ResolvedField:
    return ResolvedField(field=field, value=value)


def _block(kind: str, shastra_name: str, fields: list[ResolvedField], teeka_name: str = "") -> Block:
    return Block(kind=kind, references=[
        Reference(text="t", shastra_name=shastra_name, teeka_name=teeka_name, resolved_fields=fields)
    ])


TOPIC_TARGET = {"label": "Topic", "key": "आत्मा:उपशीर्षक"}
KW_TARGET = {"label": "Keyword", "key": "आत्मा"}


# ---------------------------------------------------------------------------
# §1: block_index is present on all emitted edges
# ---------------------------------------------------------------------------

def test_block_index_default_zero():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert len(edges) == 1
    assert edges[0]["props"]["block_index"] == 0


def test_block_index_nonzero():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg,
                                  block_index=3)
    assert edges[0]["props"]["block_index"] == 3


def test_block_index_on_gathateeka():
    cfg = _make_config()
    b = _block("sanskrit_text", "नियमसार", [_rf("गाथा", 6)], teeka_name="आत्मख्याती")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg,
                                  block_index=2)
    assert edges[0]["props"]["block_index"] == 2


def test_block_index_on_two_edges_publication_hindi():
    """Both edges emitted for publication hindi_text get the same block_index."""
    cfg = _make_config()
    b = _block("hindi_text", "कार्तिकेयानुप्रेक्षा", [_rf("गाथा", 5)], teeka_name="जयसेन")
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg,
                                  block_index=7)
    assert len(edges) == 2
    assert all(e["props"]["block_index"] == 7 for e in edges)


def test_block_index_on_inline_ref_edges():
    """block_index propagates to inline (remaining) ref edges too."""
    cfg = _make_config()
    main_ref = Reference(text="main", inline_reference=False, shastra_name="समयसार",
                         resolved_fields=[_rf("गाथा", 1)])
    inline_ref = Reference(text="inline", inline_reference=True, shastra_name="समयसार",
                           resolved_fields=[_rf("गाथा", 99)])
    b = Block(kind="sanskrit_gatha", references=[main_ref, inline_ref])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg,
                                  block_index=4)
    assert len(edges) == 2
    assert all(e["props"]["block_index"] == 4 for e in edges)


# ---------------------------------------------------------------------------
# §1: mention_path is set on edges
# ---------------------------------------------------------------------------

def test_mention_path_subsection_context():
    """mention_path for MENTIONS_TOPIC: '<topic_nk>/<block_index>'."""
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    topic_nk = "आत्मा:उपशीर्षक"
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg,
                                  block_index=2, mention_path=f"{topic_nk}/2",
                                  source_natural_key=topic_nk)
    assert edges[0]["props"]["mention_path"] == "आत्मा:उपशीर्षक/2"


def test_mention_path_definition_context():
    """mention_path for CONTAINS_DEFINITION: '<section_index>/<def_index>/<block_index>'."""
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=KW_TARGET, edge_type="CONTAINS_DEFINITION", config=cfg,
                                  block_index=1, mention_path="0/2/1",
                                  source_natural_key="आत्मा",
                                  section_index=0, definition_index=2)
    assert edges[0]["props"]["mention_path"] == "0/2/1"


def test_mention_path_absent_when_empty():
    """mention_path is not in props when caller passes empty string."""
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert "mention_path" not in edges[0]["props"]


# ---------------------------------------------------------------------------
# §3: source_natural_key
# ---------------------------------------------------------------------------

def test_source_natural_key_topic_context():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg,
                                  source_natural_key="आत्मा:उपशीर्षक")
    assert edges[0]["props"]["source_natural_key"] == "आत्मा:उपशीर्षक"


def test_source_natural_key_definition_context():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=KW_TARGET, edge_type="CONTAINS_DEFINITION", config=cfg,
                                  source_natural_key="आत्मा")
    assert edges[0]["props"]["source_natural_key"] == "आत्मा"


def test_source_natural_key_absent_when_empty():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=TOPIC_TARGET, edge_type="MENTIONS_TOPIC", config=cfg)
    assert "source_natural_key" not in edges[0]["props"]


# ---------------------------------------------------------------------------
# §2: section_index and definition_index
# ---------------------------------------------------------------------------

def test_section_and_definition_index_on_contains_definition():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=KW_TARGET, edge_type="CONTAINS_DEFINITION", config=cfg,
                                  block_index=0, mention_path="1/3/0",
                                  source_natural_key="आत्मा",
                                  section_index=1, definition_index=3)
    props = edges[0]["props"]
    assert props["section_index"] == 1
    assert props["definition_index"] == 3
    assert props["block_index"] == 0
    assert props["mention_path"] == "1/3/0"


def test_section_and_definition_index_absent_when_not_passed():
    cfg = _make_config()
    b = _block("sanskrit_gatha", "समयसार", [_rf("गाथा", 1)])
    edges = build_reference_edges(b, target=KW_TARGET, edge_type="CONTAINS_DEFINITION", config=cfg)
    props = edges[0]["props"]
    assert "section_index" not in props
    assert "definition_index" not in props


# ---------------------------------------------------------------------------
# §8: _dedupe keys on mention_path, preserving distinct citation contexts
# ---------------------------------------------------------------------------

def test_dedupe_preserves_distinct_mention_paths():
    """Two edges with same (type, from, to) but different mention_path are both kept."""
    from workers.ingestion.jainkosh.envelope import _dedupe

    edge_a = {
        "type": "CONTAINS_DEFINITION",
        "from": {"label": "Gatha", "key": "समयसार:गाथा:199"},
        "to": {"label": "Keyword", "key": "आत्मा"},
        "props": {"weight": 1.0, "source": "jainkosh", "mention_path": "0/0/1"},
    }
    edge_b = {
        "type": "CONTAINS_DEFINITION",
        "from": {"label": "Gatha", "key": "समयसार:गाथा:199"},
        "to": {"label": "Keyword", "key": "आत्मा"},
        "props": {"weight": 1.0, "source": "jainkosh", "mention_path": "0/2/0"},
    }

    result = _dedupe([edge_a, edge_b])
    assert len(result) == 2


def test_dedupe_removes_true_duplicates():
    """Two edges identical including mention_path → one survives."""
    from workers.ingestion.jainkosh.envelope import _dedupe

    edge = {
        "type": "CONTAINS_DEFINITION",
        "from": {"label": "Gatha", "key": "समयसार:गाथा:199"},
        "to": {"label": "Keyword", "key": "आत्मा"},
        "props": {"weight": 1.0, "source": "jainkosh", "mention_path": "0/0/1"},
    }
    result = _dedupe([edge, dict(edge), dict(edge)])
    assert len(result) == 1


def test_dedupe_same_from_to_no_mention_path_deduped():
    """Edges without mention_path that share (type, from, to) are deduped."""
    from workers.ingestion.jainkosh.envelope import _dedupe

    edge = {
        "type": "MENTIONS_TOPIC",
        "from": {"label": "Gatha", "key": "समयसार:गाथा:1"},
        "to": {"label": "Topic", "key": "आत्मा:sub"},
        "props": {"weight": 1.0, "source": "jainkosh"},
    }
    result = _dedupe([edge, dict(edge)])
    assert len(result) == 1


def test_dedupe_nodes_still_work():
    """Non-edge dicts (nodes) are still deduplicated correctly."""
    from workers.ingestion.jainkosh.envelope import _dedupe

    node = {"label": "Topic", "key": "आत्मा:sub", "props": {"is_leaf": True}}
    result = _dedupe([node, dict(node)])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# envelope: block loops pass correct location props
# ---------------------------------------------------------------------------

def _make_minimal_result(keyword: str, *, section_kind="siddhantkosh"):
    """Build a minimal KeywordParseResult with one subsection (one block) and one definition (one block)."""
    from workers.ingestion.jainkosh.models import KeywordParseResult

    ref = Reference(text="t", shastra_name="समयसार",
                    resolved_fields=[ResolvedField(field="गाथा", value=1)])
    block = Block(kind="sanskrit_gatha", references=[ref])

    sub = Subsection(
        topic_path="1",
        heading_text="उपशीर्षक",
        heading_path=["1"],
        natural_key=f"{keyword}:1",
        parent_natural_key=None,
        is_leaf=True,
        blocks=[block],
        children=[],
    )
    defn = Definition(definition_index=0, blocks=[block])
    sec = PageSection(
        section_kind=section_kind,
        section_index=0,
        h2_text="सिद्धान्तकोश",
        definitions=[defn],
        index_relations=[],
        subsections=[sub],
        label_topic_seeds=[],
        extra_blocks=[],
    )
    return KeywordParseResult(
        keyword=keyword,
        source_url=f"https://jainkosh.org/wiki/{keyword}",
        page_sections=[sec],
        nav=Nav(),
        parser_version="test/1.0",
        parsed_at=datetime(2026, 1, 1),
        warnings=[],
    )


def test_envelope_mentions_topic_block_index_and_mention_path():
    """build_neo4j_fragment threads block_index and mention_path for MENTIONS_TOPIC edges."""
    cfg = _make_config()
    result = _make_minimal_result("आत्मा")
    from workers.ingestion.jainkosh.envelope import build_neo4j_fragment

    frag = build_neo4j_fragment(result, cfg)
    mt_edges = [e for e in frag["edges"] if e["type"] == "MENTIONS_TOPIC"]
    assert len(mt_edges) >= 1
    e = mt_edges[0]
    assert e["props"]["block_index"] == 0
    assert e["props"]["mention_path"] == "आत्मा:1/0"
    assert e["props"]["source_natural_key"] == "आत्मा:1"


def test_envelope_contains_definition_location_props():
    """build_neo4j_fragment sets section_index, definition_index, block_index on CONTAINS_DEFINITION."""
    cfg = _make_config()
    result = _make_minimal_result("आत्मा")
    from workers.ingestion.jainkosh.envelope import build_neo4j_fragment

    frag = build_neo4j_fragment(result, cfg)
    cd_edges = [e for e in frag["edges"] if e["type"] == "CONTAINS_DEFINITION"]
    assert len(cd_edges) >= 1
    e = cd_edges[0]
    assert e["props"]["block_index"] == 0
    assert e["props"]["section_index"] == 0
    assert e["props"]["definition_index"] == 0
    assert e["props"]["mention_path"] == "0/0/0"
    assert e["props"]["source_natural_key"] == "आत्मा"


def test_envelope_block_index_increments_across_blocks():
    """Multiple blocks in a subsection get sequential block_index values."""
    from workers.ingestion.jainkosh.models import KeywordParseResult
    from workers.ingestion.jainkosh.envelope import build_neo4j_fragment

    cfg = _make_config()
    ref = Reference(text="t", shastra_name="समयसार",
                    resolved_fields=[ResolvedField(field="गाथा", value=1)])

    sub = Subsection(
        topic_path="1", heading_text="sub", heading_path=["1"],
        natural_key="आत्मा:1", parent_natural_key=None, is_leaf=True,
        blocks=[
            Block(kind="sanskrit_gatha", references=[ref]),
            Block(kind="sanskrit_gatha", references=[
                Reference(text="t2", shastra_name="समयसार",
                          resolved_fields=[ResolvedField(field="गाथा", value=2)])
            ]),
        ],
        children=[],
    )
    sec = PageSection(
        section_kind="siddhantkosh", section_index=0, h2_text="s",
        definitions=[], index_relations=[], subsections=[sub],
        label_topic_seeds=[], extra_blocks=[],
    )
    result = KeywordParseResult(
        keyword="आत्मा", source_url="https://x", page_sections=[sec],
        nav=Nav(), parser_version="test/1.0", parsed_at=datetime(2026, 1, 1), warnings=[],
    )
    frag = build_neo4j_fragment(result, cfg)
    mt_edges = sorted(
        [e for e in frag["edges"] if e["type"] == "MENTIONS_TOPIC"],
        key=lambda e: e["props"]["block_index"],
    )
    assert len(mt_edges) == 2
    assert mt_edges[0]["props"]["block_index"] == 0
    assert mt_edges[0]["props"]["mention_path"] == "आत्मा:1/0"
    assert mt_edges[1]["props"]["block_index"] == 1
    assert mt_edges[1]["props"]["mention_path"] == "आत्मा:1/1"


def test_envelope_puraankosh_skipped_for_contains_definition():
    """CONTAINS_DEFINITION edges are not emitted for puraankosh sections."""
    from workers.ingestion.jainkosh.envelope import build_neo4j_fragment

    cfg = _make_config()
    result = _make_minimal_result("आत्मा", section_kind="puraankosh")
    frag = build_neo4j_fragment(result, cfg)
    cd_edges = [e for e in frag["edges"] if e["type"] == "CONTAINS_DEFINITION"]
    assert cd_edges == []


def test_dedupe_distinct_mention_paths_both_survive_in_envelope():
    """Two CONTAINS_DEFINITION edges from same gatha to same keyword but different mention_path
    are both kept after _dedupe (the gatha cited two definitions of the same keyword)."""
    from workers.ingestion.jainkosh.models import KeywordParseResult
    from workers.ingestion.jainkosh.envelope import build_neo4j_fragment

    cfg = _make_config()
    ref = Reference(text="t", shastra_name="समयसार",
                    resolved_fields=[ResolvedField(field="गाथा", value=199)])
    block = Block(kind="sanskrit_gatha", references=[ref])

    def0 = Definition(definition_index=0, blocks=[block])
    def1 = Definition(definition_index=1, blocks=[block])
    sec = PageSection(
        section_kind="siddhantkosh", section_index=0, h2_text="s",
        definitions=[def0, def1], index_relations=[], subsections=[],
        label_topic_seeds=[], extra_blocks=[],
    )
    result = KeywordParseResult(
        keyword="आत्मा", source_url="https://x", page_sections=[sec],
        nav=Nav(), parser_version="test/1.0", parsed_at=datetime(2026, 1, 1), warnings=[],
    )
    frag = build_neo4j_fragment(result, cfg)
    cd_edges = [e for e in frag["edges"] if e["type"] == "CONTAINS_DEFINITION"]
    assert len(cd_edges) == 2
    paths = {e["props"]["mention_path"] for e in cd_edges}
    assert paths == {"0/0/0", "0/1/0"}
