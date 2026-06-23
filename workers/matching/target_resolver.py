"""Resolve Neo4j stubs → NJ Mongo target documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from neo4j import AsyncDriver

from jain_kb_common.shastra_identifiers import get_identifier_fields

from .source_iter import SourceBlock

logger = logging.getLogger("jain_kb.matching.target_resolver")

# Stub label → Devanagari segment used in Kalash Mongo natural_key
_KALASH = "कलश"
_TEEKA = "टीका"
_BHAAVARTH = "भावार्थ"

# (stub_label, block_kind) → Mongo collection name
_ROUTING: dict[tuple[str, str], str] = {
    ("Gatha", "prakrit_gatha"): "gatha_prakrit",
    ("Gatha", "prakrit_text"): "gatha_prakrit",
    ("Gatha", "sanskrit_gatha"): "gatha_sanskrit",
    # Root "shastra"-type shastras whose primary verse is Sanskrit (e.g.
    # तत्त्वार्थसूत्र) are extracted by JainKosh as a `sanskrit_text` block but
    # emit a `Gatha` stub — the sutra *is* the gatha. Its Sanskrit body lives in
    # `gatha_sanskrit`, so route there rather than dropping the edge.
    ("Gatha", "sanskrit_text"): "gatha_sanskrit",
    ("GathaTeeka", "sanskrit_text"): "gatha_teeka_sanskrit",
    ("GathaTeekaBhaavarth", "hindi_text"): "gatha_teeka_bhaavarth_hindi",
    ("Kalash", "sanskrit_gatha"): "kalash_sanskrit",
    ("Kalash", "sanskrit_text"): "kalash_sanskrit",
    ("Kalash", "hindi_gatha"): "kalash_hindi",
    ("Kalash", "hindi_text"): "kalash_hindi",
    ("KalashBhaavarth", "hindi_text"): "kalash_bhaavarth_hindi",
}

_ALL_STUB_LABELS: frozenset[str] = frozenset({l for l, _ in _ROUTING} | {"Page"})

_COLLECTION_LANG: dict[str, str] = {
    "gatha_prakrit": "pra",
    "gatha_sanskrit": "san",
    "gatha_teeka_sanskrit": "san",
    "gatha_teeka_bhaavarth_hindi": "hin",
    "kalash_sanskrit": "san",
    "kalash_hindi": "hin",
    "kalash_bhaavarth_hindi": "hin",
    "teeka_gatha_mapping": "hin",
}

# Gatha-verse collections whose Gatha stub also carries a Hindi अन्वयार्थ
# (शब्दार्थ panel) worth matching the block's `hindi_translation` against.
_GATHA_VERSE_COLLECTIONS: frozenset[str] = frozenset({"gatha_prakrit", "gatha_sanskrit"})
_TEEKA_GATHA_MAPPING = "teeka_gatha_mapping"

# Sanskrit-teeka collection whose source block (sanskrit_text) also carries a
# Hindi भावार्थ worth matching the block's `hindi_translation` against.
_GATHA_TEEKA_SANSKRIT = "gatha_teeka_sanskrit"
_GATHA_TEEKA_BHAAVARTH_HINDI = "gatha_teeka_bhaavarth_hindi"


@dataclass
class Target:
    collection: str
    natural_key: str
    stub_label: str
    shastra_natural_key: str | None
    gatha_natural_key: str | None
    lang: str | None
    text: str | None            # extracted from Mongo doc; None if target_missing
    status_hint: str | None     # "target_missing" when Mongo doc absent
    # Which source-block field to match against this target's text. "devanagari"
    # uses the source-language verse (`text_devanagari`); "hindi_translation"
    # uses the block's absorbed Hindi translation (for the अन्वयार्थ/शब्दार्थ
    # panel). Drives both the source text and the score threshold.
    source_text_kind: str = "devanagari"
    # Block kind used to pick the matching threshold; defaults to the source
    # block's own kind when None.
    match_block_kind: str | None = None


def _padded_variant_nk(nk: str, width: int = 3) -> str | None:
    """Return a copy of `nk` with the last all-numeric colon-segment re-padded
    to (or stripped from) `width` digits.

    Used as a zero-padding fallback for compound-shastra Mongo lookups, where
    JainKosh emits raw numeric values from citations ("…:गाथा:12") while NJ
    ingestion stores zero-padded ones ("…:गाथा:012").

    Walks segments right-to-left so suffixes like `:prakrit` / `:sanskrit` /
    `:टीका:san` are skipped, and only the actual gatha-number segment is
    rewritten. Returns the alternate-padding form (padded if input was
    unpadded, unpadded if input was padded). Returns None if no numeric
    segment is found.
    """
    if not nk:
        return None
    parts = nk.split(":")
    for i in range(len(parts) - 1, -1, -1):
        seg = parts[i]
        if seg.isdigit():
            stripped = seg.lstrip("0") or "0"
            padded = stripped.rjust(width, "0")
            new_seg = padded if seg == stripped else stripped
            if new_seg == seg:
                return None
            parts[i] = new_seg
            return ":".join(parts)
    return None


def _mongo_seg_from_gatha_nk(gatha_nk: str, shastra_nk: str | None) -> str:
    """Recover the Mongo per-gatha segment from a compound or legacy Gatha NK.

    Compound (e.g. परमात्मप्रकाश): `परमात्मप्रकाश:अधिकार:1:गाथा:001`
      → `अधिकार:1:गाथा:001` (full suffix after the shastra prefix).
    Legacy (e.g. समयसार): `समयसार:गाथा:8` → `8` (bare number only).

    Mirrors `workers/ingestion/nj/envelope._gatha_mongo_segment` so the keys
    constructed here line up with what NJ ingestion wrote to Mongo.
    """
    if not gatha_nk:
        return ""
    if shastra_nk and get_identifier_fields(shastra_nk, "gatha"):
        prefix = f"{shastra_nk}:"
        if gatha_nk.startswith(prefix):
            return gatha_nk[len(prefix):]
    return gatha_nk.split(":")[-1]


def _derive_mongo_nk(
    stub_label: str,
    block_kind: str,
    stub_nk: str,
    stub_props: dict,
) -> str | None:
    """Construct Mongo document natural_key from Neo4j stub properties."""
    if stub_label == "Gatha":
        if block_kind in ("prakrit_gatha", "prakrit_text"):
            return f"{stub_nk}:prakrit"
        if block_kind in ("sanskrit_gatha", "sanskrit_text"):
            return f"{stub_nk}:sanskrit"

    if stub_label == "GathaTeeka":
        teeka_nk = stub_props.get("teeka_natural_key") or ""
        gatha_nk = stub_props.get("gatha_natural_key") or ""
        shastra_nk = stub_props.get("shastra_natural_key") or ""
        gseg = _mongo_seg_from_gatha_nk(gatha_nk, shastra_nk)
        if block_kind == "sanskrit_text" and teeka_nk and gseg:
            return f"{teeka_nk}:{gseg}:{_TEEKA}:san"

    if stub_label == "GathaTeekaBhaavarth":
        pub_nk = stub_props.get("publication_natural_key") or ""
        gatha_nk = stub_props.get("gatha_natural_key") or ""
        shastra_nk = stub_props.get("shastra_natural_key") or ""
        gseg = _mongo_seg_from_gatha_nk(gatha_nk, shastra_nk)
        if block_kind == "hindi_text" and pub_nk and gseg:
            return f"{pub_nk}:{gseg}:{_BHAAVARTH}:hi"

    if stub_label == "Kalash":
        if block_kind in ("sanskrit_gatha", "sanskrit_text"):
            return f"{stub_nk}:san"
        if block_kind in ("hindi_gatha", "hindi_text"):
            return f"{stub_nk}:hi"

    if stub_label == "KalashBhaavarth":
        pub_nk = stub_props.get("publication_natural_key") or ""
        kalash_num = stub_props.get("kalash_number") or ""
        if block_kind == "hindi_text" and pub_nk and kalash_num:
            return f"{pub_nk}:{_KALASH}:{_BHAAVARTH}:{kalash_num}"

    return None


def _shastra_nk_from_stub(stub_label: str, stub_props: dict, stub_nk: str) -> str | None:
    """Best-effort shastra_natural_key extraction."""
    direct = stub_props.get("shastra_natural_key")
    if direct:
        return direct
    # Fallback: first segment of stub_nk (works for samaysar:गाथा:1 → samaysar)
    return stub_nk.split(":")[0] if stub_nk else None


async def resolve_targets(
    neo4j: AsyncDriver,
    mongo,
    source: SourceBlock,
    *,
    database: str = "jainkb",
) -> list[Target]:
    """
    Walk Neo4j edges from the source block to stub nodes, then route each stub
    to the appropriate NJ Mongo collection and verify the doc exists.
    """
    # Choose edge type and node label based on source kind
    if source.kind == "keyword_definition":
        edge_type = "CONTAINS_DEFINITION"
        parent_label = "Keyword"
        cypher = """
