from __future__ import annotations

from neo4j import AsyncDriver


async def resolve_token(
    driver: AsyncDriver,
    *,
    token: str,
    database: str = "jainkb",
) -> dict | None:
    async with driver.session(database=database) as session:
        # Try direct keyword match first
        result = await session.run(
            "MATCH (k:Keyword {natural_key: $token}) RETURN k.natural_key AS keyword_nk, k.pg_id AS keyword_pg_id",
            token=token,
        )
        record = await result.single()
        if record:
            return {"keyword_nk": record["keyword_nk"], "keyword_pg_id": record["keyword_pg_id"]}

        # Else try via alias
        result = await session.run(
            "MATCH (a:Alias {alias_text: $token})-[:ALIAS_OF]->(k:Keyword) RETURN k.natural_key AS keyword_nk, k.pg_id AS keyword_pg_id",
            token=token,
        )
        record = await result.single()
        if record:
            return {"keyword_nk": record["keyword_nk"], "keyword_pg_id": record["keyword_pg_id"]}

    return None


async def traverse_topics(
    driver: AsyncDriver,
    *,
    seed_keyword_nks: list[str],
    top_k: int = 10,
    database: str = "jainkb",
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            UNWIND $seed_keyword_nks AS kw
            MATCH (k:Keyword {natural_key: kw})
            MATCH (k)-[r:HAS_TOPIC|MENTIONS_KEYWORD|RELATED_TO|IS_A|PART_OF*1..2]-(t:Topic)
            WITH t, count(DISTINCT k) AS overlap, sum(coalesce(1.0)) AS weight_sum
            RETURN t.natural_key AS topic_nk,
                   t.display_text_hi AS heading,
                   t.pg_id AS topic_pg_id,
                   overlap,
                   weight_sum
            ORDER BY overlap DESC, weight_sum DESC
            LIMIT $top_k
            """,
            seed_keyword_nks=seed_keyword_nks,
            top_k=top_k,
        )
        records = await result.data()
    return records


async def shortest_path(
    driver: AsyncDriver,
    *,
    from_nk: str,
    to_nk: str,
    database: str = "jainkb",
) -> list | None:
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
