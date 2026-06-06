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


def _see_also_kw_edge(block, *, keyword_node: str, config: JainkoshConfig) -> dict:
    """RELATED_TO edge where the source is a Keyword (definition context)."""
    from_node = {"label": "Keyword", "key": keyword_node}
    if block.target_topic_path and block.target_keyword:
        to_node = {
            "label": "Topic",
            "resolve_by": {
                "parent_keyword": block.target_keyword,
                "topic_path": block.target_topic_path,
            },
        }
    elif block.target_keyword:
        to_node = {"label": "Keyword", "key": block.target_keyword}
    elif block.is_self and block.target_topic_path:
        to_node = {
            "label": "Topic",
            "resolve_by": {
                "parent_keyword": keyword_node,
                "topic_path": block.target_topic_path,
            },
        }
    else:
        return {}
    if not _redlink_edge_allowed(block.target_exists, to_node, config):
        return {}
    return {
        "type": "RELATED_TO",
        "from": from_node,
        "to": to_node,
        "props": {"weight": 1.0, "source": "jainkosh"},
    }


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


def _node_identity(item: dict) -> tuple:
    """Return (label, key_or_resolve_key) for node deduplication."""
    return (item.get("label", ""), item.get("key") or item.get("resolve_key", ""))


def _dedupe(items: list[dict]) -> list[dict]:
    """Deduplicate nodes and edges.

    Nodes: keyed on (label, key or resolve_key); real nodes win over stub seeds / lazy nodes.
    Edges: keyed on (type, from, to, mention_path); resolve_by and resolve_key fields included
           so that distinct cross-page targets are preserved.
    """
    seen_edges: set = set()
    out_edges: list[dict] = []
    node_map: dict = {}   # (label, key_or_rk) → item
    node_order: list = []  # insertion-order list of (label, key_or_rk) tuples

    for item in items:
        if "type" in item and "from" in item and "to" in item:
            frm = item["from"]
            to = item["to"]
            rb = to.get("resolve_by")
            to_key = (
                to.get("label", ""),
                to.get("key", "") or to.get("resolve_key", ""),
                rb.get("parent_keyword", "") if rb else "",
                rb.get("topic_path", "") if rb else "",
            )
            key = (
                item["type"],
                frm.get("label", ""), frm.get("key", ""),
                *to_key,
                item.get("props", {}).get("mention_path", ""),
            )
            if key not in seen_edges:
                seen_edges.add(key)
                out_edges.append(item)
        else:
            nk = _node_identity(item)
            is_stub = item.get("is_stub_seed") or item.get("lazy")
            if nk not in node_map:
                node_map[nk] = item
                node_order.append(nk)
            else:
                existing = node_map[nk]
                existing_is_stub = existing.get("is_stub_seed") or existing.get("lazy")
                if existing_is_stub and not is_stub:
                    node_map[nk] = item  # real node wins

    return [node_map[nk] for nk in node_order] + out_edges


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


LAZY_NODE_LABELS = {"Gatha", "GathaTeeka", "GathaTeekaBhaavarth", "Kalash", "KalashBhaavarth", "Page"}


