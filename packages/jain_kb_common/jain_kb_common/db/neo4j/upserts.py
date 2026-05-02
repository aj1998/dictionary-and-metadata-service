from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver


async def sync_keyword(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    display_text: str,
    source_url: str | None = None,
    aliases: list[dict[str, Any]] | None = None,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (k:Keyword {natural_key: $nk})
            SET k.pg_id = $pg_id,
                k.display_text = $display,
                k.source_url = $url,
                k.updated_at = datetime(),
                k.created_at = coalesce(k.created_at, datetime())
            """,
            nk=natural_key,
            pg_id=pg_id,
            display=display_text,
            url=source_url,
        )

        for alias in aliases or []:
            await session.run(
                """
                MERGE (a:Alias {alias_text: $alias})
                SET a.pg_id = $alias_pg_id,
                    a.source = $src,
                    a.created_at = coalesce(a.created_at, datetime())
                WITH a
                MATCH (k:Keyword {natural_key: $nk})
                MERGE (a)-[r:ALIAS_OF]->(k)
                SET r.source = $src
                """,
                alias=alias["alias_text"],
                alias_pg_id=alias["pg_id"],
                src=alias["source"],
                nk=natural_key,
            )


async def sync_topic(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    display_text_hi: str,
    source: str,
    parent_keyword_natural_key: str | None = None,
    mentioned_keyword_natural_keys: list[str] | None = None,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (t:Topic {natural_key: $nk})
            SET t.pg_id = $pg_id,
                t.display_text_hi = $display,
                t.source = $source,
                t.parent_keyword_natural_key = $parent,
                t.updated_at = datetime(),
                t.created_at = coalesce(t.created_at, datetime())
            """,
            nk=natural_key,
            pg_id=pg_id,
            display=display_text_hi,
            source=source,
            parent=parent_keyword_natural_key,
        )

        if parent_keyword_natural_key:
            await session.run(
                """
                MATCH (k:Keyword {natural_key: $kw}), (t:Topic {natural_key: $tp})
                MERGE (k)-[r:HAS_TOPIC]->(t)
                SET r.weight = coalesce(r.weight, 1.0), r.source = $source
                """,
                kw=parent_keyword_natural_key,
                tp=natural_key,
                source=source,
            )

        for kw_nk in mentioned_keyword_natural_keys or []:
            await session.run(
                """
                MATCH (t:Topic {natural_key: $tp}), (k:Keyword {natural_key: $kw})
                MERGE (t)-[r:MENTIONS_KEYWORD]->(k)
                SET r.weight = coalesce(r.weight, 1.0)
                """,
                tp=natural_key,
                kw=kw_nk,
            )


async def sync_shastra(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    title_hi: str,
    author_natural_key: str | None = None,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (s:Shastra {natural_key: $nk})
            SET s.pg_id = $pg_id,
                s.title_hi = $title,
                s.author_natural_key = $author,
                s.updated_at = datetime(),
                s.created_at = coalesce(s.created_at, datetime())
            """,
            nk=natural_key,
            pg_id=pg_id,
            title=title_hi,
            author=author_natural_key,
        )


async def sync_gatha(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    shastra_natural_key: str,
    gatha_number: str,
    heading_hi: str | None = None,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (g:Gatha {natural_key: $nk})
            SET g.pg_id = $pg_id,
                g.shastra_natural_key = $snk,
                g.gatha_number = $num,
                g.heading_hi = $heading,
                g.updated_at = datetime(),
                g.created_at = coalesce(g.created_at, datetime())
            """,
            nk=natural_key,
            pg_id=pg_id,
            snk=shastra_natural_key,
            num=gatha_number,
            heading=heading_hi,
        )

        await session.run(
            """
            MATCH (g:Gatha {natural_key: $gnk}), (s:Shastra {natural_key: $snk})
            MERGE (g)-[:IN_SHASTRA]->(s)
            """,
            gnk=natural_key,
            snk=shastra_natural_key,
        )
