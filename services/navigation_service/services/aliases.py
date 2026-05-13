"""Alias CRUD: writes to Postgres first, then syncs Neo4j ALIAS_OF edge.

Postgres commit happens before Neo4j write per spec constraint. If Neo4j
fails, the Postgres row stays; a retry of the same POST is idempotent
(Neo4j MERGE is used).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from neo4j import AsyncDriver

from jain_kb_common.db.postgres.keywords import Keyword, KeywordAlias


async def add_alias(
    session: AsyncSession,
    driver: AsyncDriver,
    *,
    keyword_id: uuid.UUID,
    alias_text: str,
    source: str,
    database: str = "jainkb",
) -> KeywordAlias:
    # Fetch keyword to get natural_key for Neo4j
    kw = await session.get(Keyword, keyword_id)
    if kw is None:
        raise KeyError(f"Keyword {keyword_id!s} not found")

    # Check if alias already exists (idempotent)
    existing = await session.execute(
        select(KeywordAlias).where(
            KeywordAlias.keyword_id == keyword_id,
            KeywordAlias.alias_text == alias_text,
        )
    )
    alias = existing.scalar_one_or_none()

    if alias is None:
        alias = KeywordAlias(
            keyword_id=keyword_id,
            alias_text=alias_text,
            source=source,
        )
        session.add(alias)
        await session.flush()
        await session.refresh(alias)

    # Commit Postgres first
    await session.commit()

    # Then write Neo4j ALIAS_OF edge (idempotent MERGE)
    async with driver.session(database=database) as neo4j_session:
        await neo4j_session.run(
            """
            MERGE (a:Alias {alias_text: $alias_text})
            SET a.pg_id = $pg_id,
                a.source = $source,
                a.created_at = coalesce(a.created_at, datetime())
            WITH a
            MATCH (k:Keyword {natural_key: $nk})
            MERGE (a)-[r:ALIAS_OF]->(k)
            SET r.source = $source
            """,
            alias_text=alias_text,
            pg_id=str(alias.id),
            source=source,
            nk=kw.natural_key,
        )

    return alias


async def remove_alias(
    session: AsyncSession,
    driver: AsyncDriver,
    *,
    keyword_id: uuid.UUID,
    alias_id: uuid.UUID,
    database: str = "jainkb",
) -> None:
    kw = await session.get(Keyword, keyword_id)
    if kw is None:
        raise KeyError(f"Keyword {keyword_id!s} not found")

    alias = await session.get(KeywordAlias, alias_id)
    if alias is None or alias.keyword_id != keyword_id:
        raise KeyError(f"Alias {alias_id!s} not found for keyword {keyword_id!s}")

    alias_text = alias.alias_text

    # Delete from Postgres
    await session.delete(alias)
    await session.commit()

    # Remove Alias node from Neo4j: detach ALIAS_OF edge; delete node only if no remaining edges
    async with driver.session(database=database) as neo4j_session:
        await neo4j_session.run(
            """
            MATCH (a:Alias {alias_text: $alias_text})-[r:ALIAS_OF]->(k:Keyword {natural_key: $nk})
            DELETE r
            WITH a
            WHERE NOT (a)--()
            DELETE a
            """,
            alias_text=alias_text,
            nk=kw.natural_key,
        )
