from __future__ import annotations

import logging

logger = logging.getLogger("jain_kb.matching")


def pick_refs_to_show(block_references: list[dict]) -> list[dict]:
    """
    Python port of TS pickRefsToShow (DefinitionModal.tsx).

    Prefers non-inline references that have resolved_fields.
    Falls back to the first qualifying inline reference only when no
    non-inline references exist at all (even unresolved ones).
    """
    non_inline = [r for r in block_references if not r.get("inline_reference", False)]
    if non_inline:
        return [r for r in non_inline if r.get("resolved_fields", [])]
    # Fallback: first inline reference with resolved fields
    return [
        r
        for r in block_references
        if r.get("inline_reference", False) and r.get("resolved_fields", [])
    ][:1]


def pick_hidden_refs(block_references: list[dict]) -> list[dict]:
    """
    Python port of TS pickHiddenRefs (DefinitionModal.tsx).

    Returns references with resolved_fields that are NOT shown by pick_refs_to_show.
    Uses identity (id) comparison — same semantics as the JS Set(pickRefsToShow(block)).
    """
    shown_ids = {id(r) for r in pick_refs_to_show(block_references)}
    return [
        r
        for r in block_references
        if r.get("resolved_fields", []) and id(r) not in shown_ids
    ]
