from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

VALID_TYPES = {"keyword", "topic", "gatha", "kalasha"}

_SEARCH_SQL = """
WITH keyword_matches AS (
    SELECT
        'keyword' AS entity_type,
        k.id::text AS id,
        k.natural_key,
        k.display_text,
        similarity(k.display_text, :q) AS score
    FROM keywords k
    WHERE :do_keyword AND (k.display_text % :q OR k.display_text ILIKE :ilike)
    UNION ALL
    SELECT
        'keyword' AS entity_type,
        k.id::text,
        k.natural_key,
        k.display_text,
        similarity(a.alias_text, :q) AS score
    FROM keyword_aliases a
    JOIN keywords k ON k.id = a.keyword_id
    WHERE :do_keyword AND (a.alias_text % :q OR a.alias_text ILIKE :ilike)
),
topic_matches AS (
    SELECT
        'topic' AS entity_type,
        t.id::text,
        t.natural_key,
        t.display_text::text AS display_text,
        similarity(t.display_text::text, :q) AS score
    FROM topics t
    WHERE :do_topic AND (t.display_text::text % :q OR t.display_text::text ILIKE :ilike)
),
gatha_matches AS (
    SELECT
        'gatha' AS entity_type,
        g.id::text,
        g.natural_key,
        COALESCE(g.heading::text, g.gatha_number) AS display_text,
        similarity(COALESCE(g.heading::text, g.gatha_number), :q) AS score
    FROM gathas g
    WHERE :do_gatha AND (
        g.gatha_number ILIKE :ilike
        OR g.heading::text ILIKE :ilike
    )
),
kalasha_matches AS (
    SELECT
        'kalasha' AS entity_type,
        k.id::text,
        k.natural_key,
        k.kalash_number AS display_text,
        similarity(k.kalash_number, :q) AS score
    FROM kalashas k
    WHERE :do_kalasha AND k.kalash_number ILIKE :ilike
)
SELECT entity_type, id, natural_key, display_text, score
FROM (
    SELECT * FROM keyword_matches
    UNION ALL
    SELECT * FROM topic_matches
    UNION ALL
    SELECT * FROM gatha_matches
    UNION ALL
    SELECT * FROM kalasha_matches
) combined
ORDER BY score DESC, natural_key
LIMIT :lim
"""


async def search(
    session: AsyncSession,
    q: str,
    types: set[str],
    limit: int,
) -> list[dict]:
    rows = await session.execute(
        text(_SEARCH_SQL).bindparams(
            q=q,
            ilike=f"%{q}%",
            lim=limit,
            do_keyword=("keyword" in types),
            do_topic=("topic" in types),
            do_gatha=("gatha" in types),
            do_kalasha=("kalasha" in types),
        )
    )
    results = []
    for r in rows:
        results.append({
            "entity_type": r.entity_type,
            "id": r.id,
            "natural_key": r.natural_key,
            "display_text": r.display_text,
            "score": float(r.score) if r.score is not None else 0.0,
        })
    return results
