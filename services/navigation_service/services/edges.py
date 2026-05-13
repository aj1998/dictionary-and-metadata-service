"""Manual topic→topic semantic edge administration (Neo4j only, no Postgres table)."""
from __future__ import annotations

from neo4j import AsyncDriver

from jain_kb_common.db.neo4j.schema_check import UnknownEdgeTypeError, validate_edge_type

_STRUCTURAL_TYPES = frozenset({"IN_SHASTRA", "IN_TEEKA", "IN_PUBLICATION"})
_ALLOWED_ADMIN_TYPES = frozenset({"IS_A", "PART_OF", "RELATED_TO"})


def _validate_admin_edge_type(edge_type: str) -> None:
    validate_edge_type(edge_type)
    if edge_type in _STRUCTURAL_TYPES or edge_type not in _ALLOWED_ADMIN_TYPES:
        raise ValueError(
            f"Edge type {edge_type!r} is not allowed for admin writes. "
            f"Allowed: {sorted(_ALLOWED_ADMIN_TYPES)}"
        )


async def add_topic_edge(
    driver: AsyncDriver,
    *,
    source_nk: str,
    target_nk: str,
    edge_type: str,
    weight: float = 1.0,
    database: str = "jainkb",
) -> None:
    _validate_admin_edge_type(edge_type)

    # edge_type is validated against allowlist — safe to interpolate
    cypher = f"""
MERGE (src:Topic {{natural_key: $src_nk}})
  SET src.is_stub = coalesce(src.is_stub, true),
      src.created_at = coalesce(src.created_at, datetime())
MERGE (tgt:Topic {{natural_key: $tgt_nk}})
  SET tgt.is_stub = coalesce(tgt.is_stub, true),
      tgt.created_at = coalesce(tgt.created_at, datetime())
MERGE (src)-[r:{edge_type}]->(tgt)
SET r.weight = $weight, r.source = 'admin', r.updated_at = datetime()
"""
    async with driver.session(database=database) as session:
        await session.run(cypher, src_nk=source_nk, tgt_nk=target_nk, weight=weight)


async def remove_topic_edge(
    driver: AsyncDriver,
    *,
    source_nk: str,
    target_nk: str,
    edge_type: str,
    database: str = "jainkb",
) -> None:
    _validate_admin_edge_type(edge_type)

    cypher = f"""
MATCH (src:Topic {{natural_key: $src_nk}})-[r:{edge_type}]->(tgt:Topic {{natural_key: $tgt_nk}})
DELETE r
"""
    async with driver.session(database=database) as session:
        await session.run(cypher, src_nk=source_nk, tgt_nk=target_nk)
