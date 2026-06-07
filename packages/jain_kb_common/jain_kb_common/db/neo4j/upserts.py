from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver

_VALID_LABELS = frozenset({
    "Keyword", "Topic", "Gatha", "GathaTeeka", "GathaTeekaBhaavarth",
    "Kalash", "KalashBhaavarth", "Page", "Shastra", "Teeka", "Publication", "Alias", "Table",
})


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
                k.is_stub = false,
                k.stub_source = null,
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
    topic_path: str | None = None,
    is_leaf: bool = True,
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
                t.topic_path = $topic_path,
                t.is_leaf = $is_leaf,
                t.is_stub = false,
                t.stub_source = null,
                t.updated_at = datetime(),
                t.created_at = coalesce(t.created_at, datetime())
            """,
            nk=natural_key,
            pg_id=pg_id,
            display=display_text_hi,
            source=source,
            parent=parent_keyword_natural_key,
            topic_path=topic_path,
            is_leaf=is_leaf,
        )

        for kw_nk in mentioned_keyword_natural_keys or []:
            await session.run(
                """
                MERGE (t:Topic {natural_key: $tp})
                  SET t.is_stub = coalesce(t.is_stub, true),
                      t.created_at = coalesce(t.created_at, datetime())
                MERGE (k:Keyword {natural_key: $kw})
                  SET k.is_stub = coalesce(k.is_stub, true),
                      k.created_at = coalesce(k.created_at, datetime())
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
                s.is_stub = false,
                s.stub_source = null,
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
                t.is_stub = false,
                t.stub_source = null,
                t.updated_at = datetime(),
                t.created_at = coalesce(t.created_at, datetime())
            WITH t
            MATCH (s:Shastra {natural_key: $snk})
            MERGE (s)-[:HAS_TEEKA]->(t)
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
                p.is_stub = false,
                p.stub_source = null,
                p.updated_at = datetime(),
                p.created_at = coalesce(p.created_at, datetime())
            WITH p
            MATCH (t:Teeka {natural_key: $tnk})
            MERGE (t)-[:HAS_PUBLICATION]->(p)
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
                k.is_stub = false,
                k.stub_source = null,
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


async def sync_gatha_teeka(
    driver: AsyncDriver,
    *,
    natural_key: str,
    teeka_natural_key: str,
    gatha_natural_key: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (gt:GathaTeeka {natural_key: $nk})
            SET gt.teeka_natural_key = $tnk,
                gt.gatha_natural_key = $gnk,
                gt.is_stub = false,
                gt.stub_source = null,
                gt.updated_at = datetime(),
                gt.created_at = coalesce(gt.created_at, datetime())
            WITH gt
            MATCH (t:Teeka {natural_key: $tnk})
            MERGE (gt)-[:IN_TEEKA]->(t)
            """,
            nk=natural_key,
            tnk=teeka_natural_key,
            gnk=gatha_natural_key,
        )


async def sync_gatha_teeka_bhaavarth(
    driver: AsyncDriver,
    *,
    natural_key: str,
    publication_natural_key: str,
    gatha_natural_key: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (gtb:GathaTeekaBhaavarth {natural_key: $nk})
            SET gtb.publication_natural_key = $pnk,
                gtb.gatha_natural_key = $gnk,
                gtb.is_stub = false,
                gtb.stub_source = null,
                gtb.updated_at = datetime(),
                gtb.created_at = coalesce(gtb.created_at, datetime())
            WITH gtb
            MATCH (p:Publication {natural_key: $pnk})
            MERGE (gtb)-[:IN_PUBLICATION]->(p)
            """,
            nk=natural_key,
            pnk=publication_natural_key,
            gnk=gatha_natural_key,
        )


async def sync_kalash_bhaavarth(
    driver: AsyncDriver,
    *,
    natural_key: str,
    publication_natural_key: str,
    kalash_number: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (kb:KalashBhaavarth {natural_key: $nk})
            SET kb.publication_natural_key = $pnk,
                kb.kalash_number = $num,
                kb.is_stub = false,
                kb.stub_source = null,
                kb.updated_at = datetime(),
                kb.created_at = coalesce(kb.created_at, datetime())
            WITH kb
            MATCH (p:Publication {natural_key: $pnk})
            MERGE (kb)-[:IN_PUBLICATION]->(p)
            """,
            nk=natural_key,
            pnk=publication_natural_key,
            num=kalash_number,
        )


async def sync_table(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    source: str,
    parent_natural_key: str,
    parent_kind: str,
    seq: int,
    caption_hi: str | None = None,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (t:Table {natural_key: $nk})
            SET t.pg_id = $pg_id,
                t.source = $source,
                t.parent_natural_key = $parent_nk,
                t.parent_kind = $parent_kind,
                t.seq = $seq,
                t.caption_hi = $caption_hi,
                t.is_stub = false,
                t.stub_source = null,
                t.updated_at = datetime(),
                t.created_at = coalesce(t.created_at, datetime())
            """,
            nk=natural_key,
            pg_id=pg_id,
            source=source,
            parent_nk=parent_natural_key,
            parent_kind=parent_kind,
            seq=seq,
            caption_hi=caption_hi,
        )