MATCH (stub)-[r:CONTAINS_DEFINITION]->(parent:Keyword {natural_key: $parent_nk})
WHERE r.block_index = $block_idx
  AND r.section_index = $section_idx
  AND r.definition_index = $def_idx
RETURN
  stub.natural_key AS stub_nk,
  labels(stub) AS stub_labels,
  stub.teeka_natural_key AS teeka_natural_key,
  stub.gatha_natural_key AS gatha_natural_key,
  stub.publication_natural_key AS publication_natural_key,
  stub.kalash_number AS kalash_number,
  stub.shastra_natural_key AS shastra_natural_key
"""
        params = {
            "parent_nk": source.parent_natural_key,
            "block_idx": source.block_index,
            "section_idx": source.section_index,
            "def_idx": source.definition_index,
        }
    else:
        cypher = """
MATCH (stub)-[r:MENTIONS_TOPIC]->(parent:Topic {natural_key: $parent_nk})
WHERE r.block_index = $block_idx
RETURN
  stub.natural_key AS stub_nk,
  labels(stub) AS stub_labels,
  stub.teeka_natural_key AS teeka_natural_key,
  stub.gatha_natural_key AS gatha_natural_key,
  stub.publication_natural_key AS publication_natural_key,
  stub.kalash_number AS kalash_number,
  stub.shastra_natural_key AS shastra_natural_key
