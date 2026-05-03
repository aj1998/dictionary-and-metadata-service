"""Tests: index relations are materialised as topics in the would_write envelope."""
from pathlib import Path
from datetime import datetime

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.envelope import build_envelope


_DRAVYA = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"
_URL = "https://www.jainkosh.org/wiki/%E0%A4%A6%E0%A5%8D%E0%A4%B0%E0%A4%B5%E0%A5%8D%E0%A4%AF"
_FROZEN = datetime(2026, 5, 2)


def _envelope():
    cfg = load_config()
    html = _DRAVYA.read_text(encoding="utf-8")
    result = parse_keyword_html(html, _URL, cfg, frozen_time=_FROZEN)
    return build_envelope(result, cfg)


def test_index_relations_absent_from_mongo_page_sections():
    env = _envelope()
    kdef_list = env.would_write["mongo"]["keyword_definitions"]
    assert kdef_list, "keyword_definitions must be present"
    for page_sec in kdef_list[0]["page_sections"]:
        assert "index_relations" not in page_sec, (
            "index_relations must not appear in would_write.mongo page_sections"
        )


def test_index_relation_topics_in_postgres():
    env = _envelope()
    topic_rows = env.would_write["postgres"]["topics"]

    matching = [r for r in topic_rows if "अर्थक्रियाकारित्व" in r["natural_key"]]
    assert matching, "index-relation topic for अर्थक्रियाकारित्व must exist in postgres topics"
    row = matching[0]
    assert row["is_synthetic"] is True
    assert row["label_topic_seed"] is True
    assert row["source_subkind"] == "index_relation_seed"
    assert row["topic_path"] is None


def test_index_relation_topics_in_mongo_topic_extracts():
    env = _envelope()
    extracts = env.would_write["mongo"]["topic_extracts"]
    matching = [e for e in extracts if "अर्थक्रियाकारित्व" in e["natural_key"]]
    assert matching, "mongo topic_extract for अर्थक्रियाकारित्व must exist"
    ext = matching[0]
    assert ext["blocks"] == []


def test_index_relation_topics_in_neo4j_nodes():
    env = _envelope()
    nodes = env.would_write["neo4j"]["nodes"]
    topic_nks = {n["key"] for n in nodes if n.get("label") == "Topic"}
    matching = [k for k in topic_nks if "अर्थक्रियाकारित्व" in k]
    assert matching, "neo4j Topic node for अर्थक्रियाकारित्व must exist"


def test_index_relation_related_to_edge_from_label_topic():
    env = _envelope()
    edges = env.would_write["neo4j"]["edges"]
    related_to_edges = [e for e in edges if e.get("type") == "RELATED_TO"]
    label_topic_to_vastu = [
        e for e in related_to_edges
        if "अर्थक्रियाकारित्व" in e.get("from", {}).get("key", "")
        and e.get("to", {}).get("key") == "वस्तु"
    ]
    assert label_topic_to_vastu, (
        "RELATED_TO edge from label-topic for अर्थक्रियाकारित्व to keyword वस्तु must exist"
    )


def test_index_relation_part_of_edge_to_parent_topic():
    env = _envelope()
    edges = env.would_write["neo4j"]["edges"]
    part_of_edges = [e for e in edges if e.get("type") == "PART_OF"]
    matching = [
        e for e in part_of_edges
        if "अर्थक्रियाकारित्व" in e.get("from", {}).get("key", "")
        and "द्रव्य-के-भेद-व-लक्षण" in e.get("to", {}).get("key", "")
    ]
    assert matching, "PART_OF edge from label-topic to parent topic must exist"


def test_no_old_index_relation_edge_from_parent_topic():
    """The old code emitted RELATED_TO from the parent topic (chain[-1]).
    After the fix, no RELATED_TO should come from the parent directly for index relations."""
    env = _envelope()
    edges = env.would_write["neo4j"]["edges"]
    old_style = [
        e for e in edges
        if e.get("type") == "RELATED_TO"
        and e.get("from", {}).get("key") == "द्रव्य:द्रव्य-के-भेद-व-लक्षण"
        and e.get("to", {}).get("key") == "वस्तु"
    ]
    assert not old_style, (
        "RELATED_TO must NOT be emitted from the parent topic directly; "
        "it must come from the label-topic node"
    )


def test_idempotency_contract_includes_index_relation_seed():
    env = _envelope()
    contracts = env.would_write.get("idempotency_contracts", {})
    assert "postgres:topics:index_relation_seed" in contracts
