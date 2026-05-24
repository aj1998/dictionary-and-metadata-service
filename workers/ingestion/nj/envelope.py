"""Build ingestion-ready would_write envelope for NJ parser output."""

from __future__ import annotations

from typing import Any

from .config import NJConfig, TeekaConfig
from .models import GathaExtract, KalashExtract, ShastraParseResult


def _lang_text(lang: str, text: str) -> list[dict[str, str]]:
    return [{"lang": lang, "script": "Deva", "text": text}]


def _primary_secondary(cfg: NJConfig) -> tuple[TeekaConfig, TeekaConfig | None]:
    primary = cfg.shastra.primary_teeka
    if primary is None:
        raise ValueError("NJ config missing primary teeka")
    secondary = cfg.shastra.secondary_teekas[0] if cfg.shastra.secondary_teekas else None
    return primary, secondary


def _gatha_nk(shastra_nk: str, gatha_number: str) -> str:
    return f"{shastra_nk}:{gatha_number}"


def _related(g: GathaExtract) -> list[str]:
    return list(g.related_gatha_numbers) if g.is_combined_page else []


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
        "gatha_word_meanings": [],
        "teeka_gatha_mapping": [],
        "gatha_teeka_sanskrit": [],
        "gatha_teeka_bhaavarth_hindi": [],
        "kalash_sanskrit": [],
        "kalash_hindi": [],
        "kalash_word_meanings": [],
    }

    if g.prakrit_text:
        out["gatha_prakrit"].append({
            "natural_key": f"{gatha_nk}:prakrit",
            "shastra_natural_key": shastra_nk,
            "gatha_natural_key": gatha_nk,
            "gatha_number": g.gatha_number,
            "text": _lang_text("pra", g.prakrit_text),
            "is_kalash": False,
            "raw_html_fragment": None,
        })
    if g.sanskrit_text:
        out["gatha_sanskrit"].append({
            "natural_key": f"{gatha_nk}:sanskrit",
            "shastra_natural_key": shastra_nk,
            "gatha_natural_key": gatha_nk,
            "gatha_number": g.gatha_number,
            "text": _lang_text("san", g.sanskrit_text),
        })

    for ch in g.hindi_chhands:
        out["gatha_hindi_chhand"].append({
            "natural_key": f"{gatha_nk}:chhand:{ch.chhand_index:02d}",
            "gatha_natural_key": gatha_nk,
            "chhand_index": ch.chhand_index,
            "chhand_type": ch.chhand_type,
            "translator": _lang_text("hin", "nikkyjain"),
            "text": _lang_text("hin", ch.text_hi),
        })

    full_anyavaarth = g.anyavartha.full_anyavaarth if g.anyavartha else ""
    wm_entries = []
    if g.anyavartha:
        for e in g.anyavartha.tagged_terms:
            wm_entries.append({
                "source_word": _lang_text("pra", e.source_word),
                "meanings": _lang_text("hin", e.meaning),
                "position": e.position,
            })
    out["gatha_word_meanings"].append({
        "natural_key": f"{gatha_nk}:word_meanings:prakrit",
        "gatha_natural_key": gatha_nk,
        "source_language": "pra",
        "full_anyavaarth": full_anyavaarth,
        "entries": wm_entries,
    })

    tagged_terms = []
    if g.anyavartha:
        tagged_terms = [{"source_word": e.source_word, "meaning": e.meaning} for e in g.anyavartha.tagged_terms]

    out["teeka_gatha_mapping"].append({
        "natural_key": f"{primary.natural_key}:{g.gatha_number}",
        "teeka_natural_key": primary.natural_key,
        "gatha_natural_key": gatha_nk,
        "anvayartha": _lang_text("hin", full_anyavaarth) if full_anyavaarth else [],
        "tagged_terms": tagged_terms,
        "full_anyavaarth": full_anyavaarth,
        "is_related": _related(g),
    })
    if secondary:
        out["teeka_gatha_mapping"].append({
            "natural_key": f"{secondary.natural_key}:{g.gatha_number}",
            "teeka_natural_key": secondary.natural_key,
            "gatha_natural_key": gatha_nk,
            "anvayartha": _lang_text("hin", full_anyavaarth) if full_anyavaarth else [],
            "tagged_terms": tagged_terms,
            "full_anyavaarth": full_anyavaarth,
            "is_related": _related(g),
        })

    if g.primary_teeka and g.primary_teeka.gatha_teeka_san:
        out["gatha_teeka_sanskrit"].append({
            "natural_key": f"{primary.natural_key}:{g.gatha_number}:teeka:san",
            "gatha_teeka_natural_key": f"{primary.natural_key}:{g.gatha_number}",
            "teeka_natural_key": primary.natural_key,
            "gatha_number": g.gatha_number,
            "text": _lang_text("san", g.primary_teeka.gatha_teeka_san),
        })
    if secondary and g.secondary_teeka and g.secondary_teeka.gatha_teeka_san:
        out["gatha_teeka_sanskrit"].append({
            "natural_key": f"{secondary.natural_key}:{g.gatha_number}:teeka:san",
            "gatha_teeka_natural_key": f"{secondary.natural_key}:{g.gatha_number}",
            "teeka_natural_key": secondary.natural_key,
            "gatha_number": g.gatha_number,
            "text": _lang_text("san", g.secondary_teeka.gatha_teeka_san),
        })

    if g.primary_teeka and g.primary_teeka.gatha_teeka_bhaavarth_md:
        out["gatha_teeka_bhaavarth_hindi"].append({
            "natural_key": f"{primary.publication_natural_key}:{g.gatha_number}:bhaavarth:hi",
            "gatha_teeka_bhaavarth_natural_key": f"{primary.publication_natural_key}:{g.gatha_number}:bhaavarth:hi",
            "publication_natural_key": primary.publication_natural_key,
            "gatha_teeka_natural_key": f"{primary.natural_key}:{g.gatha_number}",
            "publisher_id": primary.publisher_id,
            "gatha_number": g.gatha_number,
            "text": _lang_text("hin", g.primary_teeka.gatha_teeka_bhaavarth_md),
        })
    if secondary and g.secondary_teeka and g.secondary_teeka.gatha_teeka_bhaavarth_md:
        out["gatha_teeka_bhaavarth_hindi"].append({
            "natural_key": f"{secondary.publication_natural_key}:{g.gatha_number}:bhaavarth:hi",
            "gatha_teeka_bhaavarth_natural_key": f"{secondary.publication_natural_key}:{g.gatha_number}:bhaavarth:hi",
            "publication_natural_key": secondary.publication_natural_key,
            "gatha_teeka_natural_key": f"{secondary.natural_key}:{g.gatha_number}",
            "publisher_id": secondary.publisher_id,
            "gatha_number": g.gatha_number,
            "text": _lang_text("hin", g.secondary_teeka.gatha_teeka_bhaavarth_md),
        })

    if g.primary_teeka:
        san_map = {x.global_kalash_index: x for x in g.primary_teeka.kalash_san}
        hi_map = {x.global_kalash_index: x for x in g.primary_teeka.kalash_hindi}
        wm_map = g.primary_teeka.kalash_word_meanings
        for kidx in sorted(set(san_map) | set(hi_map)):
            kalash_nk = f"{primary.natural_key}:kalash:{kidx:03d}"
            ksan = san_map.get(kidx)
            khi = hi_map.get(kidx)
            if ksan:
                out["kalash_sanskrit"].append({
                    "natural_key": f"{kalash_nk}:san",
                    "kalash_natural_key": kalash_nk,
                    "teeka_natural_key": primary.natural_key,
                    "kalash_number": f"{kidx:03d}",
                    "text": _lang_text("san", ksan.text_san),
                    "chhand_type": ksan.chhand_type,
                })
            if khi:
                out["kalash_hindi"].append({
                    "natural_key": f"{kalash_nk}:hi",
                    "kalash_natural_key": kalash_nk,
                    "teeka_natural_key": primary.natural_key,
                    "kalash_number": f"{kidx:03d}",
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
                    "natural_key": f"{kalash_nk}:word_meanings",
                    "kalash_natural_key": kalash_nk,
                    "teeka_natural_key": primary.natural_key,
                    "kalash_number": f"{kidx:03d}",
                    "entries": [
                        {"source_word": e.source_word, "meaning": e.meaning, "position": i + 1}
                        for i, e in enumerate(wm_items)
                    ],
                })

    return out


