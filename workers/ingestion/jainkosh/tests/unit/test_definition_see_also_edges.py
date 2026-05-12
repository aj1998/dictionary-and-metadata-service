"""Tests for two bugs fixed in envelope.py:

1. _see_also_kw_edge: see_also blocks inside definition context now emit
   RELATED_TO edges from the Keyword node (previously silently dropped).

2. _dedupe resolve_by fix: edges whose 'to' uses resolve_by (Topic with
   parent_keyword + topic_path) were all collapsing to one edge because
   _dedupe keyed on to.get("key", "") which is "" for all resolve_by nodes.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from workers.ingestion.jainkosh.config import (
    DevanagariNormalizationConfig,
    JainkoshConfig,
    Neo4jEnvelopeConfig,
)
from workers.ingestion.jainkosh.envelope import (
    _dedupe,
    _see_also_kw_edge,
    build_neo4j_fragment,
)
from workers.ingestion.jainkosh.models import (
    Block,
    Definition,
    KeywordParseResult,
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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_config(redlink_mode: str = "never") -> JainkoshConfig:
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_reference import _normalise

    norm = DevanagariNormalizationConfig(enabled=False, substitutions=[])
    registry = ShastraRegistry()
    entry = ShastraEntry(
        shastra_name="समयसार", alternate_names=[], short_form="",
        format_str="गाथा", format_groups=parse_format_string("गाथा"),
        publisher="", type="shastra",
    )
    registry.entries.append(entry)
    registry._by_primary[_normalise(entry.shastra_name, norm)] = entry

    pub = PublisherRegistry()
    cfg = load_config()
    cfg.shastra_registry = registry
    cfg.publisher_registry = pub
    cfg = cfg.model_copy(update={"neo4j": Neo4jEnvelopeConfig(redlink_edges=redlink_mode)})
    return cfg


def _see_also_block(
    *,
    target_keyword: str | None = None,
    target_topic_path: str | None = None,
    is_self: bool = False,
    target_exists: bool = True,
) -> Block:
    return Block(
        kind="see_also",
        references=[],
        target_keyword=target_keyword,
        target_topic_path=target_topic_path,
        is_self=is_self,
        target_exists=target_exists,
    )


def _make_result(
    keyword: str,
    *,
    definition_blocks: list[Block],
    section_kind: str = "siddhantkosh",
) -> KeywordParseResult:
    defn = Definition(definition_index=1, blocks=definition_blocks)
    sec = PageSection(
        section_kind=section_kind,
        section_index=0,
        h2_text="section",
        definitions=[defn],
        index_relations=[],
        subsections=[],
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


# ---------------------------------------------------------------------------
# _see_also_kw_edge: unit tests
# ---------------------------------------------------------------------------

class TestSeeAlsoKwEdge:
    def test_keyword_target_only(self):
        cfg = _make_config()
        b = _see_also_block(target_keyword="द्रव्य")
        edge = _see_also_kw_edge(b, keyword_node="वस्तु", config=cfg)
        assert edge["type"] == "RELATED_TO"
        assert edge["from"] == {"label": "Keyword", "key": "वस्तु"}
        assert edge["to"] == {"label": "Keyword", "key": "द्रव्य"}
        assert edge["props"]["source"] == "jainkosh"

    def test_keyword_plus_topic_path(self):
        cfg = _make_config()
        b = _see_also_block(target_keyword="द्रव्य", target_topic_path="1.7")
        edge = _see_also_kw_edge(b, keyword_node="वस्तु", config=cfg)
        assert edge["to"] == {
            "label": "Topic",
            "resolve_by": {"parent_keyword": "द्रव्य", "topic_path": "1.7"},
        }

    def test_self_reference_with_topic_path(self):
        cfg = _make_config()
        b = _see_also_block(is_self=True, target_topic_path="2.3")
        edge = _see_also_kw_edge(b, keyword_node="आत्मा", config=cfg)
        assert edge["to"] == {
            "label": "Topic",
            "resolve_by": {"parent_keyword": "आत्मा", "topic_path": "2.3"},
        }

    def test_no_target_returns_empty(self):
        cfg = _make_config()
        b = _see_also_block()  # no target_keyword, no topic_path, not is_self
        edge = _see_also_kw_edge(b, keyword_node="वस्तु", config=cfg)
        assert edge == {}

    def test_redlink_suppressed_when_never(self):
        cfg = _make_config(redlink_mode="never")
        b = _see_also_block(target_keyword="अज्ञात", target_exists=False)
        edge = _see_also_kw_edge(b, keyword_node="वस्तु", config=cfg)
        assert edge == {}

    def test_redlink_allowed_when_always(self):
        cfg = _make_config(redlink_mode="always")
        b = _see_also_block(target_keyword="अज्ञात", target_exists=False)
        edge = _see_also_kw_edge(b, keyword_node="वस्तु", config=cfg)
        assert edge["type"] == "RELATED_TO"
        assert edge["to"] == {"label": "Keyword", "key": "अज्ञात"}

    def test_redlink_only_if_topic_suppresses_keyword_target(self):
        cfg = _make_config(redlink_mode="only_if_topic")
        b = _see_also_block(target_keyword="अज्ञात", target_exists=False)
        edge = _see_also_kw_edge(b, keyword_node="वस्तु", config=cfg)
        assert edge == {}

    def test_redlink_only_if_topic_allows_topic_target(self):
        cfg = _make_config(redlink_mode="only_if_topic")
        b = _see_also_block(target_keyword="अज्ञात", target_topic_path="1", target_exists=False)
        edge = _see_also_kw_edge(b, keyword_node="वस्तु", config=cfg)
        # target is a Topic (resolve_by), so it passes the filter
        assert edge["type"] == "RELATED_TO"
        assert edge["to"]["label"] == "Topic"


# ---------------------------------------------------------------------------
# _dedupe: resolve_by fix
# ---------------------------------------------------------------------------

class TestDedupeResolveby:
    def _edge(self, resolve_by: dict | None = None, key: str | None = None) -> dict:
        to: dict = {"label": "Topic"}
        if key is not None:
            to["key"] = key
        if resolve_by is not None:
            to["resolve_by"] = resolve_by
        return {
            "type": "RELATED_TO",
            "from": {"label": "Keyword", "key": "वस्तु"},
            "to": to,
            "props": {"weight": 1.0, "source": "jainkosh"},
        }

    def test_distinct_resolve_by_both_kept(self):
        e1 = self._edge(resolve_by={"parent_keyword": "द्रव्य", "topic_path": "1.7"})
        e2 = self._edge(resolve_by={"parent_keyword": "द्रव्य", "topic_path": "1.4"})
        result = _dedupe([e1, e2])
        assert len(result) == 2

    def test_identical_resolve_by_deduped(self):
        e = self._edge(resolve_by={"parent_keyword": "द्रव्य", "topic_path": "1.7"})
        result = _dedupe([e, dict(e), dict(e)])
        assert len(result) == 1

    def test_resolve_by_and_key_targets_all_distinct(self):
        e_kw = self._edge(key="द्रव्य")
        e_t1 = self._edge(resolve_by={"parent_keyword": "द्रव्य", "topic_path": "1.7"})
        e_t2 = self._edge(resolve_by={"parent_keyword": "द्रव्य", "topic_path": "1.4"})
        e_t3 = self._edge(resolve_by={"parent_keyword": "श्रुतज्ञान", "topic_path": "II"})
        result = _dedupe([e_kw, e_t1, e_t2, e_t3])
        assert len(result) == 4

    def test_different_parent_keyword_same_topic_path_both_kept(self):
        e1 = self._edge(resolve_by={"parent_keyword": "द्रव्य", "topic_path": "1"})
        e2 = self._edge(resolve_by={"parent_keyword": "गुण", "topic_path": "1"})
        result = _dedupe([e1, e2])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# integration: build_neo4j_fragment emits RELATED_TO for definition see_also
# ---------------------------------------------------------------------------

class TestDefinitionSeeAlsoIntegration:
    def test_see_also_keyword_target_emits_related_to(self):
        cfg = _make_config()
        result = _make_result("वस्तु", definition_blocks=[
            _see_also_block(target_keyword="द्रव्य"),
        ])
        frag = build_neo4j_fragment(result, cfg)
        rt = [e for e in frag["edges"] if e["type"] == "RELATED_TO"]
        assert len(rt) == 1
        assert rt[0]["from"] == {"label": "Keyword", "key": "वस्तु"}
        assert rt[0]["to"] == {"label": "Keyword", "key": "द्रव्य"}

    def test_see_also_topic_path_emits_resolved_key(self):
        cfg = _make_config()
        result = _make_result("वस्तु", definition_blocks=[
            _see_also_block(target_keyword="द्रव्य", target_topic_path="1.7"),
        ])
        frag = build_neo4j_fragment(result, cfg)
        rt = [e for e in frag["edges"] if e["type"] == "RELATED_TO"]
        assert len(rt) == 1
        # resolve_by replaced with concrete key; cross-page → placeholder key
        assert rt[0]["to"] == {"label": "Topic", "key": "द्रव्य:1:7"}
        # stub seed emitted for this topic
        stubs = [n for n in frag["nodes"] if n.get("is_stub_seed") and n["label"] == "Topic"]
        assert any(n["key"] == "द्रव्य:1:7" for n in stubs)

    def test_multiple_see_also_all_emitted(self):
        """All five see_also blocks from वस्तु's definition produce distinct edges."""
        cfg = _make_config()
        result = _make_result("वस्तु", definition_blocks=[
            _see_also_block(target_keyword="द्रव्य"),
            _see_also_block(target_keyword="द्रव्य", target_topic_path="1.7"),
            _see_also_block(target_keyword="द्रव्य", target_topic_path="1.4"),
            _see_also_block(target_keyword="सामान्य"),
            _see_also_block(target_keyword="श्रुतज्ञान", target_topic_path="II"),
        ])
        frag = build_neo4j_fragment(result, cfg)
        rt = [e for e in frag["edges"] if e["type"] == "RELATED_TO"]
        assert len(rt) == 5

    def test_puraankosh_see_also_not_emitted(self):
        """see_also in puraankosh definitions produces no edges (section is skipped)."""
        cfg = _make_config()
        result = _make_result("वस्तु", section_kind="puraankosh", definition_blocks=[
            _see_also_block(target_keyword="द्रव्य"),
        ])
        frag = build_neo4j_fragment(result, cfg)
        rt = [e for e in frag["edges"] if e["type"] == "RELATED_TO"]
        assert rt == []

    def test_non_see_also_blocks_still_emit_contains_definition(self):
        """Adding a see_also block does not break reference-edge emission for other blocks."""
        cfg = _make_config()
        ref_block = Block(
            kind="sanskrit_gatha",
            references=[Reference(
                text="t", shastra_name="समयसार",
                resolved_fields=[ResolvedField(field="गाथा", value=10)],
            )],
        )
        result = _make_result("वस्तु", definition_blocks=[
            ref_block,
            _see_also_block(target_keyword="द्रव्य"),
        ])
        frag = build_neo4j_fragment(result, cfg)
        cd = [e for e in frag["edges"] if e["type"] == "CONTAINS_DEFINITION"]
        rt = [e for e in frag["edges"] if e["type"] == "RELATED_TO"]
        assert len(cd) == 1
        assert len(rt) == 1

    def test_redlink_see_also_in_definition_suppressed(self):
        cfg = _make_config(redlink_mode="never")
        result = _make_result("वस्तु", definition_blocks=[
            _see_also_block(target_keyword="अज्ञात", target_exists=False),
        ])
        frag = build_neo4j_fragment(result, cfg)
        rt = [e for e in frag["edges"] if e["type"] == "RELATED_TO"]
        assert rt == []
