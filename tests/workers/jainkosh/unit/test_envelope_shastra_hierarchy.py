"""Tests: Shastra/Teeka/Publication hierarchy stub nodes in the would_write envelope.

When ``envelope.shastra_hierarchy.enabled = True``, each lazy reference node
(Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page) must
produce stub nodes for all of its structural ancestors (Shastra, Teeka,
Publication) so the hierarchy is present in Neo4j before dedicated shastra
ingestion runs.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime

import pytest

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import _derive_hierarchy_nodes, build_neo4j_fragment
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


# ---------------------------------------------------------------------------
# Unit tests for _derive_hierarchy_nodes
# ---------------------------------------------------------------------------

class TestDeriveHierarchyNodes:
    def test_gatha_emits_only_shastra_and_one_edge(self):
        nodes, edges = _derive_hierarchy_nodes("Gatha", "पंचास्तिकाय:गाथा:9")
        assert [n["label"] for n in nodes] == ["Shastra"]
        assert nodes[0]["key"] == "पंचास्तिकाय"
        assert len(edges) == 1, "Gatha emits exactly one edge: Gatha→Shastra"
        assert edges[0]["type"] == "IN_SHASTRA"
        assert edges[0]["from"]["label"] == "Gatha"

    def test_gathateeka_emits_shastra_teeka_and_two_edges(self):
        nodes, edges = _derive_hierarchy_nodes("GathaTeeka", "समयसार:आत्मख्याति:गाथा:टीका:9")
        assert [n["label"] for n in nodes] == ["Shastra", "Teeka"]
        assert nodes[0]["key"] == "समयसार"
        assert nodes[1]["key"] == "समयसार:आत्मख्याति"
        assert nodes[1]["props"]["shastra_natural_key"] == "समयसार"
        assert len(edges) == 2
        edge_types = [e["type"] for e in edges]
        assert "HAS_TEEKA" in edge_types   # Shastra → Teeka
        assert "IN_TEEKA" in edge_types    # GathaTeeka → Teeka
        has_teeka = next(e for e in edges if e["type"] == "HAS_TEEKA")
        assert has_teeka["from"] == {"label": "Shastra", "key": "समयसार"}
        assert has_teeka["to"] == {"label": "Teeka", "key": "समयसार:आत्मख्याति"}

    def test_gathateekabhaavarth_emits_full_hierarchy_and_both_edges(self):
        nodes, edges = _derive_hierarchy_nodes(
            "GathaTeekaBhaavarth", "समयसार:आत्मख्याति:3:गाथा:टीका:भावार्थ:9"
        )
        assert [n["label"] for n in nodes] == ["Shastra", "Teeka", "Publication"]
        assert nodes[0]["key"] == "समयसार"
        assert nodes[1]["key"] == "समयसार:आत्मख्याति"
        assert nodes[2]["key"] == "समयसार:आत्मख्याति:3"
        assert nodes[2]["props"]["publisher_id"] == "3"
        edge_types = [e["type"] for e in edges]
        assert "HAS_TEEKA" in edge_types
        assert "HAS_PUBLICATION" in edge_types
        has_publication = next(e for e in edges if e["type"] == "HAS_PUBLICATION")
        assert has_publication["from"] == {"label": "Teeka", "key": "समयसार:आत्मख्याति"}
        assert has_publication["to"] == {"label": "Publication", "key": "समयसार:आत्मख्याति:3"}

    def test_kalash_derives_shastra_from_teeka(self):
        # Kalash props don't include shastra_natural_key — must be derived from teeka prefix
        nodes, edges = _derive_hierarchy_nodes("Kalash", "समयसार:आत्मख्याति:कलश:2")
        assert [n["label"] for n in nodes] == ["Shastra", "Teeka"]
        assert nodes[0]["key"] == "समयसार"
        assert nodes[1]["key"] == "समयसार:आत्मख्याति"
        assert any(e["type"] == "HAS_TEEKA" for e in edges)

    def test_kalashbhaavarth_emits_full_hierarchy(self):
        nodes, edges = _derive_hierarchy_nodes(
            "KalashBhaavarth", "समयसार:आत्मख्याति:3:कलश:भावार्थ:2"
        )
        assert [n["label"] for n in nodes] == ["Shastra", "Teeka", "Publication"]
        assert nodes[2]["key"] == "समयसार:आत्मख्याति:3"
        assert any(e["type"] == "HAS_TEEKA" for e in edges)
        assert any(e["type"] == "HAS_PUBLICATION" for e in edges)

    def test_page_emits_full_hierarchy(self):
        nodes, edges = _derive_hierarchy_nodes("Page", "राजवार्तिक:टीका:18:पृष्ठ:95")
        assert [n["label"] for n in nodes] == ["Shastra", "Teeka", "Publication"]
        assert nodes[0]["key"] == "राजवार्तिक"
        assert nodes[1]["key"] == "राजवार्तिक:टीका"
        assert nodes[2]["key"] == "राजवार्तिक:टीका:18"
        assert nodes[2]["props"]["publisher_id"] == "18"
        has_publication = next(e for e in edges if e["type"] == "HAS_PUBLICATION")
        assert has_publication["from"]["key"] == "राजवार्तिक:टीका"
        assert has_publication["to"]["key"] == "राजवार्तिक:टीका:18"

    def test_all_hierarchy_nodes_marked_lazy(self):
        for label, key in [
            ("Gatha", "पंचास्तिकाय:गाथा:9"),
            ("GathaTeeka", "समयसार:आत्मख्याति:गाथा:टीका:9"),
            ("GathaTeekaBhaavarth", "समयसार:आत्मख्याति:3:गाथा:टीका:भावार्थ:9"),
            ("Kalash", "समयसार:आत्मख्याति:कलश:2"),
            ("KalashBhaavarth", "समयसार:आत्मख्याति:3:कलश:भावार्थ:2"),
            ("Page", "राजवार्तिक:टीका:18:पृष्ठ:95"),
        ]:
            nodes, _ = _derive_hierarchy_nodes(label, key)
            for node in nodes:
                assert node.get("lazy") is True, (
                    f"Hierarchy node {node['label']}:{node['key']} from {label} must be lazy"
                )


# ---------------------------------------------------------------------------
# Integration tests: build_neo4j_fragment with flag enabled/disabled
# ---------------------------------------------------------------------------

_SWABHAV = Path(__file__).parents[1] / "fixtures" / "स्वभाव.html"
_URL = "https://www.jainkosh.org/wiki/%E0%A4%B8%E0%A5%8D%E0%A4%B5%E0%A4%AD%E0%A4%BE%E0%A4%B5"
_FROZEN = datetime(2026, 5, 2)


def _make_result(html_path: Path, url: str, *, shastra_hierarchy: bool):
    cfg = load_config()
    cfg.envelope.shastra_hierarchy.enabled = shastra_hierarchy
    html = html_path.read_text(encoding="utf-8")
    return parse_keyword_html(html, url, cfg, frozen_time=_FROZEN), cfg


def _neo4j_fragment(html_path: Path, url: str, *, shastra_hierarchy: bool) -> dict:
    result, cfg = _make_result(html_path, url, shastra_hierarchy=shastra_hierarchy)
    return build_neo4j_fragment(result, cfg)


def _neo4j_nodes(html_path: Path, url: str, *, shastra_hierarchy: bool) -> list[dict]:
    return _neo4j_fragment(html_path, url, shastra_hierarchy=shastra_hierarchy)["nodes"]


class TestShastraHierarchyFlag:
    def test_flag_disabled_no_shastra_nodes(self):
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=False)
        shastra_nodes = [n for n in nodes if n.get("label") == "Shastra"]
        assert shastra_nodes == [], "Shastra nodes must not be emitted when flag is off"

    def test_flag_disabled_no_teeka_nodes(self):
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=False)
        teeka_nodes = [n for n in nodes if n.get("label") == "Teeka"]
        assert teeka_nodes == [], "Teeka nodes must not be emitted when flag is off"

    def test_flag_enabled_emits_shastra_nodes(self):
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=True)
        shastra_nodes = [n for n in nodes if n.get("label") == "Shastra"]
        assert shastra_nodes, "Shastra nodes must be emitted when flag is on"

    def test_flag_enabled_shastra_nodes_are_lazy(self):
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=True)
        for node in nodes:
            if node.get("label") == "Shastra":
                assert node.get("lazy") is True, f"Shastra node {node['key']} must be lazy"

    def test_flag_enabled_teeka_nodes_emitted(self):
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=True)
        teeka_nodes = [n for n in nodes if n.get("label") == "Teeka"]
        assert teeka_nodes, "Teeka nodes must be emitted when flag is on"

    def test_flag_enabled_deduplication(self):
        """Multiple lazy nodes from the same shastra produce exactly one Shastra node."""
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=True)
        shastra_keys = [n["key"] for n in nodes if n.get("label") == "Shastra"]
        assert len(shastra_keys) == len(set(shastra_keys)), (
            "Duplicate Shastra nodes must be deduplicated"
        )

    def test_flag_enabled_teeka_deduplication(self):
        """Multiple lazy nodes from the same teeka produce exactly one Teeka node."""
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=True)
        teeka_keys = [n["key"] for n in nodes if n.get("label") == "Teeka"]
        assert len(teeka_keys) == len(set(teeka_keys)), (
            "Duplicate Teeka nodes must be deduplicated"
        )

    def test_flag_enabled_publication_nodes_emitted_when_applicable(self):
        """If any GathaTeekaBhaavarth/KalashBhaavarth/Page lazy nodes exist, Publications appear."""
        nodes = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=True)
        lazy_labels = {n["label"] for n in nodes if n.get("lazy")}
        needs_pub = lazy_labels & {"GathaTeekaBhaavarth", "KalashBhaavarth", "Page"}
        if needs_pub:
            pub_nodes = [n for n in nodes if n.get("label") == "Publication"]
            assert pub_nodes, (
                f"Publication nodes required when {needs_pub} lazy nodes exist"
            )

    def test_existing_lazy_nodes_still_present(self):
        """Enabling the flag must not remove existing Gatha/GathaTeeka etc. lazy nodes."""
        nodes_off = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=False)
        nodes_on = _neo4j_nodes(_SWABHAV, _URL, shastra_hierarchy=True)
        lazy_off = {(n["label"], n["key"]) for n in nodes_off if n.get("lazy")}
        lazy_on = {(n["label"], n["key"]) for n in nodes_on if n.get("lazy")}
        assert lazy_off.issubset(lazy_on), (
            "Enabling shastra_hierarchy must not remove existing lazy nodes"
        )

    def test_flag_disabled_no_hierarchy_edges(self):
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=False)
        hierarchy_edges = [
            e for e in frag["edges"] if e.get("type") in ("HAS_TEEKA", "HAS_PUBLICATION", "IN_SHASTRA", "IN_TEEKA")
        ]
        assert hierarchy_edges == [], "No hierarchy edges when flag is off"

    def test_flag_enabled_has_teeka_edges_emitted(self):
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=True)
        has_teeka = [e for e in frag["edges"] if e.get("type") == "HAS_TEEKA"]
        assert has_teeka, "HAS_TEEKA edges must be emitted when flag is on"
        # HAS_TEEKA is Shastra → Teeka
        for e in has_teeka:
            assert e["from"]["label"] == "Shastra"
            assert e["to"]["label"] == "Teeka"

    def test_flag_enabled_has_publication_edges_when_publication_present(self):
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=True)
        pub_nodes = [n for n in frag["nodes"] if n.get("label") == "Publication"]
        if pub_nodes:
            has_pub = [e for e in frag["edges"] if e.get("type") == "HAS_PUBLICATION"]
            assert has_pub, "HAS_PUBLICATION edges required when Publication nodes are emitted"
            # HAS_PUBLICATION is Teeka → Publication
            for e in has_pub:
                assert e["from"]["label"] == "Teeka"
                assert e["to"]["label"] == "Publication"

    def test_flag_enabled_has_teeka_edges_deduplicated(self):
        """Multiple Teeka nodes from the same Shastra produce only one HAS_TEEKA edge."""
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=True)
        has_teeka = [e for e in frag["edges"] if e.get("type") == "HAS_TEEKA"]
        edge_keys = [(e["from"]["key"], e["to"]["key"]) for e in has_teeka]
        assert len(edge_keys) == len(set(edge_keys)), (
            "HAS_TEEKA edges must be deduplicated"
        )


# ---------------------------------------------------------------------------
# Stub system regression: new labels accepted by sync_stub_node
# ---------------------------------------------------------------------------

class TestStubSystemAcceptsHierarchyLabels:
    """Smoke-test that stubs.py now allows Shastra/Teeka/Publication labels."""

    def test_shastra_label_in_stub_props(self):
        from jain_kb_common.db.neo4j.stubs import _STUB_PROPS_BY_LABEL
        assert "Shastra" in _STUB_PROPS_BY_LABEL, "Shastra must be in stub allowlist"

    def test_teeka_label_in_stub_props(self):
        from jain_kb_common.db.neo4j.stubs import _STUB_PROPS_BY_LABEL
        assert "Teeka" in _STUB_PROPS_BY_LABEL, "Teeka must be in stub allowlist"

    def test_publication_label_in_stub_props(self):
        from jain_kb_common.db.neo4j.stubs import _STUB_PROPS_BY_LABEL
        assert "Publication" in _STUB_PROPS_BY_LABEL, "Publication must be in stub allowlist"

    def test_teeka_stub_props_include_shastra_key(self):
        from jain_kb_common.db.neo4j.stubs import _STUB_PROPS_BY_LABEL
        assert "shastra_natural_key" in _STUB_PROPS_BY_LABEL["Teeka"]

    def test_publication_stub_props_include_teeka_and_publisher(self):
        from jain_kb_common.db.neo4j.stubs import _STUB_PROPS_BY_LABEL
        props = _STUB_PROPS_BY_LABEL["Publication"]
        assert "teeka_natural_key" in props
        assert "publisher_id" in props

    def test_in_shastra_edge_type_in_valid_set(self):
        from jain_kb_common.db.neo4j.stubs import _VALID_EDGE_TYPES
        assert "IN_SHASTRA" in _VALID_EDGE_TYPES

    def test_in_teeka_edge_type_in_valid_set(self):
        from jain_kb_common.db.neo4j.stubs import _VALID_EDGE_TYPES
        assert "IN_TEEKA" in _VALID_EDGE_TYPES

    def test_in_publication_edge_type_in_valid_set(self):
        from jain_kb_common.db.neo4j.stubs import _VALID_EDGE_TYPES
        assert "IN_PUBLICATION" in _VALID_EDGE_TYPES

    def test_has_teeka_edge_type_in_valid_set(self):
        from jain_kb_common.db.neo4j.stubs import _VALID_EDGE_TYPES
        assert "HAS_TEEKA" in _VALID_EDGE_TYPES

    def test_has_publication_edge_type_in_valid_set(self):
        from jain_kb_common.db.neo4j.stubs import _VALID_EDGE_TYPES
        assert "HAS_PUBLICATION" in _VALID_EDGE_TYPES


# ---------------------------------------------------------------------------
# Unit tests: child → immediate parent edges in _derive_hierarchy_nodes
# ---------------------------------------------------------------------------

class TestChildToParentEdges:
    """Each lazy node must produce an edge to its own immediate structural parent."""

    def test_gatha_emits_in_shastra_edge_to_shastra(self):
        _, edges = _derive_hierarchy_nodes("Gatha", "पंचास्तिकाय:गाथा:9")
        child_edge = next((e for e in edges if e["from"]["label"] == "Gatha"), None)
        assert child_edge is not None, "Gatha must emit an edge to its immediate parent"
        assert child_edge["type"] == "IN_SHASTRA"
        assert child_edge["from"] == {"label": "Gatha", "key": "पंचास्तिकाय:गाथा:9"}
        assert child_edge["to"] == {"label": "Shastra", "key": "पंचास्तिकाय"}

    def test_gathateeka_emits_in_teeka_edge_to_teeka(self):
        _, edges = _derive_hierarchy_nodes("GathaTeeka", "समयसार:आत्मख्याति:गाथा:टीका:9")
        child_edge = next((e for e in edges if e["from"]["label"] == "GathaTeeka"), None)
        assert child_edge is not None, "GathaTeeka must emit an edge to its immediate parent"
        assert child_edge["type"] == "IN_TEEKA"
        assert child_edge["from"] == {"label": "GathaTeeka", "key": "समयसार:आत्मख्याति:गाथा:टीका:9"}
        assert child_edge["to"] == {"label": "Teeka", "key": "समयसार:आत्मख्याति"}

    def test_gathateekabhaavarth_emits_in_publication_edge(self):
        _, edges = _derive_hierarchy_nodes(
            "GathaTeekaBhaavarth", "समयसार:आत्मख्याति:3:गाथा:टीका:भावार्थ:9"
        )
        child_edge = next((e for e in edges if e["from"]["label"] == "GathaTeekaBhaavarth"), None)
        assert child_edge is not None, "GathaTeekaBhaavarth must emit an edge to its immediate parent"
        assert child_edge["type"] == "IN_PUBLICATION"
        assert child_edge["from"] == {"label": "GathaTeekaBhaavarth", "key": "समयसार:आत्मख्याति:3:गाथा:टीका:भावार्थ:9"}
        assert child_edge["to"] == {"label": "Publication", "key": "समयसार:आत्मख्याति:3"}

    def test_kalash_emits_in_teeka_edge_to_teeka(self):
        _, edges = _derive_hierarchy_nodes("Kalash", "समयसार:आत्मख्याति:कलश:2")
        child_edge = next((e for e in edges if e["from"]["label"] == "Kalash"), None)
        assert child_edge is not None, "Kalash must emit an edge to its immediate parent"
        assert child_edge["type"] == "IN_TEEKA"
        assert child_edge["from"] == {"label": "Kalash", "key": "समयसार:आत्मख्याति:कलश:2"}
        assert child_edge["to"] == {"label": "Teeka", "key": "समयसार:आत्मख्याति"}

    def test_kalashbhaavarth_emits_in_publication_edge(self):
        _, edges = _derive_hierarchy_nodes(
            "KalashBhaavarth", "समयसार:आत्मख्याति:3:कलश:भावार्थ:2"
        )
        child_edge = next((e for e in edges if e["from"]["label"] == "KalashBhaavarth"), None)
        assert child_edge is not None, "KalashBhaavarth must emit an edge to its immediate parent"
        assert child_edge["type"] == "IN_PUBLICATION"
        assert child_edge["from"] == {"label": "KalashBhaavarth", "key": "समयसार:आत्मख्याति:3:कलश:भावार्थ:2"}
        assert child_edge["to"] == {"label": "Publication", "key": "समयसार:आत्मख्याति:3"}

    def test_page_emits_in_publication_edge(self):
        _, edges = _derive_hierarchy_nodes("Page", "राजवार्तिक:टीका:18:पृष्ठ:95")
        child_edge = next((e for e in edges if e["from"]["label"] == "Page"), None)
        assert child_edge is not None, "Page must emit an edge to its immediate parent"
        assert child_edge["type"] == "IN_PUBLICATION"
        assert child_edge["from"] == {"label": "Page", "key": "राजवार्तिक:टीका:18:पृष्ठ:95"}
        assert child_edge["to"] == {"label": "Publication", "key": "राजवार्तिक:टीका:18"}

    def test_gatha_edge_count(self):
        """Gatha should have exactly 1 edge: Gatha→Shastra (no Teeka/Publication)."""
        _, edges = _derive_hierarchy_nodes("Gatha", "पंचास्तिकाय:गाथा:9")
        assert len(edges) == 1

    def test_gathateeka_edge_count(self):
        """GathaTeeka has 2 edges: Shastra→Teeka (HAS_TEEKA) + GathaTeeka→Teeka (IN_TEEKA)."""
        _, edges = _derive_hierarchy_nodes("GathaTeeka", "समयसार:आत्मख्याति:गाथा:टीका:9")
        assert len(edges) == 2

    def test_gathateekabhaavarth_edge_count(self):
        """GathaTeekaBhaavarth has 3 edges: HAS_TEEKA + HAS_PUBLICATION + IN_PUBLICATION."""
        _, edges = _derive_hierarchy_nodes(
            "GathaTeekaBhaavarth", "समयसार:आत्मख्याति:3:गाथा:टीका:भावार्थ:9"
        )
        assert len(edges) == 3


class TestIntegrationChildToParentEdges:
    """build_neo4j_fragment must include child→parent edges when flag is enabled."""

    def test_in_publication_edges_emitted_when_applicable(self):
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=True)
        pub_nodes = [n for n in frag["nodes"] if n.get("label") == "Publication"]
        if pub_nodes:
            in_pub = [e for e in frag["edges"] if e.get("type") == "IN_PUBLICATION"]
            assert in_pub, "IN_PUBLICATION edges must be emitted when Publication nodes exist"
            for e in in_pub:
                assert e["from"]["label"] in ("GathaTeekaBhaavarth", "KalashBhaavarth", "Page")
                assert e["to"]["label"] == "Publication"

    def test_child_to_parent_edges_absent_when_flag_disabled(self):
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=False)
        child_parent_types = {"HAS_TEEKA", "HAS_PUBLICATION", "IN_SHASTRA", "IN_TEEKA", "IN_PUBLICATION"}
        # When flag is off, no hierarchy edges should exist at all
        hierarchy_edges = [e for e in frag["edges"] if e.get("type") in child_parent_types]
        assert hierarchy_edges == [], "No hierarchy edges when flag is off"

    def test_in_shastra_includes_gatha_to_shastra(self):
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=True)
        lazy_gatha = [n for n in frag["nodes"] if n.get("label") == "Gatha" and n.get("lazy")]
        if lazy_gatha:
            in_shastra_from_gatha = [
                e for e in frag["edges"]
                if e.get("type") == "IN_SHASTRA" and e["from"]["label"] == "Gatha"
            ]
            assert in_shastra_from_gatha, "Gatha nodes must have IN_SHASTRA edges to Shastra"

    def test_in_publication_edges_deduplicated(self):
        frag = _neo4j_fragment(_SWABHAV, _URL, shastra_hierarchy=True)
        in_pub = [e for e in frag["edges"] if e.get("type") == "IN_PUBLICATION"]
        edge_keys = [(e["from"]["key"], e["to"]["key"]) for e in in_pub]
        assert len(edge_keys) == len(set(edge_keys)), "IN_PUBLICATION edges must be deduplicated"
