"""Idempotent stub node and reference-edge helpers for Neo4j."""
from __future__ import annotations

from neo4j import AsyncDriver

STUB_SOURCE_DEFAULT = "jainkosh_ingestion"

_STUB_PROPS_BY_LABEL: dict[str, list[str]] = {
    "Keyword": ["display_text"],
    "Topic": ["display_text_hi", "topic_path", "parent_keyword_natural_key"],
    "Gatha": ["shastra_natural_key", "gatha_number"],
    "GathaTeeka": ["shastra_natural_key", "teeka_natural_key", "gatha_number"],
    "GathaTeekaBhaavarth": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "gatha_number"],
    "Kalash": ["teeka_natural_key", "kalash_number"],
    "KalashBhaavarth": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "kalash_number"],
    "Page": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "page_number"],
}

_VALID_LABELS = frozenset(_STUB_PROPS_BY_LABEL)
_VALID_EDGE_TYPES = frozenset({
    "HAS_TOPIC", "PART_OF", "RELATED_TO", "MENTIONS_TOPIC", "CONTAINS_DEFINITION",
})


async def sync_stub_node(
    driver: AsyncDriver,
    *,
    label: str,
    natural_key: str,
    props: dict,
    stub_source: str = STUB_SOURCE_DEFAULT,
    database: str = "jainkb",
) -> None:
    """Idempotent MERGE: creates stub if missing, leaves real data intact.

    Uses coalesce() so real nodes are never clobbered — is_stub stays false
    once a real sync has run.
    """
    if label not in _STUB_PROPS_BY_LABEL:
        raise ValueError(f"Unknown label for stub: {label!r}")
    allowed = _STUB_PROPS_BY_LABEL[label]
    set_lines = [
        "n.updated_at = datetime()",
        "n.created_at = coalesce(n.created_at, datetime())",
        "n.is_stub = coalesce(n.is_stub, true)",
        "n.stub_source = coalesce(n.stub_source, $stub_source)",
    ]
    for p in allowed:
        if p in props:
            set_lines.append(f"n.{p} = coalesce(n.{p}, ${p})")
    cypher = f"""
MERGE (n:{label} {{natural_key: $nk}})
SET {',\n    '.join(set_lines)}
"""
    params: dict = {"nk": natural_key, "stub_source": stub_source}
    params.update({k: v for k, v in props.items() if k in allowed})
    async with driver.session(database=database) as session:
        await session.run(cypher, **params)


async def sync_reference_edge(
    driver: AsyncDriver,
    *,
    edge_type: str,
    src_label: str,
    src_nk: str,
    tgt_label: str,
    tgt_nk: str,
    database: str = "jainkb",
) -> None:
    """MERGE both endpoints (stub safety net) then MERGE the edge.

    Label and edge_type are validated against allowlists before interpolation
    into the Cypher string.
    """
    if edge_type not in _VALID_EDGE_TYPES:
        raise ValueError(f"Unknown edge type: {edge_type!r}")
    if src_label not in _VALID_LABELS:
        raise ValueError(f"Unknown src_label: {src_label!r}")
    if tgt_label not in _VALID_LABELS:
        raise ValueError(f"Unknown tgt_label: {tgt_label!r}")
    async with driver.session(database=database) as session:
        await session.run(
            f"""
MERGE (src:{src_label} {{natural_key: $s}})
  SET src.is_stub = coalesce(src.is_stub, true),
      src.stub_source = CASE WHEN src.is_stub = false THEN src.stub_source ELSE coalesce(src.stub_source, 'jainkosh_ingestion') END,
      src.created_at = coalesce(src.created_at, datetime())
MERGE (tgt:{tgt_label} {{natural_key: $t}})
  SET tgt.is_stub = coalesce(tgt.is_stub, true),
      tgt.stub_source = CASE WHEN tgt.is_stub = false THEN tgt.stub_source ELSE coalesce(tgt.stub_source, 'jainkosh_ingestion') END,
      tgt.created_at = coalesce(tgt.created_at, datetime())
MERGE (src)-[r:{edge_type}]->(tgt)
SET r.weight = coalesce(r.weight, 1.0), r.source = 'jainkosh'
""",
            s=src_nk,
            t=tgt_nk,
        )
