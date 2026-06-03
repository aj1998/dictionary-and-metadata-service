"""Resolve Neo4j stubs → NJ Mongo target documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from neo4j import AsyncDriver

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
}


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
        if block_kind == "sanskrit_gatha":
            return f"{stub_nk}:sanskrit"

    if stub_label == "GathaTeeka":
        teeka_nk = stub_props.get("teeka_natural_key") or ""
        gatha_nk = stub_props.get("gatha_natural_key") or ""
        gnum = gatha_nk.split(":")[-1] if gatha_nk else ""
        if block_kind == "sanskrit_text" and teeka_nk and gnum:
            return f"{teeka_nk}:{gnum}:{_TEEKA}:san"

    if stub_label == "GathaTeekaBhaavarth":
        pub_nk = stub_props.get("publication_natural_key") or ""
        gatha_nk = stub_props.get("gatha_natural_key") or ""
        gnum = gatha_nk.split(":")[-1] if gatha_nk else ""
        if block_kind == "hindi_text" and pub_nk and gnum:
            return f"{pub_nk}:{gnum}:{_BHAAVARTH}:hi"

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

    return targets


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
