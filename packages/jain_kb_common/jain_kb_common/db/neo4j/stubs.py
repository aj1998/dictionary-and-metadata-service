"""Idempotent stub node and reference-edge helpers for Neo4j."""
from __future__ import annotations

from neo4j import AsyncDriver

STUB_SOURCE_DEFAULT = "jainkosh_ingestion"


def _sources_clause(var: str, param: str = "src") -> str:
    """Return a Cypher fragment that performs a set-union of ${param} into {var}.sources."""
    return (
        f"{var}.sources = CASE\n"
        f"  WHEN ${param} IS NULL THEN coalesce({var}.sources, [])\n"
        f"  WHEN ${param} IN coalesce({var}.sources, []) THEN {var}.sources\n"
        f"  ELSE coalesce({var}.sources, []) + ${param}\n"
        f"END"
    )

_STUB_PROPS_BY_LABEL: dict[str, list[str]] = {
    "Keyword": ["display_text"],
    "Topic": ["display_text_hi", "topic_path", "parent_keyword_natural_key"],
    "Gatha": ["shastra_natural_key", "gatha_number"],
    "GathaTeeka": ["shastra_natural_key", "teeka_natural_key", "gatha_number"],
    "GathaTeekaBhaavarth": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "gatha_number"],
    "Kalash": ["teeka_natural_key", "kalash_number"],
    "KalashBhaavarth": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "kalash_number"],
    "Page": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "page_number"],
    "Shastra": [],
    "Teeka": ["shastra_natural_key"],
    "Publication": ["teeka_natural_key", "publisher_id"],
    "Table": ["parent_natural_key", "parent_kind", "seq", "source"],
}

_VALID_LABELS = frozenset(_STUB_PROPS_BY_LABEL)
_VALID_EDGE_TYPES = frozenset({
    "HAS_TOPIC", "PART_OF", "RELATED_TO", "MENTIONS_TOPIC", "MENTIONS_KEYWORD", "CONTAINS_DEFINITION",
    "HAS_TEEKA", "HAS_PUBLICATION",
    "IN_SHASTRA", "IN_TEEKA", "IN_PUBLICATION",
    "CONTAINS_TABLE", "MENTIONS_TABLE",
})


async def sync_stub_node(
    driver: AsyncDriver,
    *,
    label: str,
    natural_key: str,
    props: dict,
    stub_source: str = STUB_SOURCE_DEFAULT,
    source: str | None = None,
    database: str = "jainkb",
) -> None:
    """Idempotent MERGE: creates stub if missing, leaves real data intact.

    Uses coalesce() so real nodes are never clobbered — is_stub stays false
    once a real sync has run.
    `source` (e.g. "jainkosh"/"nj") is union-merged into the node's `sources`
    list; pass None to leave `sources` untouched.
    """
    if label not in _STUB_PROPS_BY_LABEL:
        raise ValueError(f"Unknown label for stub: {label!r}")
    allowed = _STUB_PROPS_BY_LABEL[label]
    set_lines = [
        "n.updated_at = datetime()",
        "n.created_at = coalesce(n.created_at, datetime())",
        "n.is_stub = coalesce(n.is_stub, true)",
        "n.stub_source = coalesce(n.stub_source, $stub_source)",
        _sources_clause("n"),
    ]
    for p in allowed:
        if p in props:
            set_lines.append(f"n.{p} = coalesce(n.{p}, ${p})")
    cypher = f"""
MERGE (n:{label} {{natural_key: $nk}})
SET {',\n    '.join(set_lines)}
"""
    params: dict = {"nk": natural_key, "stub_source": stub_source, "src": source}
    params.update({k: v for k, v in props.items() if k in allowed})
    async with driver.session(database=database) as session:
        await session.run(cypher, **params)


async def delete_placeholder_stub(
    driver: AsyncDriver,
    *,
    label: str,
    natural_key: str,
    database: str = "jainkb",
) -> None:
    """Delete a placeholder stub node (and all its edges) if it is still marked is_stub=true.

    Called during pass 2 when a numerical resolve_key placeholder (e.g. 'स्वभाव:2')
    is resolved to an actual heading-based natural_key.  The placeholder node was written
    in pass 1 as a fallback; it must be removed so the graph is not polluted with
    orphaned numerical stubs.  DETACH DELETE removes the node and all incident edges.
    If the node was upgraded to a real node by another process (is_stub=false), it is
    left untouched.
    """
    if label not in _VALID_LABELS:
        raise ValueError(f"Unknown label for stub deletion: {label!r}")
    async with driver.session(database=database) as session:
        await session.run(
            f"MATCH (n:{label} {{natural_key: $nk}}) WHERE n.is_stub = true DETACH DELETE n",
            nk=natural_key,
        )


async def sync_reference_edge(
    driver: AsyncDriver,
    *,
    edge_type: str,
    src_label: str,
    src_nk: str,
    tgt_label: str,
    tgt_nk: str,
    edge_props: dict | None = None,
    database: str = "jainkb",
) -> None:
    """MERGE both endpoints (stub safety net) then MERGE the edge.

    Label and edge_type are validated against allowlists before interpolation
    into the Cypher string. edge_props (e.g. block_index, section_index,
    definition_index) are written onto the relationship via SET r += $rel_props.
    """
    if edge_type not in _VALID_EDGE_TYPES:
        raise ValueError(f"Unknown edge type: {edge_type!r}")
    if src_label not in _VALID_LABELS:
        raise ValueError(f"Unknown src_label: {src_label!r}")
    if tgt_label not in _VALID_LABELS:
        raise ValueError(f"Unknown tgt_label: {tgt_label!r}")
    rel_props: dict = {"weight": 1.0, "source": "jainkosh"}
    if edge_props:
        rel_props.update(edge_props)
    # Block-level identifiers must be part of the MERGE key — otherwise a topic
    # / keyword that references the same target from multiple blocks would
    # collapse onto a single edge, and the matcher would only see the last
    # block_index written. -1 is used as a "not applicable" sentinel so the
    # MERGE pattern stays the same for keyword vs topic edges.
    merge_block_index = rel_props.get("block_index", -1)
    merge_section_index = rel_props.get("section_index", -1)
    merge_definition_index = rel_props.get("definition_index", -1)
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
MERGE (src)-[r:{edge_type} {{
    block_index: $bi,
    section_index: $si,
    definition_index: $di
}}]->(tgt)
SET r += $rel_props
""",
            s=src_nk,
            t=tgt_nk,
            rel_props=rel_props,
            bi=merge_block_index,
            si=merge_section_index,
            di=merge_definition_index,
        )
