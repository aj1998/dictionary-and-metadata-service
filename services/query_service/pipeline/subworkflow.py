from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher: topics mentioned in a specific gatha
# ---------------------------------------------------------------------------
_TOPICS_IN_GATHA_CYPHER = """
MATCH (s:Shastra {natural_key: $shastra_nk})<-[:IN_SHASTRA]-(g:Gatha {number: $gatha_n})
MATCH (g)-[:MENTIONS_TOPIC]->(t:Topic)
RETURN t.natural_key AS topic_nk,
       t.display_text_hi AS display_text_hi,
       t.is_leaf AS is_leaf,
       count(*) AS mention_count
ORDER BY mention_count DESC, t.natural_key
LIMIT $limit
"""

# ---------------------------------------------------------------------------
# Cypher: topics mentioned across a whole shastra (all gathas)
# ---------------------------------------------------------------------------
_TOPICS_IN_SHASTRA_CYPHER = """
MATCH (s:Shastra {natural_key: $shastra_nk})<-[:IN_SHASTRA]-(g:Gatha)
MATCH (g)-[:MENTIONS_TOPIC]->(t:Topic)
RETURN t.natural_key AS topic_nk,
       t.display_text_hi AS display_text_hi,
       t.is_leaf AS is_leaf,
       count(*) AS mention_count
ORDER BY mention_count DESC, t.natural_key
LIMIT $limit
"""

# ---------------------------------------------------------------------------
# Cypher: shastras (+ gatha refs) that mention a topic
# ---------------------------------------------------------------------------
_SHASTRAS_FOR_TOPIC_CYPHER = """
MATCH (t:Topic {natural_key: $topic_nk})<-[:MENTIONS_TOPIC]-(g:Gatha)-[:IN_SHASTRA]->(s:Shastra)
WITH s,
     collect({number: g.number, page_number: g.page_number}) AS all_gathas,
     count(g) AS total_mentions
ORDER BY total_mentions DESC
LIMIT $limit_shastras
RETURN s.natural_key AS shastra_nk,
       s.name_hi     AS name_hi,
       total_mentions,
       all_gathas[0..$limit_gpp] AS gathas
"""


@dataclass
class TopicMentionRow:
    topic_nk: str
    display_text_hi: str
    is_leaf: bool
    mention_count: int


@dataclass
class ShastraTopicRow:
    shastra_nk: str
    name_hi: str
    total_mentions: int
    gathas: list[dict] = field(default_factory=list)


async def fetch_topics_in_shastra(
    driver: object,
    shastra_nk: str,
    gatha_number: int | None,
    limit: int,
    database: str,
) -> list[TopicMentionRow]:
    """Run Neo4j Cypher to get topics mentioned in a shastra (or a single gatha)."""
    if gatha_number is not None:
        cypher = _TOPICS_IN_GATHA_CYPHER
        params: dict = {"shastra_nk": shastra_nk, "gatha_n": gatha_number, "limit": limit}
    else:
        cypher = _TOPICS_IN_SHASTRA_CYPHER
        params = {"shastra_nk": shastra_nk, "limit": limit}

    rows: list[TopicMentionRow] = []
    async with driver.session(database=database) as session:  # type: ignore[attr-defined]
        result = await session.run(cypher, **params)
        data = await result.data()
        for row in data:
            rows.append(TopicMentionRow(
                topic_nk=row["topic_nk"],
                display_text_hi=row.get("display_text_hi") or "",
                is_leaf=bool(row.get("is_leaf", True)),
                mention_count=int(row.get("mention_count") or 0),
            ))

    logger.debug(
        "fetch_topics_in_shastra shastra=%s gatha=%s limit=%d → %d rows",
        shastra_nk, gatha_number, limit, len(rows),
    )
    return rows


async def fetch_shastras_for_topic(
    driver: object,
    topic_nk: str,
    limit_shastras: int,
    limit_gathas_per_shastra: int,
    database: str,
) -> list[ShastraTopicRow]:
    """Run Neo4j Cypher to find shastras (+ gatha refs) that mention a topic."""
    rows: list[ShastraTopicRow] = []
    async with driver.session(database=database) as session:  # type: ignore[attr-defined]
        result = await session.run(
            _SHASTRAS_FOR_TOPIC_CYPHER,
            topic_nk=topic_nk,
            limit_shastras=limit_shastras,
            limit_gpp=limit_gathas_per_shastra,
        )
        data = await result.data()
        for row in data:
            rows.append(ShastraTopicRow(
                shastra_nk=row.get("shastra_nk") or "",
                name_hi=row.get("name_hi") or "",
                total_mentions=int(row.get("total_mentions") or 0),
                gathas=list(row.get("gathas") or []),
            ))

    logger.debug(
        "fetch_shastras_for_topic topic=%s limit_s=%d limit_g=%d → %d rows",
        topic_nk, limit_shastras, limit_gathas_per_shastra, len(rows),
    )
    return rows