async def sync_contains_table_edge(
    driver: AsyncDriver,
    *,
    parent_label: str,
    parent_nk: str,
    table_nk: str,
    source: str,
    database: str = "jainkb",
) -> None:
    if parent_label not in _VALID_LABELS:
        raise ValueError(f"Unknown parent_label: {parent_label!r}")
    async with driver.session(database=database) as session:
        await session.run(
            f"""
            MERGE (parent:{parent_label} {{natural_key: $pnk}})
              SET parent.is_stub = coalesce(parent.is_stub, true),
                  parent.created_at = coalesce(parent.created_at, datetime())
            MERGE (t:Table {{natural_key: $tnk}})
              SET t.is_stub = coalesce(t.is_stub, true),
                  t.created_at = coalesce(t.created_at, datetime())
            MERGE (parent)-[r:CONTAINS_TABLE]->(t)
            SET r.weight = coalesce(r.weight, 1.0), r.source = $source
            """,
            pnk=parent_nk,
            tnk=table_nk,
            source=source,
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
                g.is_stub = false,
                g.stub_source = null,
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


async def sync_has_topic_edge(
    driver: AsyncDriver,
    *,
    keyword_nk: str,
    topic_nk: str,
    source: str = "jainkosh",
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (k:Keyword {natural_key: $kw})
              SET k.is_stub = coalesce(k.is_stub, true),
                  k.stub_source = CASE WHEN k.is_stub = false THEN k.stub_source ELSE coalesce(k.stub_source, 'jainkosh_ingestion') END,
                  k.created_at = coalesce(k.created_at, datetime())
            MERGE (t:Topic {natural_key: $tp})
              SET t.is_stub = coalesce(t.is_stub, true),
                  t.stub_source = CASE WHEN t.is_stub = false THEN t.stub_source ELSE coalesce(t.stub_source, 'jainkosh_ingestion') END,
                  t.created_at = coalesce(t.created_at, datetime())
            MERGE (k)-[r:HAS_TOPIC]->(t)
            SET r.weight = coalesce(r.weight, 1.0), r.source = $source
            """,
            kw=keyword_nk,
            tp=topic_nk,
            source=source,
        )


async def sync_part_of_edge(
    driver: AsyncDriver,
    *,
    child_nk: str,
    parent_nk: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (child:Topic {natural_key: $c})
              SET child.is_stub = coalesce(child.is_stub, true),
                  child.stub_source = CASE WHEN child.is_stub = false THEN child.stub_source ELSE coalesce(child.stub_source, 'jainkosh_ingestion') END,
                  child.created_at = coalesce(child.created_at, datetime())
            MERGE (parent:Topic {natural_key: $p})
              SET parent.is_stub = coalesce(parent.is_stub, true),
                  parent.stub_source = CASE WHEN parent.is_stub = false THEN parent.stub_source ELSE coalesce(parent.stub_source, 'jainkosh_ingestion') END,
                  parent.created_at = coalesce(parent.created_at, datetime())
            MERGE (child)-[r:PART_OF]->(parent)
            SET r.weight = coalesce(r.weight, 1.0), r.source = 'jainkosh'
            """,
            c=child_nk,
            p=parent_nk,
        )


async def sync_related_to_edge(
    driver: AsyncDriver,
    *,
    source_nk: str,
    target_nk: str,
    source_label: str = "Topic",
    target_label: str = "Topic",
    weight: float = 1.0,
    database: str = "jainkb",
) -> None:
    if source_label not in _VALID_LABELS:
        raise ValueError(f"Unknown source_label: {source_label!r}")
    if target_label not in _VALID_LABELS:
        raise ValueError(f"Unknown target_label: {target_label!r}")
    async with driver.session(database=database) as session:
        await session.run(
            f"""
            MERGE (src:{source_label} {{natural_key: $s}})
              SET src.is_stub = coalesce(src.is_stub, true),
                  src.stub_source = CASE WHEN src.is_stub = false THEN src.stub_source ELSE coalesce(src.stub_source, 'jainkosh_ingestion') END,
                  src.created_at = coalesce(src.created_at, datetime())
            MERGE (tgt:{target_label} {{natural_key: $t}})
              SET tgt.is_stub = coalesce(tgt.is_stub, true),
                  tgt.stub_source = CASE WHEN tgt.is_stub = false THEN tgt.stub_source ELSE coalesce(tgt.stub_source, 'jainkosh_ingestion') END,
                  tgt.created_at = coalesce(tgt.created_at, datetime())
            MERGE (src)-[r:RELATED_TO]->(tgt)
            SET r.weight = coalesce(r.weight, $w), r.source = 'jainkosh'
            """,
            s=source_nk,
            t=target_nk,
            w=weight,
        )
