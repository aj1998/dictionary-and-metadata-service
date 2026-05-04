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

    sk_defs = sum(
        len(s.get("definitions", []))
        for s in sections
        if s.get("section_kind") == "siddhantkosh"
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
        "index_rels": index_rels,
        "total_subs": total_subs,
        "warnings": len(warnings),
    }


def main() -> None:
    header = f"{'Page':<12} {'SiddhantKosh defs':>18} {'Index relations':>16} {'Total subsections':>18} {'Warnings':>9}"
    sep = "-" * len(header)
    print(header)
    print(sep)
    for page in PAGES:
        path = GOLDEN_DIR / f"{page}.json"
        if not path.exists():
            print(f"{page:<12} (golden not found)")
            continue
        s = stats(path)
        print(
            f"{page:<12} {s['sk_defs']:>18} {s['index_rels']:>16} {s['total_subs']:>18} {s['warnings']:>9}"
        )


if __name__ == "__main__":
    main()
