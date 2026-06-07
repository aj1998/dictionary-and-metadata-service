"""Neo4j graph traversal queries for the navigation service.

All public functions execute a single Cypher round-trip per call.
Stub filtering is done at the Cypher level (WHERE NOT n.is_stub).
"""
from __future__ import annotations

from neo4j import AsyncDriver

_STRUCTURAL_TYPES = frozenset({"IN_SHASTRA", "IN_TEEKA", "IN_PUBLICATION"})
_SEMANTIC_TYPES = frozenset({"IS_A", "PART_OF", "RELATED_TO"})


def _safe_depth(depth: int) -> int:
    return max(1, min(depth, 3))


def _build_neighbor_query(
    edge_types: list[str],
    depth: int,
    exclude_stubs: bool,
) -> str:
    """Build one-shot UNION Cypher for topic neighbor traversal."""
    d = _safe_depth(depth)
    stub_clause = "AND NOT coalesce(t.is_stub, false)" if exclude_stubs else ""

    # Partition edge types: RELATED_TO is undirected; others are directional
    directional = [et for et in edge_types if et != "RELATED_TO" and et not in _STRUCTURAL_TYPES]
    has_related = "RELATED_TO" in edge_types

    parts: list[str] = []

    if directional:
        et_str = "|".join(directional)
        # Outbound direction
        parts.append(f"""
MATCH (src:Topic {{natural_key: $nk}})
MATCH p1 = (src)-[:{et_str}*1..{d}]->(t:Topic)
WHERE t <> src {stub_clause}
WITH src, t, relationships(p1) AS rels
WITH t, type(rels[0]) AS edge_type, 'outbound' AS edge_direction, coalesce(rels[0].weight, 1.0) AS weight
RETURN t.natural_key AS natural_key, t.display_text_hi AS display_text_hi,
       labels(t)[0] AS label, edge_type, edge_direction, weight, coalesce(t.is_stub, false) AS is_stub
""")
        # Inbound direction
        parts.append(f"""
MATCH (src:Topic {{natural_key: $nk}})
MATCH p2 = (src)<-[:{et_str}*1..{d}]-(t:Topic)
WHERE t <> src {stub_clause}
WITH src, t, relationships(p2) AS rels
WITH t, type(rels[0]) AS edge_type, 'inbound' AS edge_direction, coalesce(rels[0].weight, 1.0) AS weight
RETURN t.natural_key AS natural_key, t.display_text_hi AS display_text_hi,
       labels(t)[0] AS label, edge_type, edge_direction, weight, coalesce(t.is_stub, false) AS is_stub
""")

    if has_related:
        parts.append(f"""
MATCH (src:Topic {{natural_key: $nk}})
MATCH p3 = (src)-[:RELATED_TO*1..{d}]-(t:Topic)
WHERE t <> src {stub_clause}
WITH src, t, relationships(p3) AS rels
WITH t, 'RELATED_TO' AS edge_type, 'undirected' AS edge_direction, coalesce(rels[0].weight, 1.0) AS weight
RETURN t.natural_key AS natural_key, t.display_text_hi AS display_text_hi,
       labels(t)[0] AS label, edge_type, edge_direction, weight, coalesce(t.is_stub, false) AS is_stub
""")

    if not parts:
        # No valid edge types → return empty via a no-match query
        return "MATCH (n:_NoSuchLabel) RETURN n.natural_key AS natural_key, n.display_text_hi AS display_text_hi, '' AS label, '' AS edge_type, '' AS edge_direction, 0.0 AS weight, false AS is_stub"

    return "\nUNION\n".join(parts)


async def get_topic_neighbors(
    driver: AsyncDriver,
    *,
    topic_nk: str,
    edge_types: list[str],
    depth: int = 1,
    exclude_stubs: bool = True,
    database: str = "jainkb",
) -> list[dict]:
    # Filter out structural edge types silently
    allowed = [et for et in edge_types if et not in _STRUCTURAL_TYPES]
    if not allowed:
        return []

    cypher = _build_neighbor_query(allowed, depth, exclude_stubs)
    seen: set[str] = set()
    results: list[dict] = []

    async with driver.session(database=database) as session:
        result = await session.run(cypher, nk=topic_nk)
        records = await result.data()

    for r in records:
        nk = r["natural_key"]
        if nk and nk not in seen:
            seen.add(nk)
            results.append({
                "natural_key": nk,
                "display_text_hi": r.get("display_text_hi"),
                "label": r.get("label") or "Topic",
                "edge_type": r["edge_type"],
                "edge_direction": r["edge_direction"],
                "weight": r.get("weight", 1.0),
                "is_stub": bool(r.get("is_stub", False)),
            })
    return results


