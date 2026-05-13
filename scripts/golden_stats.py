#!/usr/bin/env python3
"""Print parse-result counts from golden JSON files (used to update README table)."""

import json
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent.parent / "workers" / "ingestion" / "jainkosh" / "tests" / "golden"
PAGES = ["आत्मा", "द्रव्य", "पर्याय"]


def count_subsections_recursive(nodes: list) -> int:
    total = len(nodes)
    for node in nodes:
        total += count_subsections_recursive(node.get("children", []))
    return total


def count_resolved_refs_in_blocks(blocks: list) -> int:
    count = 0
    for block in blocks:
        for ref in block.get("references", []):
            if ref.get("resolved_fields"):
                count += 1
    return count


def count_resolved_refs_in_subsections(subsections: list) -> int:
    count = 0
    for sub in subsections:
        count += count_resolved_refs_in_blocks(sub.get("blocks", []))
        count += count_resolved_refs_in_subsections(sub.get("children", []))
        count += count_resolved_refs_in_subsections(sub.get("subsections", []))
    return count


def count_resolved_refs(sections: list) -> int:
    count = 0
    for section in sections:
        for defn in section.get("definitions", []):
            count += count_resolved_refs_in_blocks(defn.get("blocks", []))
        count += count_resolved_refs_in_subsections(section.get("subsections", []))
    return count


def md_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    col_widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    def fmt_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells)) + " |"
    sep = "| " + " | ".join("-" * w for w in col_widths) + " |"
    lines = [f"### {title}", fmt_row(headers), sep] + [fmt_row(r) for r in rows]
    return "\n".join(lines)


def stats(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    kpr = data["keyword_parse_result"]
    sections = kpr["page_sections"]
    warnings = kpr["warnings"]
    neo4j = data["would_write"]["neo4j"]

    sk_defs = sum(
        len(s.get("definitions", []))
        for s in sections
        if s.get("section_kind") == "siddhantkosh"
    )
    pk_defs = sum(
        len(s.get("definitions", []))
        for s in sections
        if s.get("section_kind") == "puraankosh"
    )
    index_rels = sum(
        len(s.get("index_relations", []))
        for s in sections
        if s.get("section_kind") == "siddhantkosh"
    )
    total_subs = sum(
        count_subsections_recursive(s.get("subsections", []))
        for s in sections
    )

    keyword = kpr["keyword"]

    def node_label(node: dict) -> str:
        label = node["label"]
        key = node["key"]
        if label == "Keyword":
            return "Keyword (ext)" if key != keyword else "Keyword (int)"
        if label == "Topic":
            return "Topic (ext)" if not key.startswith(keyword + ":") else "Topic (int)"
        return label

    non_lazy_nodes = [n for n in neo4j["nodes"] if not n.get("lazy")]
    lazy_nodes = [n for n in neo4j["nodes"] if n.get("lazy")]

    node_type_counts: dict[str, int] = {}
    for n in non_lazy_nodes:
        lbl = node_label(n)
        node_type_counts[lbl] = node_type_counts.get(lbl, 0) + 1

    lazy_node_type_counts: dict[str, int] = {}
    for n in lazy_nodes:
        lbl = n["label"]
        lazy_node_type_counts[lbl] = lazy_node_type_counts.get(lbl, 0) + 1

    edge_type_counts: dict[str, int] = {}
    for e in neo4j["edges"]:
        etype = e["type"]
        edge_type_counts[etype] = edge_type_counts.get(etype, 0) + 1

    keywords_total = node_type_counts.get("Keyword (int)", 0) + node_type_counts.get("Keyword (ext)", 0)
    topics_total = node_type_counts.get("Topic (int)", 0) + node_type_counts.get("Topic (ext)", 0)

    return {
        "sk_defs": sk_defs,
        "pk_defs": pk_defs,
        "index_rels": index_rels,
        "total_subs": total_subs,
        "keywords": keywords_total,
        "topics": topics_total,
        "nodes": len(non_lazy_nodes),
        "edges": len(neo4j["edges"]),
        "refs_resolved": count_resolved_refs(sections),
        "warnings": len(warnings),
        "node_type_counts": node_type_counts,
        "lazy_node_type_counts": lazy_node_type_counts,
        "edge_type_counts": edge_type_counts,
    }


def _int_ext_sort_key(label: str) -> tuple:
    """Sort (int) before (ext), otherwise alphabetical."""
    if label.endswith(" (int)"):
        return (label[:-6], 0)
    if label.endswith(" (ext)"):
        return (label[:-6], 1)
    return (label, 2)


def main() -> None:
    all_node_types: set[str] = set()
    all_lazy_node_types: set[str] = set()
    all_edge_types: set[str] = set()
    page_stats: list[tuple[str, dict]] = []

    for page in PAGES:
        path = GOLDEN_DIR / f"{page}.json"
        if not path.exists():
            print(f"*{page}: golden not found*")
            continue
        s = stats(path)
        page_stats.append((page, s))
        all_node_types.update(s["node_type_counts"].keys())
        all_lazy_node_types.update(s["lazy_node_type_counts"].keys())
        all_edge_types.update(s["edge_type_counts"].keys())

    # Summary table
    summary_headers = [
        "Page", "SK defs", "PK defs", "Idx rels", "Subsections",
        "Keywords (int+ext)", "Topics (int+ext)", "Nodes", "Edges", "Refs (Res)", "Warnings",
    ]
    summary_rows = [
        [
            page,
            str(s["sk_defs"]),
            str(s["pk_defs"]),
            str(s["index_rels"]),
            str(s["total_subs"]),
            str(s["keywords"]),
            str(s["topics"]),
            str(s["nodes"]),
            str(s["edges"]),
            str(s["refs_resolved"]),
            str(s["warnings"]),
        ]
        for page, s in page_stats
    ]
    print(md_table("Summary", summary_headers, summary_rows))

    # Nodes table
    print()
    node_types = sorted(all_node_types, key=_int_ext_sort_key)
    lazy_node_types = sorted(all_lazy_node_types)
    all_combined = node_types + [f"{t} (lazy)" for t in lazy_node_types]
    node_headers = ["Page"] + all_combined
    node_rows = []
    for page, s in page_stats:
        row = [page]
        for t in all_combined:
            if t.endswith(" (lazy)"):
                key = t[: -len(" (lazy)")]
                val = s["lazy_node_type_counts"].get(key, 0)
            else:
                val = s["node_type_counts"].get(t, 0)
            row.append(str(val))
        node_rows.append(row)
    print(md_table("Nodes", node_headers, node_rows))

    # Edges table
    print()
    edge_types = sorted(all_edge_types)
    edge_headers = ["Page"] + edge_types
    edge_rows = [
        [page] + [str(s["edge_type_counts"].get(t, 0)) for t in edge_types]
        for page, s in page_stats
    ]
    print(md_table("Edges", edge_headers, edge_rows))


if __name__ == "__main__":
    main()
