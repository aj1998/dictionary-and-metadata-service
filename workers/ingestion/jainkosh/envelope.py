"""Build the 'would_write' envelope (pg/mongo/neo4j fragments)."""

from __future__ import annotations

from copy import deepcopy
from typing import Optional

from .config import JainkoshConfig, load_config
from .models import KeywordParseResult, Subsection, WouldWriteEnvelope

_DEFAULT_CONTRACTS: dict[str, dict] = {
    "postgres:topics:index_relation_seed": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": [
            "display_text", "is_leaf", "is_synthetic",
            "parent_topic_natural_key", "topic_path",
            "source", "source_subkind",
        ],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:topics", "mongo:topic_extracts", "neo4j:Topic"],
    },
    "postgres:keywords": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["display_text", "source_url"],
        "fields_append": ["definition_doc_ids"],
        "fields_skip_if_set": [],
        "stores": ["postgres:keywords", "mongo:keyword_definitions", "neo4j:Keyword"],
    },
    "postgres:topics": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": [
            "topic_path",
            "display_text",
            "parent_topic_natural_key",
            "is_leaf",
            "is_synthetic",
            "source",
        ],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:topics", "mongo:topic_extracts", "neo4j:Topic"],
    },
    "postgres:topics:label_seed": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": [
            "display_text",
            "is_leaf",
            "is_synthetic",
            "parent_topic_natural_key",
            "topic_path",
            "source",
            "source_subkind",
        ],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:topics", "mongo:topic_extracts", "neo4j:Topic"],
    },
    "postgres:keyword_aliases": {
        "conflict_key": ["keyword_natural_key", "alias_text"],
        "on_conflict": "do_update",
        "fields_replace": ["alias_kind", "source"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:keyword_aliases"],
    },
    "mongo:keyword_definitions": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["page_sections", "redirect_aliases", "source_url"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:keyword_definitions"],
    },
    "mongo:topic_extracts": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": [
            "topic_path",
            "parent_natural_key",
            "is_leaf",
            "heading",
            "blocks",
            "source",
            "source_url",
        ],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:topic_extracts"],
    },
    "neo4j:Keyword": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["display_text", "source_url"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Keyword"],
    },
    "neo4j:Topic": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["display_text_hi", "topic_path", "parent_keyword_natural_key", "source", "is_leaf"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Topic"],
    },
}


def walk_subsection_tree(subsections: list[Subsection]):
    """Yield all subsections in pre-order (parent before children)."""
    for sub in subsections:
        yield sub
        yield from walk_subsection_tree(sub.children)


def build_pg_fragment(result: KeywordParseResult, config: Optional[JainkoshConfig] = None) -> dict:
    if config is None:
        config = load_config()
    keyword_row = {
        "table": "keywords",
        "natural_key": result.keyword,
        "display_text": result.keyword,
        "source_url": result.source_url,
        "definition_doc_ids": [],
    }
    topic_rows = []
    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            topic_rows.append({
                "table": "topics",
                "natural_key": sub.natural_key,
                "topic_path": sub.topic_path,
                "parent_topic_natural_key": sub.parent_natural_key,
                "display_text": [{"lang": "hin", "script": "Deva", "text": sub.heading_text}],
                "source": "jainkosh",
                "parent_keyword_natural_key": result.keyword,
                "is_leaf": sub.is_leaf,
                "is_synthetic": sub.is_synthetic,
                "source_subkind": sub.source_subkind,
            })
    if config.envelope.index_relations_as_topics.enabled:
        topic_rows.extend(_build_index_relation_pg_rows(result, config))
    return {"keywords": [keyword_row], "topics": topic_rows, "keyword_aliases": []}


def build_mongo_fragment(result: KeywordParseResult, config: Optional[JainkoshConfig] = None) -> dict:
    if config is None:
        config = load_config()
    kdef = {
        "collection": "keyword_definitions",
        "natural_key": result.keyword,
        "source_url": result.source_url,
        "page_sections": [
            {
                "section_index": s.section_index,
                "section_kind": s.section_kind,
                "h2_text": s.h2_text,
                "definitions": [d.model_dump() for d in s.definitions],
                "label_topic_seeds": [t.model_dump() for t in s.label_topic_seeds],
                "extra_blocks": [b.model_dump() for b in s.extra_blocks],
            }
            for s in result.page_sections
        ],
        "redirect_aliases": [],
    }
    topic_extracts = []
    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            frag = "#" + sub.topic_path if sub.topic_path else ""
            topic_extracts.append({
                "collection": "topic_extracts",
                "natural_key": sub.natural_key,
                "topic_path": sub.topic_path,
                "parent_natural_key": sub.parent_natural_key,
                "is_leaf": sub.is_leaf,
                "heading": [{"lang": "hin", "script": "Deva", "text": sub.heading_text}],
                "blocks": [b.model_dump() for b in sub.blocks],
                "source": "jainkosh",
                "source_url": f"{result.source_url}{frag}",
            })
    if config.envelope.index_relations_as_topics.enabled:
        topic_extracts.extend(_build_index_relation_mongo_extracts(result, config))
    return {"keyword_definitions": [kdef], "topic_extracts": topic_extracts}


