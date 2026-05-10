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


async def sync_teeka(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    shastra_natural_key: str,
    teekakar_natural_key: str | None = None,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (t:Teeka {natural_key: $nk})
            SET t.pg_id = $pg_id,
                t.shastra_natural_key = $snk,
                t.teekakar_natural_key = $teekakar,
                t.updated_at = datetime(),
                t.created_at = coalesce(t.created_at, datetime())
            WITH t
            MATCH (s:Shastra {natural_key: $snk})
            MERGE (t)-[:IN_SHASTRA]->(s)
            """,
            nk=natural_key,
            pg_id=pg_id,
            snk=shastra_natural_key,
            teekakar=teekakar_natural_key,
        )


async def sync_publication(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    teeka_natural_key: str,
    publisher_id: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (p:Publication {natural_key: $nk})
            SET p.pg_id = $pg_id,
                p.teeka_natural_key = $tnk,
                p.publisher_id = $pub_id,
                p.updated_at = datetime(),
                p.created_at = coalesce(p.created_at, datetime())
            WITH p
            MATCH (t:Teeka {natural_key: $tnk})
            MERGE (p)-[:IN_TEEKA]->(t)
            """,
            nk=natural_key,
            pg_id=pg_id,
            tnk=teeka_natural_key,
            pub_id=publisher_id,
        )


async def sync_kalash(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    teeka_natural_key: str,
    kalash_number: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (k:Kalash {natural_key: $nk})
            SET k.pg_id = $pg_id,
                k.teeka_natural_key = $tnk,
                k.kalash_number = $num,
                k.updated_at = datetime(),
                k.created_at = coalesce(k.created_at, datetime())
            WITH k
            MATCH (t:Teeka {natural_key: $tnk})
            MERGE (k)-[:IN_TEEKA]->(t)
            """,
            nk=natural_key,
            pg_id=pg_id,
            tnk=teeka_natural_key,
            num=kalash_number,
        )


async def ensure_lazy_node(
    session,
    label: str,
    natural_key: str,
    props: dict,
    parent_edge_type: str,
    parent_label: str,
    parent_natural_key: str,
) -> None:
    await session.run(
        f"""
        MERGE (n:{label} {{natural_key: $nk}})
        SET n += $props,
            n.updated_at = datetime(),
            n.created_at = coalesce(n.created_at, datetime())
        WITH n
        MERGE (parent:{parent_label} {{natural_key: $parent_nk}})
        MERGE (n)-[:{parent_edge_type}]->(parent)
        """,
        nk=natural_key,
        props=props,
        parent_nk=parent_natural_key,
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