def _derive_hierarchy_nodes(label: str, key: str) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) for the parent Shastra/Teeka/Publication hierarchy.

    Parses the structured key to extract the shastra, teeka, and publication
    components, emitting lazy stub nodes and the connecting structural edges
    (IN_SHASTRA: Teeka→Shastra, IN_TEEKA: Publication→Teeka).
    """
    props = _derive_props(label, key)
    nodes: list[dict] = []
    edges: list[dict] = []

    teeka_nk: str | None = props.get("teeka_natural_key")
    shastra_nk: str | None = props.get("shastra_natural_key")
    pub_id: str | None = props.get("publisher_id")

    # Kalash props don't include shastra_natural_key; derive from teeka_nk prefix
    if teeka_nk and not shastra_nk:
        shastra_nk = teeka_nk.split(":")[0]

    if shastra_nk:
        nodes.append({
            "label": "Shastra",
            "key": shastra_nk,
            "props": {},
            "lazy": True,
        })

    if teeka_nk:
        nodes.append({
            "label": "Teeka",
            "key": teeka_nk,
            "props": {"shastra_natural_key": shastra_nk} if shastra_nk else {},
            "lazy": True,
        })
        if shastra_nk:
            edges.append({
                "type": "IN_SHASTRA",
                "from": {"label": "Teeka", "key": teeka_nk},
                "to": {"label": "Shastra", "key": shastra_nk},
                "props": {"source": "jainkosh"},
            })

    pub_nk: str | None = None
    if teeka_nk and pub_id:
        pub_nk = f"{teeka_nk}:{pub_id}"
        nodes.append({
            "label": "Publication",
            "key": pub_nk,
            "props": {"teeka_natural_key": teeka_nk, "publisher_id": pub_id},
            "lazy": True,
        })
        edges.append({
            "type": "IN_TEEKA",
            "from": {"label": "Publication", "key": pub_nk},
            "to": {"label": "Teeka", "key": teeka_nk},
            "props": {"source": "jainkosh"},
        })

    # Edge from the child node itself to its immediate structural parent
    if label == "Gatha" and shastra_nk:
        edges.append({
            "type": "IN_SHASTRA",
            "from": {"label": "Gatha", "key": key},
            "to": {"label": "Shastra", "key": shastra_nk},
            "props": {"source": "jainkosh"},
        })
    elif label in ("GathaTeeka", "Kalash") and teeka_nk:
        edges.append({
            "type": "IN_TEEKA",
            "from": {"label": label, "key": key},
            "to": {"label": "Teeka", "key": teeka_nk},
            "props": {"source": "jainkosh"},
        })
    elif label in ("GathaTeekaBhaavarth", "KalashBhaavarth", "Page") and pub_nk:
        edges.append({
            "type": "IN_PUBLICATION",
            "from": {"label": label, "key": key},
            "to": {"label": "Publication", "key": pub_nk},
            "props": {"source": "jainkosh"},
        })

    return nodes, edges


def _last_segment_unhyphen(topic_path: str) -> str:
    """Return the last dot-separated segment with hyphens replaced by spaces."""
    seg = topic_path.split(".")[-1] if topic_path else ""
    return seg.replace("-", " ")


def _resolve_rb_natural_key(
    parent_keyword: str,
    topic_path: str,
    current_keyword: str,
    path_to_nk: dict[str, str],
) -> str:
    """Convert a resolve_by target to a natural key.

    For same-keyword references, looks up the exact heading-based key from the
    current envelope.  For cross-page references, falls back to a placeholder
    key ({parent_keyword}:{path_with_colons}) which allows edge creation but
    may not match when the target page is later ingested.
    """
    if parent_keyword == current_keyword:
        return path_to_nk.get(topic_path, f"{parent_keyword}:{topic_path.replace('.', ':')}")
    return f"{parent_keyword}:{topic_path.replace('.', ':')}"


def _derive_props(label: str, key: str) -> dict:
    if label == "Gatha":
        # key: {shastra}:गाथा:{n}
        prefix, n = key.rsplit(":गाथा:", 1)
        return {"shastra_natural_key": prefix, "gatha_number": n}
    if label == "Kalash":
        # key: {shastra}:{teeka}:कलश:{n}
        prefix, n = key.rsplit(":कलश:", 1)
        return {"teeka_natural_key": prefix, "kalash_number": n}
    if label == "GathaTeeka":
        # key: {shastra}:{teeka}:गाथा:टीका:{n}
        prefix, n = key.rsplit(":गाथा:टीका:", 1)
        shastra = prefix.split(":")[0]
        return {"shastra_natural_key": shastra, "teeka_natural_key": prefix, "gatha_number": n}
    if label == "GathaTeekaBhaavarth":
        # key: {shastra}:{teeka}:{pub_id}:गाथा:टीका:भावार्थ:{n}
        prefix, n = key.rsplit(":गाथा:टीका:भावार्थ:", 1)
        parts = prefix.split(":")
        shastra = parts[0]
        pub_id = parts[-1]
        teeka_nk = ":".join(parts[:-1])
        return {
            "shastra_natural_key": shastra,
            "teeka_natural_key": teeka_nk,
            "publisher_id": pub_id,
            "gatha_number": n,
        }
    if label == "KalashBhaavarth":
        # key: {shastra}:{teeka}:{pub_id}:कलश:भावार्थ:{n}
        prefix, n = key.rsplit(":कलश:भावार्थ:", 1)
        parts = prefix.split(":")
        shastra = parts[0]
        pub_id = parts[-1]
        teeka_nk = ":".join(parts[:-1])
        return {
            "shastra_natural_key": shastra,
            "teeka_natural_key": teeka_nk,
            "publisher_id": pub_id,
            "kalash_number": n,
        }
    if label == "Page":
        # key: {shastra}:{teeka}:{pub_id}:पृष्ठ:{n}
        prefix, n = key.rsplit(":पृष्ठ:", 1)
        parts = prefix.split(":")
        shastra = parts[0]
        pub_id = parts[-1]
        teeka_nk = ":".join(parts[:-1])
        return {
            "shastra_natural_key": shastra,
            "teeka_natural_key": teeka_nk,
            "publisher_id": pub_id,
            "page_number": n,
        }
    return {}


def _collect_lazy_nodes(ref_edges: list[dict], nodes: list[dict]) -> None:
    for edge in ref_edges:
        src = edge["from"]
        label = src["label"]
        key = src["key"]
        if label in LAZY_NODE_LABELS:
            nodes.append({
                "label": label,
                "key": key,
                "props": _derive_props(label, key),
                "lazy": True,
            })


def build_neo4j_fragment(result: KeywordParseResult, config: JainkoshConfig) -> dict:
    from .reference_edges import build_reference_edges

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

            topic_target = {"label": "Topic", "key": sub.natural_key}
            for i, b in enumerate(sub.blocks):
                if b.kind == "see_also":
                    edge = _see_also_edge(
                        b, source_topic_key=sub.natural_key, keyword_node=result.keyword, config=config
                    )
                    if edge:
                        edges.append(edge)
                else:
                    ref_edges = build_reference_edges(
                        b, target=topic_target, edge_type="MENTIONS_TOPIC", config=config,
                        block_index=i,
                        mention_path=f"{sub.natural_key}/{i}",
                        source_natural_key=sub.natural_key,
                    )
                    _collect_lazy_nodes(ref_edges, nodes)
                    edges.extend(ref_edges)

    for sec in result.page_sections:
        if sec.section_kind == "puraankosh":
            continue
        kw_target = {"label": "Keyword", "key": result.keyword}
        for d in sec.definitions:
            for i, b in enumerate(d.blocks):
                if b.kind == "see_also":
                    edge = _see_also_kw_edge(b, keyword_node=result.keyword, config=config)
                    if edge:
                        edges.append(edge)
                else:
                    ref_edges = build_reference_edges(
                        b, target=kw_target, edge_type="CONTAINS_DEFINITION", config=config,
                        block_index=i,
                        mention_path=f"{sec.section_index}/{d.definition_index}/{i}",
                        source_natural_key=result.keyword,
                        section_index=sec.section_index,
                        definition_index=d.definition_index,
                    )
                    _collect_lazy_nodes(ref_edges, nodes)
                    edges.extend(ref_edges)

    ir_nodes, ir_edges = _build_index_relation_neo4j(result, config)
    nodes.extend(ir_nodes)
    _collect_lazy_nodes(ir_edges, nodes)
    edges.extend(ir_edges)

    # Build topic_path → natural_key map for same-keyword resolve_by lookup
    _path_to_nk: dict[str, str] = {}
    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            if sub.topic_path:
                _path_to_nk[sub.topic_path] = sub.natural_key

    # Resolve resolve_by edges → concrete keys; collect stub seeds
    stub_seeds: list[dict] = []
    resolved_edges: list[dict] = []
    for edge in edges:
        to = edge.get("to", {})
        rb = to.get("resolve_by")
        if rb:
            rb_parent = rb["parent_keyword"]
            rb_path = rb["topic_path"]
            target_exists = edge.get("props", {}).get("target_exists", True)
            if not target_exists:
                # Redlinks: drop per spec (no stub for non-existent pages)
                continue
            new_edge = dict(edge)
            if rb_parent == result.keyword:
                # Same-keyword self-reference: heading-based key is available now.
                nk = _resolve_rb_natural_key(rb_parent, rb_path, result.keyword, _path_to_nk)
                stub_seeds.append({
                    "label": "Topic",
                    "key": nk,
                    "is_stub_seed": True,
                    "props": {
                        "display_text_hi": _last_segment_unhyphen(rb_path),
                        "topic_path": rb_path,
                        "parent_keyword_natural_key": rb_parent,
                    },
                })
                new_edge["to"] = {"label": "Topic", "key": nk}
            else:
                # Cross-page reference: use resolve_key so the ingestion layer can
                # look up the actual natural_key from Postgres once the target
                # keyword has been ingested, rather than landing on a permanent
                # numeric-path placeholder key (e.g. "स्वभाव:2") that never
                # matches the real node ("स्वभाव:स्वभाव-व-शक्ति-निर्देश").
                rk = f"{rb_parent}:{rb_path.replace('.', ':')}"
                stub_seeds.append({
                    "label": "Topic",
                    "resolve_key": rk,
                    "is_stub_seed": True,
                    "props": {
                        "display_text_hi": _last_segment_unhyphen(rb_path),
                        "topic_path": rb_path,
                        "parent_keyword_natural_key": rb_parent,
                    },
                })
                new_edge["to"] = {"label": "Topic", "resolve_key": rk}
            resolved_edges.append(new_edge)
        else:
            # Cross-page Keyword references get a Keyword stub seed
            if (
                to.get("label") == "Keyword"
                and to.get("key")
                and to["key"] != result.keyword
            ):
                stub_seeds.append({
                    "label": "Keyword",
                    "key": to["key"],
                    "is_stub_seed": True,
                    "props": {"display_text": to["key"]},
                })
            resolved_edges.append(edge)

    nodes.extend(stub_seeds)

    # When shastra_hierarchy is enabled, emit stub nodes for Shastra/Teeka/Publication
    # ancestors of each lazy reference node (Gatha, GathaTeeka, etc.) so the full
    # structural hierarchy is present in Neo4j even before dedicated shastra ingestion.
    if config.envelope.shastra_hierarchy.enabled:
        hierarchy_nodes: list[dict] = []
        hierarchy_edges: list[dict] = []
        for node in nodes:
            if node.get("lazy") and node.get("label") in LAZY_NODE_LABELS:
                h_nodes, h_edges = _derive_hierarchy_nodes(node["label"], node["key"])
                hierarchy_nodes.extend(h_nodes)
                hierarchy_edges.extend(h_edges)
        nodes.extend(hierarchy_nodes)
        resolved_edges.extend(hierarchy_edges)

    return {"nodes": _dedupe(nodes), "edges": _dedupe(resolved_edges)}


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