"""
        params = {
            "parent_nk": source.parent_natural_key,
            "block_idx": source.block_index,
        }

    targets: list[Target] = []

    async with neo4j.session(database=database) as session:
        result = await session.run(cypher, **params)
        records = await result.data()

    for rec in records:
        stub_nk: str = rec["stub_nk"] or ""
        stub_labels: list[str] = rec.get("stub_labels") or []
        stub_label = next(
            (l for l in stub_labels if l in _ALL_STUB_LABELS),
            None,
        )
        if stub_label is None:
            logger.warning(
                "unknown stub label(s) %s for stub %s — skip",
                stub_labels, stub_nk,
            )
            continue

        if stub_label == "Page":
            logger.debug("Page stub %s skipped in v1", stub_nk)
            continue

        collection = _ROUTING.get((stub_label, source.block_kind))
        if collection is None:
            logger.warning(
                "no routing for (stub=%s, block_kind=%s) — skip",
                stub_label, source.block_kind,
            )
            continue

        stub_props = {
            "teeka_natural_key": rec.get("teeka_natural_key"),
            "gatha_natural_key": rec.get("gatha_natural_key"),
            "publication_natural_key": rec.get("publication_natural_key"),
            "kalash_number": rec.get("kalash_number"),
            "shastra_natural_key": rec.get("shastra_natural_key"),
        }

        mongo_nk = _derive_mongo_nk(stub_label, source.block_kind, stub_nk, stub_props)
        if mongo_nk is None:
            logger.warning(
                "cannot derive Mongo nk for stub=%s block_kind=%s — skip",
                stub_nk, source.block_kind,
            )
            continue

        shastra_nk = _shastra_nk_from_stub(stub_label, stub_props, stub_nk)
        # gatha_natural_key for the target metadata
        gatha_nk: str | None = stub_props.get("gatha_natural_key")
        if stub_label == "Gatha":
            gatha_nk = stub_nk

        # Fetch the Mongo doc
        mongo_doc = await mongo[collection].find_one({"natural_key": mongo_nk})
        if mongo_doc is None:
            # Compound-shastra zero-padding fallback: JainKosh's reference parser
            # builds stub NKs with raw values from the citation (e.g.
            # "…:गाथा:12"), but NJ ingestion zero-pads gatha numbers in the
            # compound suffix ("…:गाथा:012"). Try alternate paddings of the
            # last numeric segment in the stored NK so both citation forms hit
            # the same Mongo doc. Mirrors `_find_compound_gatha_fuzzy` on the
            # API side (services/core_service/.../routers/gathas.py).
            alt_nk = _padded_variant_nk(mongo_nk)
            if alt_nk and alt_nk != mongo_nk:
                mongo_doc = await mongo[collection].find_one({"natural_key": alt_nk})
                if mongo_doc is not None:
                    logger.info(
                        "fuzzy zero-pad match: %s → %s", mongo_nk, alt_nk
                    )
                    mongo_nk = alt_nk
                    # Keep the metadata gatha_nk consistent with what the doc
                    # actually lives under, so UI deep-links resolve.
                    if stub_label == "Gatha" and gatha_nk:
                        gatha_nk = _padded_variant_nk(gatha_nk) or gatha_nk
        text: str | None = None
        status_hint: str | None = None

        if mongo_doc is None:
            logger.info(
                "target_missing: collection=%s natural_key=%s", collection, mongo_nk
            )
            status_hint = "target_missing"
        else:
            text_list = mongo_doc.get("text", [])
            if text_list and isinstance(text_list, list) and text_list[0]:
                text = text_list[0].get("text") if isinstance(text_list[0], dict) else None

        targets.append(Target(
            collection=collection,
            natural_key=mongo_nk,
            stub_label=stub_label,
            shastra_natural_key=shastra_nk,
            gatha_natural_key=gatha_nk,
            lang=_COLLECTION_LANG.get(collection),
            text=text,
            status_hint=status_hint,
        ))

        # Second target: the gatha's Hindi अन्वयार्थ (शब्दार्थ panel). When the
        # primary verse target is a Gatha and the source block carries an
        # absorbed Hindi translation, also match that translation against the
        # gatha's first teeka_gatha_mapping doc (mirrors the reading page's
        # `primaryMapping = teekaMapping[0]`), so the अन्वयार्थ panel highlights
        # alongside the verse.
        if (
            stub_label == "Gatha"
            and collection in _GATHA_VERSE_COLLECTIONS
            and source.hindi_translation
            and gatha_nk
        ):
            anvayartha = await _resolve_anvayartha_target(
                mongo, gatha_nk, shastra_nk
            )
            if anvayartha is not None:
                targets.append(anvayartha)

        # Second target: the gatha's Hindi भावार्थ (bhaavarth panel). A
        # `sanskrit_text` block carries the Sanskrit teeka in `text_devanagari`
        # (matched above against `gatha_teeka_sanskrit`) and its Hindi
        # translation — which IS the published भावार्थ — in `hindi_translation`.
        # Mirror the अन्वयार्थ pattern: when the primary target is a Sanskrit
        # teeka and the block has a Hindi translation, also match that
        # translation against the gatha's `gatha_teeka_bhaavarth_hindi` doc so
        # the भावार्थ panel highlights alongside the teeka.
        if (
            stub_label == "GathaTeeka"
            and collection == _GATHA_TEEKA_SANSKRIT
            and source.hindi_translation
        ):
            # Strip the `:टीका:san` suffix to recover the teeka_gatha key
            # (`{teeka_nk}:{gseg}`), which the bhaavarth doc stores as
            # `gatha_teeka_natural_key`.
            gatha_teeka_nk = mongo_nk
            for suffix in (f":{_TEEKA}:san", f":{_TEEKA}:hi"):
                if gatha_teeka_nk.endswith(suffix):
                    gatha_teeka_nk = gatha_teeka_nk[: -len(suffix)]
                    break
            bhaavarth = await _resolve_bhaavarth_target(
                mongo, gatha_teeka_nk, gatha_nk, shastra_nk
            )
            if bhaavarth is not None:
                targets.append(bhaavarth)

    return targets


async def _resolve_bhaavarth_target(
    mongo,
    gatha_teeka_nk: str,
    gatha_nk: str | None,
    shastra_nk: str | None,
) -> Target | None:
    """Build a `gatha_teeka_bhaavarth_hindi` (भावार्थ) target for a sanskrit teeka.

    The bhaavarth doc is keyed independently of the teeka (it carries a
    publication index, e.g. `…:0:96:भावार्थ:hi`), but stores the owning teeka's
    `gatha_teeka_natural_key` (`{teeka_nk}:{gseg}`), so we look it up by that
    field rather than re-deriving the publication-prefixed NK. Returns None when
    no bhaavarth doc exists (so we don't emit a noisy `target_missing` for teekas
    that simply have no भावार्थ). The matched text is the doc's first `text`
    entry — exactly what the भावार्थ panel renders and highlights against.
    """
    doc = await mongo[_GATHA_TEEKA_BHAAVARTH_HINDI].find_one(
        {"gatha_teeka_natural_key": gatha_teeka_nk}
    )
    if doc is None:
        return None
    text_list = doc.get("text", [])
    text = None
    if text_list and isinstance(text_list, list) and text_list[0]:
        text = text_list[0].get("text") if isinstance(text_list[0], dict) else None
    if not text:
        return None
    return Target(
        collection=_GATHA_TEEKA_BHAAVARTH_HINDI,
        natural_key=doc["natural_key"],
        stub_label="GathaTeekaBhaavarth",
        shastra_natural_key=shastra_nk,
        gatha_natural_key=gatha_nk,
        lang=_COLLECTION_LANG.get(_GATHA_TEEKA_BHAAVARTH_HINDI),
        text=text,
        status_hint=None,
        source_text_kind="hindi_translation",
        match_block_kind="hindi_text",
    )


async def _resolve_anvayartha_target(
    mongo,
    gatha_nk: str,
    shastra_nk: str | None,
) -> Target | None:
    """Build a teeka_gatha_mapping (अन्वयार्थ) target for a gatha.

    Mirrors core_service's `primaryMapping = teekaMapping[0]`: the first
    teeka_gatha_mapping doc for the gatha. Returns None when no mapping doc
    exists (so we don't emit a noisy target_missing row for gathas that simply
    have no anvayartha). The matched text is the doc's `full_anyavaarth`, which
    is exactly what the शब्दार्थ panel renders and highlights against.
    """
    doc = await mongo[_TEEKA_GATHA_MAPPING].find_one({"gatha_natural_key": gatha_nk})
    if doc is None:
        return None
    text = doc.get("full_anyavaarth")
    if not text:
        anv = doc.get("anvayartha") or []
        if anv and isinstance(anv[0], dict):
            text = anv[0].get("text")
    if not text:
        return None
    return Target(
        collection=_TEEKA_GATHA_MAPPING,
        natural_key=doc["natural_key"],
        stub_label="Gatha",
        shastra_natural_key=shastra_nk,
        gatha_natural_key=gatha_nk,
        lang=_COLLECTION_LANG.get(_TEEKA_GATHA_MAPPING),
        text=text,
        status_hint=None,
        source_text_kind="hindi_translation",
        match_block_kind="hindi_text",
    )


async def resolve_targets_for_shastra(
    neo4j: AsyncDriver,
    *,
    shastra_nk: str,
    database: str = "jainkb",
) -> list[dict]:
    """
    Return list of {parent_nk, parent_label, block_idx, section_idx, def_idx}
    for all source blocks whose stub targets belong to the given shastra.
    """
    cypher = """
MATCH (stub {shastra_natural_key: $shastra_nk})-[r:CONTAINS_DEFINITION|MENTIONS_TOPIC]->(parent)
WHERE (parent:Keyword OR parent:Topic)
RETURN DISTINCT
  parent.natural_key AS parent_nk,
  labels(parent) AS parent_labels,
  r.block_index AS block_idx,
  r.section_index AS section_idx,
  r.definition_index AS def_idx
"""
    async with neo4j.session(database=database) as session:
        result = await session.run(cypher, shastra_nk=shastra_nk)
        records = await result.data()
    return records
