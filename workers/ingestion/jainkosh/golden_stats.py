#!/usr/bin/env python3
"""Print parse-result counts from golden JSON files (used to update README table)."""

import json
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent / "tests" / "golden"
PAGES = ["आत्मा", "द्रव्य", "पर्याय"]


def count_subsections_recursive(nodes: list) -> int:
    total = len(nodes)
    for node in nodes:
        total += count_subsections_recursive(node.get("children", []))
    return total


def stats(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    kpr = data["keyword_parse_result"]
    sections = kpr["page_sections"]
    warnings = kpr["warnings"]
    postgres = data["would_write"]["postgres"]
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
    return {
        "sk_defs": sk_defs,
        "pk_defs": pk_defs,
        "index_rels": index_rels,
        "total_subs": total_subs,
        "keywords": len(postgres["keywords"]),
        "topics": len(postgres["topics"]),
        "nodes": len(neo4j["nodes"]),
        "edges": len(neo4j["edges"]),
        "warnings": len(warnings),
    }


def main() -> None:
    cols = [
        ("Page", 12, "<"),
        ("SK defs", 8, ">"),
        ("PK defs", 8, ">"),
        ("Idx rels", 9, ">"),
        ("Subsections", 12, ">"),
        ("Keywords", 9, ">"),
        ("Topics", 7, ">"),
        ("Nodes", 6, ">"),
        ("Edges", 6, ">"),
        ("Warnings", 9, ">"),
    ]
    header = "  ".join(f"{name:{align}{width}}" for name, width, align in cols)
    print(header)
    print("-" * len(header))
    for page in PAGES:
        path = GOLDEN_DIR / f"{page}.json"
        if not path.exists():
            print(f"{page:<12}  (golden not found)")
            continue
        s = stats(path)
        row = [
            f"{page:<12}",
            f"{s['sk_defs']:>8}",
            f"{s['pk_defs']:>8}",
            f"{s['index_rels']:>9}",
            f"{s['total_subs']:>12}",
            f"{s['keywords']:>9}",
            f"{s['topics']:>7}",
            f"{s['nodes']:>6}",
            f"{s['edges']:>6}",
            f"{s['warnings']:>9}",
        ]
        print("  ".join(row))


if __name__ == "__main__":
    main()