def _redlink_edge_allowed(target_exists: bool, to_node: dict, config: JainkoshConfig) -> bool:
    if target_exists:
        return True
    mode = config.neo4j.redlink_edges
    if mode == "always":
        return True
    if mode == "never":
        return False
    if mode == "only_if_topic":
        return to_node.get("label") == "Topic"
    return False


def _see_also_edge(block, *, source_topic_key: str, keyword_node: str, config: JainkoshConfig) -> dict:
    from_node = {"label": "Topic", "key": source_topic_key}
    if block.target_topic_path and block.target_keyword:
        to_node = {
            "label": "Topic",
            "resolve_by": {
                "parent_keyword": block.target_keyword,
                "topic_path": block.target_topic_path,
            },
        }
        edge_type = "RELATED_TO"
    elif block.target_keyword:
        to_node = {"label": "Keyword", "key": block.target_keyword}
        edge_type = "RELATED_TO"
    elif block.is_self and block.target_topic_path:
        to_node = {
            "label": "Topic",
            "resolve_by": {
                "parent_keyword": keyword_node,
                "topic_path": block.target_topic_path,
            },
        }
        edge_type = "RELATED_TO"
    else:
        return {}
    if not _redlink_edge_allowed(block.target_exists, to_node, config):
        return {}
    return {
        "type": edge_type,
        "from": from_node,
        "to": to_node,
        "props": {"weight": 1.0, "source": "jainkosh"},
    }


def _index_relation_edge(rel, src: tuple, *, keyword: str, config: JainkoshConfig) -> dict:
    src_label, src_key = src
    from_node = {"label": src_label, "key": src_key}

    if rel.target_topic_path and rel.target_keyword:
        to_node = {
            "label": "Topic",
            "resolve_by": {
                "parent_keyword": rel.target_keyword,
                "topic_path": rel.target_topic_path,
            },
        }
    elif rel.target_keyword:
        to_node = {"label": "Keyword", "key": rel.target_keyword}
    elif rel.is_self and rel.target_topic_path:
        to_node = {
            "label": "Topic",
            "resolve_by": {
                "parent_keyword": keyword,
                "topic_path": rel.target_topic_path,
            },
        }
    else:
        return {}

    if not _redlink_edge_allowed(rel.target_exists, to_node, config):
        return {}

    return {
        "type": "RELATED_TO",
        "from": from_node,
        "to": to_node,
        "props": {"weight": 1.0, "source": "jainkosh", "target_exists": rel.target_exists},
    }


def _dedupe(items: list[dict]) -> list[dict]:
    """Deduplicate list of dicts by converting to JSON strings."""
    import json
    seen = set()
    out = []
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _index_relation_topic_natural_key(
    rel, keyword: str, config: JainkoshConfig
) -> str:
    from .topic_keys import slug as _slug
    sl = _slug(rel.label_text, config)
    parent_nk = (
        rel.source_topic_natural_key_chain[-1]
        if rel.source_topic_natural_key_chain
        else keyword
    )
    return f"{parent_nk}:{sl}"


def _index_relation_parent_nk(rel, keyword: str) -> Optional[str]:
    if rel.source_topic_natural_key_chain:
        return rel.source_topic_natural_key_chain[-1]
    return None


def _build_index_relation_pg_rows(
    result, config: JainkoshConfig
) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for sec in result.page_sections:
        for rel in sec.index_relations:
            nk = _index_relation_topic_natural_key(rel, result.keyword, config)
            if nk in seen:
                continue
            seen.add(nk)
            parent_nk = _index_relation_parent_nk(rel, result.keyword)
            rows.append({
                "table": "topics",
                "natural_key": nk,
                "topic_path": None,
                "parent_topic_natural_key": parent_nk,
                "display_text": [{"lang": "hin", "script": "Deva", "text": rel.label_text}],
                "source": "jainkosh",
                "parent_keyword_natural_key": result.keyword,
                "is_leaf": True,
                "is_synthetic": True,
                "source_subkind": "index_relation_seed",
                "label_topic_seed": True,
            })
    return rows


def _build_index_relation_mongo_extracts(
    result, config: JainkoshConfig
) -> list[dict]:
    extracts = []
    seen: set[str] = set()
    for sec in result.page_sections:
        for rel in sec.index_relations:
            nk = _index_relation_topic_natural_key(rel, result.keyword, config)
            if nk in seen:
                continue
            seen.add(nk)
            parent_nk = _index_relation_parent_nk(rel, result.keyword)
            extracts.append({
                "collection": "topic_extracts",
                "natural_key": nk,
                "topic_path": None,
                "parent_natural_key": parent_nk,
                "is_leaf": True,
                "heading": [{"lang": "hin", "script": "Deva", "text": rel.label_text}],
                "blocks": [],
                "source": "jainkosh",
                "source_url": result.source_url,
            })
    return extracts


