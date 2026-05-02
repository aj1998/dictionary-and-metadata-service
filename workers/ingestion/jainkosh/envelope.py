"""Build the 'would_write' envelope (pg/mongo/neo4j fragments)."""

from __future__ import annotations

from .models import KeywordParseResult, Subsection, WouldWriteEnvelope


def walk_subsection_tree(subsections: list[Subsection]):
    """Yield all subsections in pre-order (parent before children)."""
    for sub in subsections:
        yield sub
        yield from walk_subsection_tree(sub.children)


def _sub_to_summary(sub: Subsection) -> dict:
    return {
        "natural_key": sub.natural_key,
        "topic_path": sub.topic_path,
        "heading": [{"lang": "hin", "script": "Deva", "text": sub.heading_text}],
        "is_leaf": sub.is_leaf,
        "is_synthetic": sub.is_synthetic,
        "children": [_sub_to_summary(c) for c in sub.children],
    }


def build_pg_fragment(result: KeywordParseResult) -> dict:
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
            })
    return {"keywords": [keyword_row], "topics": topic_rows, "keyword_aliases": []}


def build_mongo_fragment(result: KeywordParseResult) -> dict:
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
                "subsection_tree": [_sub_to_summary(t) for t in s.subsections],
                "extra_blocks": [b.model_dump() for b in s.extra_blocks],
                "index_relations": [r.model_dump() for r in s.index_relations],
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
    return {"keyword_definitions": [kdef], "topic_extracts": topic_extracts}


def _see_also_edge(block, *, source_topic_key: str, keyword_node: str) -> dict:
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
    return {
        "type": edge_type,
        "from": from_node,
        "to": to_node,
        "props": {"weight": 1.0, "source": "jainkosh"},
    }


def _index_relation_edge(rel, src: tuple, *, keyword: str) -> dict:
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


def build_neo4j_fragment(result: KeywordParseResult) -> dict:
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
                    b, source_topic_key=sub.natural_key, keyword_node=result.keyword
                )
                if edge:
                    edges.append(edge)

    # Index relations
    for sec in result.page_sections:
        for rel in sec.index_relations:
            if rel.source_topic_path:
                # Find the topic node for this source_topic_path
                src_nk = None
                for sub in walk_subsection_tree(sec.subsections):
                    if sub.topic_path == rel.source_topic_path:
                        src_nk = sub.natural_key
                        break
                if src_nk:
                    src = ("Topic", src_nk)
                else:
                    src = ("Keyword", result.keyword)
            else:
                src = ("Keyword", result.keyword)

            edge = _index_relation_edge(rel, src, keyword=result.keyword)
            if edge:
                edges.append(edge)

    return {"nodes": _dedupe(nodes), "edges": _dedupe(edges)}


def build_envelope(result: KeywordParseResult) -> WouldWriteEnvelope:
    return WouldWriteEnvelope(
        keyword_parse_result=result,
        would_write={
            "postgres": build_pg_fragment(result),
            "mongo": build_mongo_fragment(result),
            "neo4j": build_neo4j_fragment(result),
        },
    )
