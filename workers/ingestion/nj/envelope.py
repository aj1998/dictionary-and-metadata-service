"""Build ingestion-ready would_write envelope for NJ parser output."""

from __future__ import annotations

from itertools import groupby
from typing import Any

from .config import NJConfig, TeekaConfig
from .models import GathaExtract, KalashExtract, ShastraParseResult

# ---------------------------------------------------------------------------
# Idempotency contracts — same shape as JK envelope contracts
# ---------------------------------------------------------------------------

_NJ_CONTRACTS: dict[str, dict] = {
    "mongo:gatha_hindi_chhand": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["chhand_index", "chhand_type", "translator", "text"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:gatha_hindi_chhand"],
    },
    "mongo:gatha_prakrit": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["text", "is_kalash", "raw_html_fragment"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:gatha_prakrit"],
    },
    "mongo:gatha_sanskrit": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["text"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:gatha_sanskrit"],
    },
    "mongo:gatha_teeka_bhaavarth_hindi": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["text"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:gatha_teeka_bhaavarth_hindi"],
    },
    "mongo:gatha_teeka_sanskrit": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["text"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:gatha_teeka_sanskrit"],
    },
    "mongo:kalash_hindi": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["text", "chhand_type"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:kalash_hindi"],
    },
    "mongo:kalash_sanskrit": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["text", "chhand_type"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:kalash_sanskrit"],
    },
    "mongo:kalash_word_meanings": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["entries"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:kalash_word_meanings"],
    },
    "mongo:teeka_gatha_mapping": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["anvayartha", "tagged_terms", "full_anyavaarth", "is_related"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:teeka_gatha_mapping"],
    },
    "neo4j:Gatha": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["gatha_number", "shastra_natural_key", "heading_hi"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Gatha"],
    },
    "neo4j:GathaTeeka": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["teeka_natural_key", "gatha_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:GathaTeeka"],
    },
    "neo4j:GathaTeekaBhaavarth": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["publication_natural_key", "gatha_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:GathaTeekaBhaavarth"],
    },
    "neo4j:Kalash": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["teeka_natural_key", "kalash_number"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Kalash"],
    },
    "neo4j:KalashBhaavarth": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["publication_natural_key", "kalash_number"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:KalashBhaavarth"],
    },
    "neo4j:Publication": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["teeka_natural_key", "publisher_id"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Publication"],
    },
    "neo4j:Shastra": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["title"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Shastra"],
    },
    "neo4j:Teeka": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["teekakar_natural_key", "shastra_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Teeka"],
    },
    "neo4j:Topic": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["name", "shastra_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Topic"],
    },
    "postgres:authors": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["display_name", "kind"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:authors"],
    },
    "postgres:gathas": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["shastra_natural_key", "gatha_number", "adhikaar_number", "adhikaar", "heading"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:gathas", "neo4j:Gatha"],
    },
    "postgres:kalashas": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["teeka_natural_key", "kalash_number", "gatha_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:kalashas"],
    },
    "postgres:publications": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["teeka_natural_key", "publisher_id"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:publications"],
    },
    "postgres:shastras": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["title", "author_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:shastras", "neo4j:Shastra"],
    },
    "postgres:teeka_chapters": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["chapter_number", "name", "start_gatha_natural_key", "end_gatha_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:teeka_chapters"],
    },
    "postgres:teekas": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["shastra_natural_key", "teekakar_natural_key"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:teekas"],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lang_text(lang: str, text: str) -> list[dict[str, str]]:
    return [{"lang": lang, "script": "Deva", "text": text}]


def _norm_num(s: str) -> str:
    """Strip leading zeros from a numeric string: '001' → '1', '011' → '11'."""
    try:
        return str(int(s))
    except ValueError:
        return s


def _primary_secondary(cfg: NJConfig) -> tuple[TeekaConfig, TeekaConfig | None]:
    primary = cfg.shastra.primary_teeka
    if primary is None:
        raise ValueError("NJ config missing primary teeka")
    secondary = cfg.shastra.secondary_teekas[0] if cfg.shastra.secondary_teekas else None
    return primary, secondary


def _gatha_nk(shastra_nk: str, gatha_number: str) -> str:
    return f"{shastra_nk}:{_GATHA}:{_norm_num(gatha_number)}"


def _related(g: GathaExtract) -> list[str]:
    return list(g.related_gatha_numbers) if g.is_combined_page else []


def _neo4j_node(label: str, key: str, props: dict[str, Any]) -> dict[str, Any]:
    return {"label": label, "key": key, "props": props}


def _neo4j_edge(
    edge_type: str,
    from_label: str,
    from_key: str,
    to_label: str,
    to_key: str,
    props: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": edge_type,
        "from": {"label": from_label, "key": from_key},
        "to": {"label": to_label, "key": to_key},
        "props": props or {},
    }


# ---------------------------------------------------------------------------
# Mongo fragment builders
# ---------------------------------------------------------------------------

_GATHA = "गाथा"
_KALASH = "कलश"
_TEEKA = "टीका"
_BHAAVARTH = "भावार्थ"
_ADHYAAY = "अध्याय"


def _build_mongo_for_gatha(
    g: GathaExtract,
    primary: TeekaConfig,
    secondary: TeekaConfig | None,
) -> dict[str, list[dict[str, Any]]]:
    shastra_nk = g.shastra_natural_key
    gatha_nk = _gatha_nk(shastra_nk, g.gatha_number)
    out: dict[str, list[dict[str, Any]]] = {
        "gatha_prakrit": [],
        "gatha_sanskrit": [],
        "gatha_hindi_chhand": [],
        "teeka_gatha_mapping": [],
        "gatha_teeka_sanskrit": [],
        "gatha_teeka_bhaavarth_hindi": [],
        "kalash_sanskrit": [],
        "kalash_hindi": [],
        "kalash_word_meanings": [],
    }

    norm_gatha_num = _norm_num(g.gatha_number)
    if g.prakrit_text:
        out["gatha_prakrit"].append({
            "collection": "gatha_prakrit",
            "natural_key": f"{gatha_nk}:prakrit",
            "shastra_natural_key": shastra_nk,
            "gatha_natural_key": gatha_nk,
            "gatha_number": norm_gatha_num,
            "text": _lang_text("pra", g.prakrit_text),
            "is_kalash": False,
            "raw_html_fragment": None,
        })
    if g.sanskrit_text:
        out["gatha_sanskrit"].append({
            "collection": "gatha_sanskrit",
            "natural_key": f"{gatha_nk}:sanskrit",
            "shastra_natural_key": shastra_nk,
            "gatha_natural_key": gatha_nk,
            "gatha_number": norm_gatha_num,
            "text": _lang_text("san", g.sanskrit_text),
        })

    for ch in g.hindi_chhands:
        out["gatha_hindi_chhand"].append({
            "collection": "gatha_hindi_chhand",
            "natural_key": f"{gatha_nk}:chhand:{ch.chhand_index}",
            "gatha_natural_key": gatha_nk,
            "chhand_index": ch.chhand_index,
            "chhand_type": ch.chhand_type,
            "translator": _lang_text("hin", "nikkyjain"),
            "text": _lang_text("hin", ch.text_hi),
        })

    full_anyavaarth = g.anyavartha.full_anyavaarth if g.anyavartha else ""
    tagged_terms = []
    if g.anyavartha:
        tagged_terms = [{"source_word": e.source_word, "meaning": e.meaning} for e in g.anyavartha.tagged_terms]

    # Only populate teeka_gatha_mapping for the primary teeka
    out["teeka_gatha_mapping"].append({
        "collection": "teeka_gatha_mapping",
        "natural_key": f"{primary.natural_key}:{norm_gatha_num}",
        "teeka_natural_key": primary.natural_key,
        "gatha_natural_key": gatha_nk,
        "anvayartha": _lang_text("hin", full_anyavaarth) if full_anyavaarth else [],
        "tagged_terms": tagged_terms,
        "full_anyavaarth": full_anyavaarth,
        "is_related": _related(g),
    })

    if g.primary_teeka and g.primary_teeka.gatha_teeka_san:
        out["gatha_teeka_sanskrit"].append({
            "collection": "gatha_teeka_sanskrit",
            "natural_key": f"{primary.natural_key}:{norm_gatha_num}:{_TEEKA}:san",
            "gatha_teeka_natural_key": f"{primary.natural_key}:{norm_gatha_num}",
            "teeka_natural_key": primary.natural_key,
            "gatha_number": norm_gatha_num,
            "text": _lang_text("san", g.primary_teeka.gatha_teeka_san),
        })
    if secondary and g.secondary_teeka and g.secondary_teeka.gatha_teeka_san:
        out["gatha_teeka_sanskrit"].append({
            "collection": "gatha_teeka_sanskrit",
            "natural_key": f"{secondary.natural_key}:{norm_gatha_num}:{_TEEKA}:san",
            "gatha_teeka_natural_key": f"{secondary.natural_key}:{norm_gatha_num}",
            "teeka_natural_key": secondary.natural_key,
            "gatha_number": norm_gatha_num,
            "text": _lang_text("san", g.secondary_teeka.gatha_teeka_san),
        })

    if g.primary_teeka and g.primary_teeka.gatha_teeka_bhaavarth_md:
        out["gatha_teeka_bhaavarth_hindi"].append({
            "collection": "gatha_teeka_bhaavarth_hindi",
            "natural_key": f"{primary.publication_natural_key}:{norm_gatha_num}:{_BHAAVARTH}:hi",
            "gatha_teeka_bhaavarth_natural_key": f"{primary.publication_natural_key}:{norm_gatha_num}:{_BHAAVARTH}:hi",
            "publication_natural_key": primary.publication_natural_key,
            "gatha_teeka_natural_key": f"{primary.natural_key}:{norm_gatha_num}",
            "publisher_id": primary.publisher_id,
            "gatha_number": norm_gatha_num,
            "text": _lang_text("hin", g.primary_teeka.gatha_teeka_bhaavarth_md),
        })
    if secondary and g.secondary_teeka and g.secondary_teeka.gatha_teeka_bhaavarth_md:
        out["gatha_teeka_bhaavarth_hindi"].append({
            "collection": "gatha_teeka_bhaavarth_hindi",
            "natural_key": f"{secondary.publication_natural_key}:{norm_gatha_num}:{_BHAAVARTH}:hi",
            "gatha_teeka_bhaavarth_natural_key": f"{secondary.publication_natural_key}:{norm_gatha_num}:{_BHAAVARTH}:hi",
            "publication_natural_key": secondary.publication_natural_key,
            "gatha_teeka_natural_key": f"{secondary.natural_key}:{norm_gatha_num}",
            "publisher_id": secondary.publisher_id,
            "gatha_number": norm_gatha_num,
            "text": _lang_text("hin", g.secondary_teeka.gatha_teeka_bhaavarth_md),
        })

    if g.primary_teeka:
        san_map = {x.global_kalash_index: x for x in g.primary_teeka.kalash_san}
        hi_map = {x.global_kalash_index: x for x in g.primary_teeka.kalash_hindi}
        wm_map = g.primary_teeka.kalash_word_meanings
        for kidx in sorted(set(san_map) | set(hi_map)):
            kalash_nk = f"{primary.natural_key}:{_KALASH}:{kidx}"
            ksan = san_map.get(kidx)
            khi = hi_map.get(kidx)
            if ksan:
                out["kalash_sanskrit"].append({
                    "collection": "kalash_sanskrit",
                    "natural_key": f"{kalash_nk}:san",
                    "kalash_natural_key": kalash_nk,
                    "teeka_natural_key": primary.natural_key,
                    "kalash_number": str(kidx),
                    "text": _lang_text("san", ksan.text_san),
                    "chhand_type": ksan.chhand_type,
                })
            if khi:
                out["kalash_hindi"].append({
                    "collection": "kalash_hindi",
                    "natural_key": f"{kalash_nk}:hi",
                    "kalash_natural_key": kalash_nk,
                    "teeka_natural_key": primary.natural_key,
                    "kalash_number": str(kidx),
                    "text": _lang_text("hin", khi.text_hi),
                    "chhand_type": khi.chhand_type,
                })
            wm_items = wm_map.get(kidx, [])
            if not wm_items and khi:
                wm_items = wm_map.get(khi.local_kalash_index, [])
            if not wm_items and ksan:
                wm_items = wm_map.get(ksan.local_kalash_index, [])
            if wm_items:
                out["kalash_word_meanings"].append({
                    "collection": "kalash_word_meanings",
                    "natural_key": f"{kalash_nk}:word_meanings",
                    "kalash_natural_key": kalash_nk,
                    "teeka_natural_key": primary.natural_key,
                    "kalash_number": str(kidx),
                    "entries": [
                        {"source_word": e.source_word, "meaning": e.meaning, "position": i + 1}
                        for i, e in enumerate(wm_items)
                    ],
                })

    return out


def _build_mongo_for_secondary_kalash(
    k: KalashExtract,
    secondary: TeekaConfig | None,
) -> dict[str, list[dict[str, Any]]]:
    if secondary is None:
        return {}
    norm_kalash_num = _norm_num(k.kalash_number)
    kalash_j_nk = f"{secondary.natural_key}:{_KALASH}:{norm_kalash_num}"
    out: dict[str, list[dict[str, Any]]] = {
        "gatha_prakrit": [],
        "gatha_teeka_sanskrit": [],
        "gatha_teeka_bhaavarth_hindi": [],
    }
    if k.prakrit_text:
        out["gatha_prakrit"].append({
            "collection": "gatha_prakrit",
            "natural_key": f"{kalash_j_nk}:prakrit",
            "shastra_natural_key": k.shastra_natural_key,
            "gatha_natural_key": kalash_j_nk,
            "gatha_number": norm_kalash_num,
            "text": _lang_text("pra", k.prakrit_text),
            "is_kalash": True,
            "raw_html_fragment": None,
        })
    if k.secondary_teeka and k.secondary_teeka.gatha_teeka_san:
        out["gatha_teeka_sanskrit"].append({
            "collection": "gatha_teeka_sanskrit",
            "natural_key": f"{secondary.natural_key}:{_KALASH}:{norm_kalash_num}:{_TEEKA}:san",
            "gatha_teeka_natural_key": f"{secondary.natural_key}:{_KALASH}:{norm_kalash_num}",
            "teeka_natural_key": secondary.natural_key,
            "gatha_number": norm_kalash_num,
            "text": _lang_text("san", k.secondary_teeka.gatha_teeka_san),
        })
    if k.secondary_teeka and k.secondary_teeka.gatha_teeka_bhaavarth_md:
        out["gatha_teeka_bhaavarth_hindi"].append({
            "collection": "gatha_teeka_bhaavarth_hindi",
            "natural_key": f"{secondary.publication_natural_key}:{_KALASH}:{norm_kalash_num}:{_BHAAVARTH}:hi",
            "gatha_teeka_bhaavarth_natural_key": f"{secondary.publication_natural_key}:{_KALASH}:{norm_kalash_num}:{_BHAAVARTH}:hi",
            "publication_natural_key": secondary.publication_natural_key,
            "gatha_teeka_natural_key": f"{secondary.natural_key}:{_KALASH}:{norm_kalash_num}",
            "publisher_id": secondary.publisher_id,
            "gatha_number": norm_kalash_num,
            "text": _lang_text("hin", k.secondary_teeka.gatha_teeka_bhaavarth_md),
        })
    return out


# ---------------------------------------------------------------------------
# Neo4j fragment builder
# ---------------------------------------------------------------------------

def _build_neo4j(
    result: ShastraParseResult,
    cfg: NJConfig,
) -> dict[str, list[dict[str, Any]]]:
    """Build neo4j nodes and edges.

    Node types: Shastra, Teeka, Publication, Topic, Gatha, GathaTeeka,
                GathaTeekaBhaavarth, Kalash, KalashBhaavarth.
    Edge types: HAS_TEEKA, HAS_PUBLICATION, MENTIONS_TOPIC, HAS_GATHA_TEEKA,
                HAS_KALASH, HAS_BHAAVARTH.

    Node shape: {label, key, props} — matches JK envelope format.
    Edge shape: {type, from: {label, key}, to: {label, key}, props}.
    """
    shastra_nk = result.shastra_natural_key
    primary, secondary = _primary_secondary(cfg)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Shastra node
    nodes.append(_neo4j_node("Shastra", shastra_nk, {
        "title_hi": cfg.shastra.title_hi,
        "author_natural_key": cfg.shastra.author.natural_key,
    }))

    # Teeka + Publication nodes, and Shastra→Teeka / Teeka→Publication / Shastra→Publication edges
    for t in cfg.shastra.teekas:
        nodes.append(_neo4j_node("Teeka", t.natural_key, {
            "teeka_natural_key": t.natural_key,
            "teekakar_natural_key": t.teekakar_natural_key,
            "shastra_natural_key": shastra_nk,
        }))
        nodes.append(_neo4j_node("Publication", t.publication_natural_key, {
            "publication_natural_key": t.publication_natural_key,
            "teeka_natural_key": t.natural_key,
            "publisher_id": t.publisher_id,
        }))
        edges.append(_neo4j_edge("HAS_TEEKA", "Shastra", shastra_nk, "Teeka", t.natural_key))
        edges.append(_neo4j_edge("HAS_PUBLICATION", "Teeka", t.natural_key, "Publication", t.publication_natural_key))
        edges.append(_neo4j_edge("HAS_PUBLICATION", "Shastra", shastra_nk, "Publication", t.publication_natural_key))

    # Topic nodes (deduplicated by heading text)
    seen_topics: set[str] = set()
    for g in result.gathas:
        if g.heading_hi and g.heading_hi not in seen_topics:
            seen_topics.add(g.heading_hi)
            nodes.append(_neo4j_node("Topic", g.heading_hi, {
                "display_text_hi": g.heading_hi,
                "shastra_natural_key": shastra_nk,
                "source": "nj",
            }))

    # Per-gatha nodes and edges
    for g in result.gathas:
        gatha_nk = _gatha_nk(shastra_nk, g.gatha_number)
        norm_gatha_num = _norm_num(g.gatha_number)

        nodes.append(_neo4j_node("Gatha", gatha_nk, {
            "shastra_natural_key": shastra_nk,
            "gatha_number": norm_gatha_num,
            "heading_hi": g.heading_hi,
        }))
        if g.heading_hi:
            edges.append(_neo4j_edge(
                "MENTIONS_TOPIC",
                "Gatha", gatha_nk,
                "Topic", g.heading_hi,
                {"weight": 1.0, "source": "nj"},
            ))

        if g.primary_teeka is not None:
            # GathaTeeka node (primary): {teeka_nk}:गाथा:टीका:{gatha_num}
            gt_nk = f"{primary.natural_key}:{_GATHA}:{_TEEKA}:{norm_gatha_num}"
            nodes.append(_neo4j_node("GathaTeeka", gt_nk, {
                "teeka_natural_key": primary.natural_key,
                "gatha_natural_key": gatha_nk,
            }))
            edges.append(_neo4j_edge("HAS_GATHA_TEEKA", "Teeka", primary.natural_key, "GathaTeeka", gt_nk))

            if g.primary_teeka.gatha_teeka_bhaavarth_md:
                # GathaTeekaBhaavarth node: {pub_nk}:गाथा:टीका:भावार्थ:{gatha_num}
                gtb_nk = f"{primary.publication_natural_key}:{_GATHA}:{_TEEKA}:{_BHAAVARTH}:{norm_gatha_num}"
                nodes.append(_neo4j_node("GathaTeekaBhaavarth", gtb_nk, {
                    "publication_natural_key": primary.publication_natural_key,
                    "gatha_natural_key": gatha_nk,
                }))
                edges.append(_neo4j_edge("HAS_BHAAVARTH", "Publication", primary.publication_natural_key, "GathaTeekaBhaavarth", gtb_nk))

            # Kalash + KalashBhaavarth nodes for each primary kalash on this page
            for ksan in g.primary_teeka.kalash_san:
                kidx = ksan.global_kalash_index
                kalash_nk = f"{primary.natural_key}:{_KALASH}:{kidx}"
                nodes.append(_neo4j_node("Kalash", kalash_nk, {
                    "teeka_natural_key": primary.natural_key,
                    "kalash_number": str(kidx),
                }))
                edges.append(_neo4j_edge("HAS_KALASH", "Teeka", primary.natural_key, "Kalash", kalash_nk))

                # KalashBhaavarth node: {pub_nk}:कलश:भावार्थ:{kalash_num}
                kb_nk = f"{primary.publication_natural_key}:{_KALASH}:{_BHAAVARTH}:{kidx}"
                nodes.append(_neo4j_node("KalashBhaavarth", kb_nk, {
                    "publication_natural_key": primary.publication_natural_key,
                    "kalash_number": str(kidx),
                }))
                edges.append(_neo4j_edge("HAS_BHAAVARTH", "Publication", primary.publication_natural_key, "KalashBhaavarth", kb_nk))

        if secondary and g.secondary_teeka is not None:
            # GathaTeeka node (secondary)
            gt_j_nk = f"{secondary.natural_key}:{_GATHA}:{_TEEKA}:{norm_gatha_num}"
            nodes.append(_neo4j_node("GathaTeeka", gt_j_nk, {
                "teeka_natural_key": secondary.natural_key,
                "gatha_natural_key": gatha_nk,
            }))
            edges.append(_neo4j_edge("HAS_GATHA_TEEKA", "Teeka", secondary.natural_key, "GathaTeeka", gt_j_nk))

            if g.secondary_teeka.gatha_teeka_bhaavarth_md:
                gtb_j_nk = f"{secondary.publication_natural_key}:{_GATHA}:{_TEEKA}:{_BHAAVARTH}:{norm_gatha_num}"
                nodes.append(_neo4j_node("GathaTeekaBhaavarth", gtb_j_nk, {
                    "publication_natural_key": secondary.publication_natural_key,
                    "gatha_natural_key": gatha_nk,
                }))
                edges.append(_neo4j_edge("HAS_BHAAVARTH", "Publication", secondary.publication_natural_key, "GathaTeekaBhaavarth", gtb_j_nk))

    # Secondary kalash nodes
    for k in result.secondary_kalashes:
        if secondary:
            norm_kalash_num = _norm_num(k.kalash_number)
            kalash_j_nk = f"{secondary.natural_key}:{_KALASH}:{norm_kalash_num}"
            nodes.append(_neo4j_node("Kalash", kalash_j_nk, {
                "teeka_natural_key": secondary.natural_key,
                "kalash_number": norm_kalash_num,
            }))
            edges.append(_neo4j_edge("HAS_KALASH", "Teeka", secondary.natural_key, "Kalash", kalash_j_nk))

            if k.secondary_teeka and k.secondary_teeka.gatha_teeka_bhaavarth_md:
                kb_j_nk = f"{secondary.publication_natural_key}:{_KALASH}:{_BHAAVARTH}:{norm_kalash_num}"
                nodes.append(_neo4j_node("KalashBhaavarth", kb_j_nk, {
                    "publication_natural_key": secondary.publication_natural_key,
                    "kalash_number": norm_kalash_num,
                }))
                edges.append(_neo4j_edge("HAS_BHAAVARTH", "Publication", secondary.publication_natural_key, "KalashBhaavarth", kb_j_nk))

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Teeka chapters
# ---------------------------------------------------------------------------

def _build_teeka_chapters(
    result: ShastraParseResult,
    primary: TeekaConfig,
) -> list[dict[str, Any]]:
    """Build chapter records for the primary teeka, grouped by adhikaar."""
    sorted_gathas = sorted(
        result.gathas,
        key=lambda g: (g.adhikaar_number or 0, g.gatha_number),
    )
    chapters = []
    for adhikaar_num, group_iter in groupby(sorted_gathas, key=lambda g: g.adhikaar_number):
        if adhikaar_num is None:
            continue
        group_list = list(group_iter)
        first = group_list[0]
        last = group_list[-1]
        chapters.append({
            "table": "teeka_chapters",
            "natural_key": f"{primary.natural_key}:{_ADHYAAY}:{adhikaar_num}",
            "teeka_natural_key": primary.natural_key,
            "chapter_number": adhikaar_num,
            "name": _lang_text("hin", first.adhikaar_hi) if first.adhikaar_hi else [],
            "start_gatha_natural_key": _gatha_nk(first.shastra_natural_key, first.gatha_number),
            "end_gatha_natural_key": _gatha_nk(last.shastra_natural_key, last.gatha_number),
        })
    return chapters


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def build_envelope(result: ShastraParseResult, cfg: NJConfig) -> dict[str, Any]:
    """Convert ShastraParseResult into ingestion-ready envelope."""
    primary, secondary = _primary_secondary(cfg)

    ww: dict[str, Any] = {
        "postgres": {
            "authors": [],
            "shastras": [],
            "teekas": [],
            "publications": [],
            "gathas": [],
            "kalashas": [],
            "teeka_chapters": [],
        },
        "mongo": {
            "gatha_prakrit": [],
            "gatha_sanskrit": [],
            "gatha_hindi_chhand": [],
            "teeka_gatha_mapping": [],
            "gatha_teeka_sanskrit": [],
            "gatha_teeka_bhaavarth_hindi": [],
            "kalash_sanskrit": [],
            "kalash_hindi": [],
            "kalash_word_meanings": [],
        },
        "neo4j": {"nodes": [], "edges": []},
        "idempotency_contracts": _NJ_CONTRACTS,
    }

    ww["postgres"]["authors"].append({
        "table": "authors",
        "natural_key": cfg.shastra.author.natural_key,
        "display_name": _lang_text("hin", cfg.shastra.author.display_name_hi),
        "kind": cfg.shastra.author.kind,
    })
    for t in cfg.shastra.teekas:
        ww["postgres"]["authors"].append({
            "table": "authors",
            "natural_key": t.teekakar_natural_key,
            "display_name": _lang_text("hin", t.teekakar_display_name_hi),
            "kind": "acharya",
        })
        ww["postgres"]["teekas"].append({
            "table": "teekas",
            "natural_key": t.natural_key,
            "shastra_natural_key": cfg.shastra.natural_key,
            "teekakar_natural_key": t.teekakar_natural_key,
        })
        ww["postgres"]["publications"].append({
            "table": "publications",
            "natural_key": t.publication_natural_key,
            "teeka_natural_key": t.natural_key,
            "publisher_id": t.publisher_id,
        })
    ww["postgres"]["shastras"].append({
        "table": "shastras",
        "natural_key": cfg.shastra.natural_key,
        "title": _lang_text("hin", cfg.shastra.title_hi),
        "author_natural_key": cfg.shastra.author.natural_key,
    })

    for g in result.gathas:
        gatha_nk = _gatha_nk(g.shastra_natural_key, g.gatha_number)
        ww["postgres"]["gathas"].append({
            "table": "gathas",
            "natural_key": gatha_nk,
            "shastra_natural_key": g.shastra_natural_key,
            "gatha_number": _norm_num(g.gatha_number),
            "adhikaar_number": g.adhikaar_number,
            "adhikaar": _lang_text("hin", g.adhikaar_hi) if g.adhikaar_hi else [],
            "heading": _lang_text("hin", g.heading_hi) if g.heading_hi else [],
        })

        mg = _build_mongo_for_gatha(g, primary, secondary)
        for coll, docs in mg.items():
            ww["mongo"][coll].extend(docs)

    seen_kalash_nk: set[str] = set()
    for doc in ww["mongo"]["kalash_sanskrit"] + ww["mongo"]["kalash_hindi"] + ww["mongo"]["kalash_word_meanings"]:
        nk = doc["kalash_natural_key"]
        if nk in seen_kalash_nk:
            continue
        seen_kalash_nk.add(nk)
        gatha_ref = next(
            (
                _gatha_nk(g.shastra_natural_key, g.gatha_number)
                for g in result.gathas
                if g.primary_teeka and any(
                    k.global_kalash_index == int(nk.rsplit(":", 1)[1])
                    for k in g.primary_teeka.kalash_san
                )
            ),
            None,
        )
        ww["postgres"]["kalashas"].append({
            "table": "kalashas",
            "natural_key": nk,
            "teeka_natural_key": primary.natural_key,
            "kalash_number": nk.rsplit(":", 1)[1],
            "gatha_natural_key": gatha_ref,
        })

    for k in result.secondary_kalashes:
        if secondary:
            ww["postgres"]["kalashas"].append({
                "table": "kalashas",
                "natural_key": f"{secondary.natural_key}:{_KALASH}:{_norm_num(k.kalash_number)}",
                "teeka_natural_key": secondary.natural_key,
                "kalash_number": _norm_num(k.kalash_number),
                "gatha_natural_key": (
                    _gatha_nk(result.shastra_natural_key, k.preceding_primary_gatha_number)
                    if k.preceding_primary_gatha_number
                    else None
                ),
            })
            ms = _build_mongo_for_secondary_kalash(k, secondary)
            for coll, docs in ms.items():
                ww["mongo"][coll].extend(docs)

    # Neo4j nodes and edges
    neo4j = _build_neo4j(result, cfg)
    ww["neo4j"]["nodes"] = neo4j["nodes"]
    ww["neo4j"]["edges"] = neo4j["edges"]

    # Teeka chapters for primary teeka only
    ww["postgres"]["teeka_chapters"] = _build_teeka_chapters(result, primary)

    return {
        "shastra_parse_result": result.model_dump(mode="json"),
        "would_write": ww,
    }