def _build_index_relation_neo4j(
    result, config: JainkoshConfig
) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) for index-relation topics."""
    if not config.envelope.index_relations_as_topics.enabled:
        return [], []
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nk: set[str] = set()
    for sec in result.page_sections:
        for rel in sec.index_relations:
            nk = _index_relation_topic_natural_key(rel, result.keyword, config)
            if nk not in seen_nk:
                seen_nk.add(nk)
                nodes.append({
                    "label": "Topic",
                    "key": nk,
                    "props": {
                        "display_text_hi": rel.label_text,
                        "topic_path": None,
                        "parent_keyword_natural_key": result.keyword,
                        "source": "jainkosh",
                        "is_leaf": True,
                    },
                })
                parent_nk = _index_relation_parent_nk(rel, result.keyword)
                if parent_nk is not None:
                    edges.append({
                        "type": "PART_OF",
                        "from": {"label": "Topic", "key": nk},
                        "to": {"label": "Topic", "key": parent_nk},
                        "props": {"weight": 1.0, "source": "jainkosh"},
                    })
                else:
                    edges.append({
                        "type": "HAS_TOPIC",
                        "from": {"label": "Keyword", "key": result.keyword},
                        "to": {"label": "Topic", "key": nk},
                        "props": {"weight": 1.0, "source": "jainkosh"},
                    })

            edge = _index_relation_edge(rel, ("Topic", nk), keyword=result.keyword, config=config)
            if edge:
                edges.append(edge)

    return nodes, edges


def build_neo4j_fragment(result: KeywordParseResult, config: JainkoshConfig) -> dict:
    nodes = [
        {
            "label": "Keyword",
            "key": result.keyword,
            "props": {
                "display_text": result.keyword,
                "source_url": result.source_url,
            },
        }
    ]
    edges = []

    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            nodes.append({
                "label": "Topic",
                "key": sub.natural_key,
                "props": {
                    "display_text_hi": sub.heading_text,
                    "topic_path": sub.topic_path,
                    "parent_keyword_natural_key": result.keyword,
                    "source": "jainkosh",
                    "is_leaf": sub.is_leaf,
                },
            })

            if sub.parent_natural_key is None:
                # Keyword → Topic
                edges.append({
                    "type": "HAS_TOPIC",
                    "from": {"label": "Keyword", "key": result.keyword},
                    "to": {"label": "Topic", "key": sub.natural_key},
                    "props": {"weight": 1.0, "source": "jainkosh"},
                })
            else:
                # Topic → Topic (PART_OF: child → parent)
                edges.append({
                    "type": "PART_OF",
                    "from": {"label": "Topic", "key": sub.natural_key},
                    "to": {"label": "Topic", "key": sub.parent_natural_key},
                    "props": {"weight": 1.0, "source": "jainkosh"},
                })

            for b in sub.blocks:
                if b.kind != "see_also":
                    continue
                edge = _see_also_edge(
                    b, source_topic_key=sub.natural_key, keyword_node=result.keyword, config=config
                )
                if edge:
                    edges.append(edge)

    ir_nodes, ir_edges = _build_index_relation_neo4j(result, config)
    nodes.extend(ir_nodes)
    edges.extend(ir_edges)

    return {"nodes": _dedupe(nodes), "edges": _dedupe(edges)}


def build_envelope(result: KeywordParseResult, config: Optional[JainkoshConfig] = None) -> WouldWriteEnvelope:
    if config is None:
        config = load_config()
    return WouldWriteEnvelope(
        keyword_parse_result=result,
        would_write={
            "postgres": build_pg_fragment(result, config),
            "mongo": build_mongo_fragment(result, config),
            "neo4j": build_neo4j_fragment(result, config),
            "idempotency_contracts": _build_contracts(result),
        },
    )


def _has_label_seed_topic(result: KeywordParseResult) -> bool:
    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            if sub.label_topic_seed:
                return True
    return False


def _has_index_relation_topic(result: KeywordParseResult) -> bool:
    for sec in result.page_sections:
        if sec.index_relations:
            return True
    return False


def _build_contracts(result: KeywordParseResult) -> dict[str, dict]:
    keys = {
        "postgres:keywords",
        "postgres:topics",
        "postgres:keyword_aliases",
        "mongo:keyword_definitions",
        "mongo:topic_extracts",
        "neo4j:Keyword",
        "neo4j:Topic",
    }
    if _has_label_seed_topic(result):
        keys.add("postgres:topics:label_seed")
    if _has_index_relation_topic(result):
        keys.add("postgres:topics:index_relation_seed")
    return {k: deepcopy(_DEFAULT_CONTRACTS[k]) for k in sorted(keys)}
