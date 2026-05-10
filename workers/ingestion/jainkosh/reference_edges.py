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
) -> dict:
    props: dict = {"weight": 1.0, "source": "jainkosh"}
    props.update(pankti_props)
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
) -> list[dict]:
    sn = ref.shastra_name
    tn = ref.teeka_name

    if shastra_type == "shastra":
        key = f"{sn}:गाथा:{g}"
        return [_make_edge(edge_type, "Gatha", key, target, pankti_props)]

    if shastra_type == "teeka":
        if block_kind in {"sanskrit_gatha", "prakrit_gatha", "hindi_gatha"}:
            key = f"{sn}:गाथा:{g}"
            return [_make_edge(edge_type, "Gatha", key, target, pankti_props)]
        if block_kind in {"sanskrit_text", "prakrit_text", "hindi_text"}:
            if not tn:
                logger.warning("missing_teeka_for_edge: teeka_name empty for %s", sn)
                return []
            key = f"{sn}:{tn}:गाथा:टीका:{g}"
            return [_make_edge(edge_type, "GathaTeeka", key, target, pankti_props)]
        return []

    if shastra_type == "publication":
        if block_kind in {"sanskrit_gatha", "prakrit_gatha", "hindi_gatha"}:
            key = f"{sn}:गाथा:{g}"
            return [_make_edge(edge_type, "Gatha", key, target, pankti_props)]
        if block_kind in {"sanskrit_text", "prakrit_text"}:
            if not tn:
                logger.warning("missing_teeka_for_edge: teeka_name empty for %s", sn)
                return []
            key = f"{sn}:{tn}:गाथा:टीका:{g}"
            return [_make_edge(edge_type, "GathaTeeka", key, target, pankti_props)]
        if block_kind == "hindi_text":
            if not tn:
                logger.warning("missing_teeka_for_edge: teeka_name empty for %s", sn)
                return []
            edges = []
            key1 = f"{sn}:{tn}:गाथा:टीका:{g}"
            edges.append(_make_edge(edge_type, "GathaTeeka", key1, target, pankti_props))
            key2 = f"{sn}:{tn}:{publisher_id}:गाथा:टीका:भावार्थ:{g}"
            edges.append(_make_edge(edge_type, "GathaTeekaBhaavarth", key2, target, pankti_props))
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
) -> list[dict]:
    sn = ref.shastra_name
    tn = ref.teeka_name

    if shastra_type == "shastra":
        return []

    if shastra_type == "teeka":
        if block_kind in {"sanskrit_gatha", "prakrit_gatha", "hindi_gatha"}:
            if not tn:
                logger.warning("missing_teeka_for_edge: teeka_name empty for %s", sn)
                return []
            key = f"{sn}:{tn}:कलश:{k}"
            return [_make_edge(edge_type, "Kalash", key, target, pankti_props)]
        return []

    if shastra_type == "publication":
        if block_kind in {"sanskrit_gatha", "prakrit_gatha", "hindi_gatha"}:
            if not tn:
                logger.warning("missing_teeka_for_edge: teeka_name empty for %s", sn)
                return []
            key = f"{sn}:{tn}:कलश:{k}"
            return [_make_edge(edge_type, "Kalash", key, target, pankti_props)]
        if block_kind == "hindi_text":
            if not tn:
                logger.warning("missing_teeka_for_edge: teeka_name empty for %s", sn)
                return []
            key = f"{sn}:{tn}:{publisher_id}:कलश:भावार्थ:{k}"
            return [_make_edge(edge_type, "KalashBhaavarth", key, target, pankti_props)]
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
) -> list[dict]:
    if shastra_type != "publication":
        return []
    sn = ref.shastra_name
    tn = ref.teeka_name
    if not tn:
        logger.warning("missing_teeka_for_edge: teeka_name empty for %s", sn)
        return []
    key = f"{sn}:{tn}:{publisher_id}:पृष्ठ:{p}"
    return [_make_edge(edge_type, "Page", key, target, pankti_props)]


def build_reference_edges(
    block,
    *,
    target: dict,
    edge_type: str,
    config: "JainkoshConfig",
) -> list[dict]:
    """Return edge dicts for this block. May return [] if no eligible ref or
    the ref doesn't carry the required keyword fields."""
    ref = _pick_reference(block.references)
    if ref is None or ref.shastra_name is None:
        return []

    if config.shastra_registry is None:
        return []

    shastra_type = config.shastra_registry.get_type(ref.shastra_name)
    if shastra_type is None:
        return []

    cfg = config
    ek = cfg.reference.entity_keywords
    rf = ref.resolved_fields
    block_kind = block.kind

    publisher_id = _resolve_publisher_id(ref, config)
    pankti_props = _pankti_props(rf, cfg)

    edges: list[dict] = []

    g = _first_value(rf, ek.gatha)
    if g is not None:
        edges.extend(_emit_gatha(
            ref, shastra_type, block_kind, g, publisher_id,
            edge_type, target, pankti_props, config,
        ))

    k = _first_value(rf, ek.kalash)
    if k is not None:
        edges.extend(_emit_kalash(
            ref, shastra_type, block_kind, k, publisher_id,
            edge_type, target, pankti_props,
        ))

    p = _first_value(rf, ek.page)
    if p is not None:
        edges.extend(_emit_page(
            ref, shastra_type, block_kind, p, publisher_id,
            edge_type, target, pankti_props,
        ))

    return edges