async def get_keyword_topics(
    driver: AsyncDriver,
    *,
    keyword_nk: str,
    edge_types: list[str],
    depth: int = 1,
    exclude_stubs: bool = True,
    database: str = "jainkb",
) -> list[dict]:
    d = _safe_depth(depth)
    et_str = "|".join(et for et in edge_types if et not in _STRUCTURAL_TYPES) or "HAS_TOPIC"
    stub_clause = "AND NOT coalesce(t.is_stub, false)" if exclude_stubs else ""

    cypher = f"""
MATCH (k:Keyword {{natural_key: $nk}})
MATCH p = (k)-[:{et_str}*1..{d}]->(t:Topic)
WHERE true {stub_clause}
WITH t, relationships(p) AS rels
RETURN DISTINCT t.natural_key AS natural_key, t.display_text_hi AS display_text_hi,
       type(rels[0]) AS edge_type, coalesce(t.is_stub, false) AS is_stub
"""
    async with driver.session(database=database) as session:
        result = await session.run(cypher, nk=keyword_nk)
        records = await result.data()

    return [
        {
            "natural_key": r["natural_key"],
            "display_text_hi": r.get("display_text_hi"),
            "edge_type": r["edge_type"],
            "is_stub": bool(r.get("is_stub", False)),
        }
        for r in records
        if r["natural_key"]
    ]


async def get_topic_ancestors(
    driver: AsyncDriver,
    *,
    topic_nk: str,
    database: str = "jainkb",
) -> dict:
    """Walk PART_OF outbound from topic to its root.

    Returns: {parent_keyword_natural_key, ancestors: [root_topic_nk, ..., direct_parent_nk]}
    Ancestors does NOT include the topic itself.
    """
    cypher = """
MATCH (t:Topic {natural_key: $nk})
OPTIONAL MATCH path = (t)-[:PART_OF*0..50]->(root:Topic)
WHERE NOT (root)-[:PART_OF]->(:Topic)
WITH t, path, root
ORDER BY length(path) DESC
LIMIT 1
WITH t, coalesce(nodes(path), [t]) AS chain
RETURN [n IN chain | n.natural_key] AS chain_nks,
       t.parent_keyword_natural_key AS parent_keyword
"""
    async with driver.session(database=database) as session:
        result = await session.run(cypher, nk=topic_nk)
        record = await result.single()

    if not record:
        return {"parent_keyword_natural_key": None, "ancestors": []}

    chain = record.get("chain_nks") or []
    # chain is [topic, parent, ..., root]; reverse and drop topic itself
    ancestors = list(reversed(chain))[:-1] if chain else []
    return {
        "parent_keyword_natural_key": record.get("parent_keyword"),
        "ancestors": ancestors,
    }


async def get_topic_related(
    driver: AsyncDriver,
    *,
    topic_nk: str,
    exclude_stubs: bool = False,
    database: str = "jainkb",
) -> list[dict]:
    """RELATED_TO neighbors of a topic — returns Topic AND Keyword targets."""
    stub_clause = "AND NOT coalesce(n.is_stub, false)" if exclude_stubs else ""
    cypher = f"""
MATCH (src:Topic {{natural_key: $nk}})-[:RELATED_TO]-(n)
WHERE (n:Topic OR n:Keyword) AND n <> src {stub_clause}
RETURN DISTINCT n.natural_key AS natural_key,
       coalesce(n.display_text_hi, n.display_text) AS display_text,
       labels(n)[0] AS label,
       coalesce(n.is_stub, false) AS is_stub
"""
    async with driver.session(database=database) as session:
        result = await session.run(cypher, nk=topic_nk)
        records = await result.data()

    return [
        {
            "natural_key": r["natural_key"],
            "display_text": r.get("display_text"),
            "label": r.get("label") or "Topic",
            "is_stub": bool(r.get("is_stub", False)),
        }
        for r in records
        if r["natural_key"]
    ]


async def get_topic_keywords(
    driver: AsyncDriver,
    *,
    topic_nk: str,
    exclude_stubs: bool = True,
    database: str = "jainkb",
) -> list[dict]:
    stub_clause = "AND NOT coalesce(k.is_stub, false)" if exclude_stubs else ""

    cypher = f"""
MATCH (t:Topic {{natural_key: $nk}})-[:MENTIONS_KEYWORD]->(k:Keyword)
WHERE true {stub_clause}
RETURN k.natural_key AS natural_key, k.display_text AS display_text,
       'MENTIONS_KEYWORD' AS edge_type, coalesce(k.is_stub, false) AS is_stub
"""
    async with driver.session(database=database) as session:
        result = await session.run(cypher, nk=topic_nk)
        records = await result.data()

    return [
        {
            "natural_key": r["natural_key"],
            "display_text": r.get("display_text"),
            "edge_type": r["edge_type"],
            "is_stub": bool(r.get("is_stub", False)),
        }
        for r in records
        if r["natural_key"]
    ]


async def get_graph_node_count(
    driver: AsyncDriver,
    *,
    database: str = "jainkb",
) -> int:
    async with driver.session(database=database) as session:
        result = await session.run("MATCH (n) RETURN count(n) AS cnt")
        record = await result.single()
        return int(record["cnt"]) if record else 0


async def get_shortest_path(
    driver: AsyncDriver,
    *,
    from_nk: str,
    to_nk: str,
    database: str = "jainkb",
) -> list[str] | None:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH p = shortestPath((a:Topic {natural_key: $from})-[*..6]-(b:Topic {natural_key: $to}))
            RETURN [n IN nodes(p) | coalesce(n.natural_key, '')] AS node_keys,
                   length(p) AS path_length
            """,
            **{"from": from_nk, "to": to_nk},
        )
        record = await result.single()
        if record:
            return record["node_keys"]
    return None