def _build_mongo_for_secondary_kalash(k: KalashExtract, secondary: TeekaConfig | None) -> dict[str, list[dict[str, Any]]]:
    if secondary is None:
        return {}
    kalash_j_nk = f"{secondary.natural_key}:kalash:{k.kalash_number}"
    out: dict[str, list[dict[str, Any]]] = {
        "gatha_prakrit": [],
        "gatha_word_meanings": [],
        "gatha_teeka_sanskrit": [],
        "gatha_teeka_bhaavarth_hindi": [],
    }
    if k.prakrit_text:
        out["gatha_prakrit"].append({
            "natural_key": f"{kalash_j_nk}:prakrit",
            "shastra_natural_key": k.shastra_natural_key,
            "gatha_natural_key": kalash_j_nk,
            "gatha_number": k.kalash_number,
            "text": _lang_text("pra", k.prakrit_text),
            "is_kalash": True,
            "raw_html_fragment": None,
        })
    full_anyavaarth = k.anyavartha.full_anyavaarth if k.anyavartha else ""
    out["gatha_word_meanings"].append({
        "natural_key": f"{kalash_j_nk}:word_meanings:prakrit",
        "gatha_natural_key": kalash_j_nk,
        "source_language": "pra",
        "full_anyavaarth": full_anyavaarth,
        "entries": [
            {
                "source_word": _lang_text("pra", e.source_word),
                "meanings": _lang_text("hin", e.meaning),
                "position": e.position,
            }
            for e in (k.anyavartha.tagged_terms if k.anyavartha else [])
        ],
    })
    if k.secondary_teeka and k.secondary_teeka.gatha_teeka_san:
        out["gatha_teeka_sanskrit"].append({
            "natural_key": f"{secondary.natural_key}:kalash:{k.kalash_number}:teeka:san",
            "gatha_teeka_natural_key": f"{secondary.natural_key}:kalash:{k.kalash_number}",
            "teeka_natural_key": secondary.natural_key,
            "gatha_number": k.kalash_number,
            "text": _lang_text("san", k.secondary_teeka.gatha_teeka_san),
        })
    if k.secondary_teeka and k.secondary_teeka.gatha_teeka_bhaavarth_md:
        out["gatha_teeka_bhaavarth_hindi"].append({
            "natural_key": f"{secondary.publication_natural_key}:kalash:{k.kalash_number}:bhaavarth:hi",
            "gatha_teeka_bhaavarth_natural_key": f"{secondary.publication_natural_key}:kalash:{k.kalash_number}:bhaavarth:hi",
            "publication_natural_key": secondary.publication_natural_key,
            "gatha_teeka_natural_key": f"{secondary.natural_key}:kalash:{k.kalash_number}",
            "publisher_id": secondary.publisher_id,
            "gatha_number": k.kalash_number,
            "text": _lang_text("hin", k.secondary_teeka.gatha_teeka_bhaavarth_md),
        })
    return out


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
        },
        "mongo": {
            "gatha_prakrit": [],
            "gatha_sanskrit": [],
            "gatha_hindi_chhand": [],
            "gatha_word_meanings": [],
            "teeka_gatha_mapping": [],
            "gatha_teeka_sanskrit": [],
            "gatha_teeka_bhaavarth_hindi": [],
            "kalash_sanskrit": [],
            "kalash_hindi": [],
            "kalash_word_meanings": [],
        },
        "neo4j": {"nodes": [], "edges": []},
        "idempotency_contracts": {
            "gathas": "natural_key",
            "kalashas": "natural_key",
            "mongo": "natural_key",
        },
    }

    ww["postgres"]["authors"].append({
        "natural_key": cfg.shastra.author.natural_key,
        "display_name": _lang_text("hin", cfg.shastra.author.display_name_hi),
        "kind": cfg.shastra.author.kind,
    })
    for t in cfg.shastra.teekas:
        ww["postgres"]["authors"].append({
            "natural_key": t.teekakar_natural_key,
            "display_name": _lang_text("hin", t.teekakar_display_name_hi),
            "kind": "acharya",
        })
        ww["postgres"]["teekas"].append({
            "natural_key": t.natural_key,
            "shastra_natural_key": cfg.shastra.natural_key,
            "teekakar_natural_key": t.teekakar_natural_key,
        })
        ww["postgres"]["publications"].append({
            "natural_key": t.publication_natural_key,
            "teeka_natural_key": t.natural_key,
            "publisher_id": t.publisher_id,
        })
    ww["postgres"]["shastras"].append({
        "natural_key": cfg.shastra.natural_key,
        "title": _lang_text("hin", cfg.shastra.title_hi),
        "author_natural_key": cfg.shastra.author.natural_key,
    })

    for g in result.gathas:
        gatha_nk = _gatha_nk(g.shastra_natural_key, g.gatha_number)
        ww["postgres"]["gathas"].append({
            "natural_key": gatha_nk,
            "shastra_natural_key": g.shastra_natural_key,
            "gatha_number": g.gatha_number,
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
                if g.primary_teeka and any(k.global_kalash_index == int(nk.rsplit(":", 1)[1]) for k in g.primary_teeka.kalash_san)
            ),
            None,
        )
        ww["postgres"]["kalashas"].append({
            "natural_key": nk,
            "teeka_natural_key": primary.natural_key,
            "kalash_number": nk.rsplit(":", 1)[1],
            "gatha_natural_key": gatha_ref,
        })

    for k in result.secondary_kalashes:
        if secondary:
            ww["postgres"]["kalashas"].append({
                "natural_key": f"{secondary.natural_key}:kalash:{k.kalash_number}",
                "teeka_natural_key": secondary.natural_key,
                "kalash_number": k.kalash_number,
                "gatha_natural_key": (
                    _gatha_nk(result.shastra_natural_key, k.preceding_primary_gatha_number)
                    if k.preceding_primary_gatha_number
                    else None
                ),
            })
            ms = _build_mongo_for_secondary_kalash(k, secondary)
            for coll, docs in ms.items():
                ww["mongo"][coll].extend(docs)

    return {
        "shastra_parse_result": result.model_dump(mode="json"),
        "would_write": ww,
    }
