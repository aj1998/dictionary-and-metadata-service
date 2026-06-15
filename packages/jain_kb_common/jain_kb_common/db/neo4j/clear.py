"""Helpers for selectively removing nodes by source."""

from __future__ import annotations

from neo4j import AsyncDriver


async def clear_source(
    driver: AsyncDriver,
    *,
    source: str,
    database: str = "neo4j",
) -> dict[str, int]:
    """Delete/shrink all nodes that carry *source* in their .sources property.

    Nodes exclusively owned by *source* are detach-deleted.
    Nodes co-owned by multiple sources have *source* removed from their array.
    Returns counts of deleted and updated nodes.
    """
    deleted = 0
    updated = 0

    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (n)
            WHERE $src IN n.sources AND size(n.sources) = 1
            DETACH DELETE n
            RETURN count(n) AS cnt
            """,
            src=source,
        )
        record = await result.single()
        if record:
            deleted = record["cnt"]

    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (n)
            WHERE $src IN n.sources AND size(n.sources) > 1
            SET n.sources = [s IN n.sources WHERE s <> $src]
            RETURN count(n) AS cnt
            """,
            src=source,
        )
        record = await result.single()
        if record:
            updated = record["cnt"]

    return {"deleted": deleted, "updated": updated}
