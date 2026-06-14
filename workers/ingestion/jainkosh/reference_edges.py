"""Emit Neo4j edges from resolved Reference objects (§4 of reference_edge_creation_spec)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import JainkoshConfig
    from .models import Block, Reference, ResolvedField

logger = logging.getLogger(__name__)


def _pick_reference(refs: list) -> Optional[object]:
    if not refs:
        return None
    for r in refs:
        if not r.inline_reference:
            return r
    return refs[0]


def _first_value(rfields: list, names: list[str]) -> Optional[int]:
    """Return the int value of the first matching field name."""
    by = {f.field: f.value for f in rfields}
    for n in names:
        if n in by and isinstance(by[n], int):
            return by[n]
    return None


def _pankti_props(rfields: list, cfg) -> dict:
    v = _first_value(rfields, cfg.reference.entity_keywords.pankti)
    return {"pankti": v} if v is not None else {}


def _resolve_publisher_id(ref, config: "JainkoshConfig") -> str:
    if config.shastra_registry is None or config.publisher_registry is None:
        return "publisher_to_be_added"
    # Try exact name first (handles multi-word names like "जैनेंद्र व्याकरण" whose
    # spaces _by_primary normalises away, causing the lookup to miss the entry).
    entry = config.shastra_registry._by_exact_name.get(ref.shastra_name)
    if entry is None:
        entry = config.shastra_registry._by_primary.get(ref.shastra_name)
    if entry is None:
        return "publisher_to_be_added"
    publisher_name = entry.publisher
    return config.publisher_registry.get_id(publisher_name)


def _make_edge(
    edge_type: str,
    src_label: str,
    src_key: str,
    target: dict,
    pankti_props: dict,
    extra_props: Optional[dict] = None,
) -> dict:
    props: dict = {"weight": 1.0, "source": "jainkosh"}
    props.update(pankti_props)
    if extra_props:
        props.update(extra_props)
    return {
        "type": edge_type,
        "from": {"label": src_label, "key": src_key},
        "to": target,
        "props": props,
    }


def _emit_gatha(
    ref,
    shastra_type: str,
    block_kind: str,
    g: int,
    publisher_id: str,
    edge_type: str,
    target: dict,
    pankti_props: dict,
    config: "JainkoshConfig",
    extra_props: Optional[dict] = None,
    is_bhaavarth: bool = False,
) -> list[dict]:
    sn = ref.shastra_name
    tn = ref.teeka_name

    if shastra_type == "shastra":
        key = f"{sn}:गाथा:{g}"
        return [_make_edge(edge_type, "Gatha", key, target, pankti_props, extra_props)]

    if shastra_type == "teeka":
        # `prakrit_text` is original Prakrit source content (same as `prakrit_gatha`,
        # see v1.11.19 — extended here to `teeka` type for parity with `publication`).
        if block_kind in {"sanskrit_gatha", "prakrit_gatha", "hindi_gatha", "prakrit_text"}:
            key = f"{sn}:गाथा:{g}"
            return [_make_edge(edge_type, "Gatha", key, target, pankti_props, extra_props)]
        if block_kind in {"sanskrit_text", "hindi_text"}:
            key = f"{sn}:{tn or 'टीका'}:गाथा:टीका:{g}"
            return [_make_edge(edge_type, "GathaTeeka", key, target, pankti_props, extra_props)]
        return []

    if shastra_type == "publication":
        if block_kind in {"sanskrit_gatha", "prakrit_gatha", "hindi_gatha", "prakrit_text"}:
            key = f"{sn}:गाथा:{g}"
            return [_make_edge(edge_type, "Gatha", key, target, pankti_props, extra_props)]
        if block_kind == "sanskrit_text":
            key = f"{sn}:{tn or 'टीका'}:गाथा:टीका:{g}"
            return [_make_edge(edge_type, "GathaTeeka", key, target, pankti_props, extra_props)]
        if block_kind == "hindi_text":
            if not tn:
                if is_bhaavarth:
                    key = f"{sn}:टीका:{publisher_id}:गाथा:टीका:भावार्थ:{g}"
                    return [_make_edge(edge_type, "GathaTeekaBhaavarth", key, target, pankti_props, extra_props)]
                key = f"{sn}:गाथा:{g}"
                return [_make_edge(edge_type, "Gatha", key, target, pankti_props, extra_props)]
            edges = []
            key1 = f"{sn}:{tn}:गाथा:टीका:{g}"
            edges.append(_make_edge(edge_type, "GathaTeeka", key1, target, pankti_props, extra_props))
            key2 = f"{sn}:{tn}:{publisher_id}:गाथा:टीका:भावार्थ:{g}"
            edges.append(_make_edge(edge_type, "GathaTeekaBhaavarth", key2, target, pankti_props, extra_props))
            return edges
        return []

    return []


def _emit_kalash(
    ref,
    shastra_type: str,
    block_kind: str,
    k: int,
    publisher_id: str,
    edge_type: str,
    target: dict,
    pankti_props: dict,
    extra_props: Optional[dict] = None,
) -> list[dict]:
    sn = ref.shastra_name
    tn = ref.teeka_name or "टीका"

    if shastra_type == "shastra":
        return []

    if shastra_type == "teeka":
        if block_kind in {
            "sanskrit_gatha", "prakrit_gatha", "hindi_gatha",
            "sanskrit_text", "prakrit_text",
        }:
            key = f"{sn}:{tn}:कलश:{k}"
            return [_make_edge(edge_type, "Kalash", key, target, pankti_props, extra_props)]
        return []

    if shastra_type == "publication":
        if block_kind in {
            "sanskrit_gatha", "prakrit_gatha", "hindi_gatha",
            "sanskrit_text", "prakrit_text",
        }:
            key = f"{sn}:{tn}:कलश:{k}"
            return [_make_edge(edge_type, "Kalash", key, target, pankti_props, extra_props)]
        if block_kind == "hindi_text":
            key = f"{sn}:{tn}:{publisher_id}:कलश:भावार्थ:{k}"
            return [_make_edge(edge_type, "KalashBhaavarth", key, target, pankti_props, extra_props)]
        return []

    return []


def _emit_page(
    ref,
    shastra_type: str,
    block_kind: str,
    p: int,
    publisher_id: str,
    edge_type: str,
    target: dict,
    pankti_props: dict,
    extra_props: Optional[dict] = None,
) -> list[dict]:
    if shastra_type != "publication":
        return []
    sn = ref.shastra_name
    tn = ref.teeka_name or "टीका"
    key = f"{sn}:{tn}:{publisher_id}:पृष्ठ:{p}"
    return [_make_edge(edge_type, "Page", key, target, pankti_props, extra_props)]


def _emit_gatha_inline(
    ref,
    shastra_type: str,
    g: int,
    publisher_id: str,
    edge_type: str,
    target: dict,
    pankti_props: dict,
    config: "JainkoshConfig",
    extra_props: Optional[dict] = None,
) -> list[dict]:
    """Gatha edges for non-main refs — no block-kind check.

    shastra → Gatha; teeka → GathaTeeka only; publication → GathaTeekaBhaavarth only.
    """
    sn = ref.shastra_name
    tn = ref.teeka_name

    if shastra_type == "shastra":
        key = f"{sn}:गाथा:{g}"
        return [_make_edge(edge_type, "Gatha", key, target, pankti_props, extra_props)]

    if shastra_type == "teeka":
        key = f"{sn}:{tn or 'टीका'}:गाथा:टीका:{g}"
        return [_make_edge(edge_type, "GathaTeeka", key, target, pankti_props, extra_props)]

    if shastra_type == "publication":
        if not tn:
            key = f"{sn}:गाथा:{g}"
            return [_make_edge(edge_type, "Gatha", key, target, pankti_props, extra_props)]
        key = f"{sn}:{tn}:{publisher_id}:गाथा:टीका:भावार्थ:{g}"
        return [_make_edge(edge_type, "GathaTeekaBhaavarth", key, target, pankti_props, extra_props)]

    return []


def _emit_kalash_inline(
    ref,
    shastra_type: str,
    k: int,
    publisher_id: str,
    edge_type: str,
    target: dict,
    pankti_props: dict,
    extra_props: Optional[dict] = None,
) -> list[dict]:
    """Kalash edges for non-main refs — no block-kind check.

    shastra → nothing; teeka → Kalash; publication → KalashBhaavarth only.
    """
    sn = ref.shastra_name
    tn = ref.teeka_name or "टीका"

    if shastra_type == "shastra":
        return []

    if shastra_type == "teeka":
        key = f"{sn}:{tn}:कलश:{k}"
        return [_make_edge(edge_type, "Kalash", key, target, pankti_props, extra_props)]

    if shastra_type == "publication":
        key = f"{sn}:{tn}:{publisher_id}:कलश:भावार्थ:{k}"
        return [_make_edge(edge_type, "KalashBhaavarth", key, target, pankti_props, extra_props)]

    return []


def _emit_inline_ref_edges(
    ref,
    block_kind: str,
    edge_type: str,
    target: dict,
    config: "JainkoshConfig",
    extra_props: Optional[dict] = None,
) -> list[dict]:
    """Emit edges for a remaining non-inline reference using simplified rules."""
    if ref.shastra_name is None:
        return []
    if config.shastra_registry is None:
        return []

    shastra_type = config.shastra_registry.get_type(ref.shastra_name)
    if shastra_type is None:
        return []

    ek = config.reference.entity_keywords
    rf = ref.resolved_fields
    publisher_id = _resolve_publisher_id(ref, config)
    pankti_props = _pankti_props(rf, config)

    edges: list[dict] = []

    g = _first_value(rf, ek.gatha)
    if g is not None:
        edges.extend(_emit_gatha_inline(
            ref, shastra_type, g, publisher_id, edge_type, target, pankti_props, config, extra_props,
        ))

    k = _first_value(rf, ek.kalash)
    if k is not None:
        edges.extend(_emit_kalash_inline(
            ref, shastra_type, k, publisher_id, edge_type, target, pankti_props, extra_props,
        ))

    p = _first_value(rf, ek.page)
    if p is not None:
        edges.extend(_emit_page(
            ref, shastra_type, block_kind, p, publisher_id, edge_type, target, pankti_props, extra_props,
        ))

    return edges


def _emit_inline_only_edges(
    ref,
    edge_type: str,
    target: dict,
    config: "JainkoshConfig",
    extra_props: Optional[dict] = None,
) -> list[dict]:
    """Emit simplified Gatha/Kalash/Page edges for inline (parenthetical) references.

    Inline refs emit a plain Gatha node for any shastra type when gatha-matcher
    fields (गाथा/श्लोक/सूत्र/दोहक/वार्तिक) are present — no GathaTeeka or
    GathaTeekaBhaavarth.  Kalash and Page follow the same shastra-type guards as
    the non-inline paths.
    """
    if ref.shastra_name is None:
        return []
    if config.shastra_registry is None:
        return []

    shastra_type = config.shastra_registry.get_type(ref.shastra_name)
    if shastra_type is None:
        return []

    ek = config.reference.entity_keywords
    rf = ref.resolved_fields
    publisher_id = _resolve_publisher_id(ref, config)
    pankti_props = _pankti_props(rf, config)
    sn = ref.shastra_name
    tn = ref.teeka_name or "टीका"

    edges: list[dict] = []

    g = _first_value(rf, ek.gatha)
    if g is not None:
        key = f"{sn}:गाथा:{g}"
        edges.append(_make_edge(edge_type, "Gatha", key, target, pankti_props, extra_props))

    k = _first_value(rf, ek.kalash)
    if k is not None and shastra_type in ("teeka", "publication"):
        key = f"{sn}:{tn}:कलश:{k}"
        edges.append(_make_edge(edge_type, "Kalash", key, target, pankti_props, extra_props))

    p = _first_value(rf, ek.page)
    if p is not None and shastra_type == "publication":
        key = f"{sn}:{tn}:{publisher_id}:पृष्ठ:{p}"
        edges.append(_make_edge(edge_type, "Page", key, target, pankti_props, extra_props))

    return edges


def build_cell_reference_edges(
    refs: "list[Reference]",
    *,
    target: dict,
    edge_type: str,
    config: "JainkoshConfig",
    mention_path: str = "",
    source_natural_key: str = "",
) -> list[dict]:
    """Return edge dicts for a list of cell-level references from a table cell.

    Table cells have no block_kind context (verse/prose/etc.), so all refs
    use the simplified inline path — emitting only Gatha, Kalash, and Page
    nodes.  This mirrors how inline (parenthetical) refs are handled elsewhere.
    """
    if not refs:
        return []
    if config.shastra_registry is None:
        return []

    extra_props: dict = {}
    if mention_path:
        extra_props["mention_path"] = mention_path
    if source_natural_key:
        extra_props["source_natural_key"] = source_natural_key

    edges: list[dict] = []
    for ref in refs:
        edges.extend(_emit_inline_only_edges(ref, edge_type, target, config, extra_props))
    return edges


def build_reference_edges(
    block,
    *,
    target: dict,
    edge_type: str,
    config: "JainkoshConfig",
    block_index: int = 0,
    mention_path: str = "",
    source_natural_key: str = "",
    section_index: Optional[int] = None,
    definition_index: Optional[int] = None,
) -> list[dict]:
    """Return edge dicts for this block.

    Non-inline refs: the first (main) ref uses full block-kind-aware emission;
    remaining non-inline refs use the simplified inline rules.

    Inline (parenthetical) refs: always use the simplified Gatha/Kalash/Page
    path regardless of whether a non-inline ref is present.
    """
    refs = block.references
    if not refs:
        return []

    if config.shastra_registry is None:
        return []

    block_kind = block.kind
    extra_props: dict = {"block_index": block_index}
    if mention_path:
        extra_props["mention_path"] = mention_path
    if source_natural_key:
        extra_props["source_natural_key"] = source_natural_key
    if section_index is not None:
        extra_props["section_index"] = section_index
    if definition_index is not None:
        extra_props["definition_index"] = definition_index

    non_inline_refs = [r for r in refs if not r.inline_reference]
    inline_refs = [r for r in refs if r.inline_reference]

    edges: list[dict] = []

    # --- Non-inline refs: first is "main" (full block-kind-aware logic) ---
    if non_inline_refs:
        main_ref = non_inline_refs[0]
        if main_ref.shastra_name is not None:
            shastra_type = config.shastra_registry.get_type(main_ref.shastra_name)
            if shastra_type is not None:
                ek = config.reference.entity_keywords
                rf = main_ref.resolved_fields
                publisher_id = _resolve_publisher_id(main_ref, config)
                pankti_props = _pankti_props(rf, config)
                is_bhaavarth = (
                    block_kind == "hindi_text"
                    and getattr(block, "hindi_translation", None) is None
                )

                g = _first_value(rf, ek.gatha)
                if g is not None:
                    edges.extend(_emit_gatha(
                        main_ref, shastra_type, block_kind, g, publisher_id,
                        edge_type, target, pankti_props, config, extra_props,
                        is_bhaavarth=is_bhaavarth,
                    ))

                k = _first_value(rf, ek.kalash)
                if k is not None:
                    edges.extend(_emit_kalash(
                        main_ref, shastra_type, block_kind, k, publisher_id,
                        edge_type, target, pankti_props, extra_props,
                    ))

                p = _first_value(rf, ek.page)
                if p is not None:
                    edges.extend(_emit_page(
                        main_ref, shastra_type, block_kind, p, publisher_id,
                        edge_type, target, pankti_props, extra_props,
                    ))

        # Remaining non-inline refs use simplified rules
        for r in non_inline_refs[1:]:
            edges.extend(_emit_inline_ref_edges(r, block_kind, edge_type, target, config, extra_props))

    # --- All inline refs: simplified Gatha/Kalash/Page only ---
    for r in inline_refs:
        edges.extend(_emit_inline_only_edges(r, edge_type, target, config, extra_props))

    return edges
