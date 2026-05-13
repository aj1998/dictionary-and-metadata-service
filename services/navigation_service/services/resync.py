"""Graph resync service: rebuilds Neo4j graph from Postgres source of truth.

In v1, all scopes run synchronously in the request thread. 'full' scope
wipes all nodes first (requires X-Confirm: resync-full header enforced at
the router layer).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from neo4j import AsyncDriver

from jain_kb_common.db.postgres.keywords import Keyword, KeywordAlias
from jain_kb_common.db.postgres.topics import Topic
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.neo4j.upserts import (
    sync_keyword,
    sync_topic,
    sync_shastra,
    sync_gatha,
)


def _extract_display_text_hi(display_text: list | dict | str | None) -> str:
    """Extract Hindi display text from the multilingual JSONB field."""
    if not display_text:
        return ""
    if isinstance(display_text, str):
        return display_text
    if isinstance(display_text, list):
        for item in display_text:
            if isinstance(item, dict) and item.get("lang") == "hi":
                return item.get("text", "")
        # fallback: first item
        if display_text and isinstance(display_text[0], dict):
            return display_text[0].get("text", "")
    if isinstance(display_text, dict):
        return display_text.get("text", display_text.get("hi", ""))
    return str(display_text)


async def _resync_keywords(
    session: AsyncSession,
    driver: AsyncDriver,
    database: str,
) -> None:
    keywords = (await session.execute(select(Keyword))).scalars().all()
    for kw in keywords:
        aliases_rows = (
            await session.execute(
                select(KeywordAlias).where(KeywordAlias.keyword_id == kw.id)
            )
        ).scalars().all()
        aliases = [
            {"alias_text": a.alias_text, "pg_id": str(a.id), "source": a.source}
            for a in aliases_rows
        ]
        await sync_keyword(
            driver,
            natural_key=kw.natural_key,
            pg_id=str(kw.id),
            display_text=kw.display_text,
            source_url=kw.source_url,
            aliases=aliases,
            database=database,
        )


async def _resync_topics(
    session: AsyncSession,
    driver: AsyncDriver,
    database: str,
) -> None:
    topics = (await session.execute(select(Topic))).scalars().all()
    for t in topics:
        display_hi = _extract_display_text_hi(t.display_text)
        # Resolve parent keyword natural_key if set
        parent_kw_nk: str | None = None
        if t.parent_keyword_id:
            kw = await session.get(Keyword, t.parent_keyword_id)
            if kw:
                parent_kw_nk = kw.natural_key

        await sync_topic(
            driver,
            natural_key=t.natural_key,
            pg_id=str(t.id),
            display_text_hi=display_hi,
            source=t.source.value if hasattr(t.source, "value") else str(t.source),
            parent_keyword_natural_key=parent_kw_nk,
            topic_path=t.topic_path,
            is_leaf=t.is_leaf,
            database=database,
        )


async def _resync_shastras(
    session: AsyncSession,
    driver: AsyncDriver,
    database: str,
) -> None:
    shastras = (await session.execute(select(Shastra))).scalars().all()
    for s in shastras:
        title_hi = _extract_display_text_hi(s.title)
        await sync_shastra(
            driver,
            natural_key=s.natural_key,
            pg_id=str(s.id),
            title_hi=title_hi,
            database=database,
        )

    gathas = (await session.execute(select(Gatha))).scalars().all()
    for g in gathas:
        shastra = await session.get(Shastra, g.shastra_id)
        shastra_nk = shastra.natural_key if shastra else ""
        await sync_gatha(
            driver,
            natural_key=g.natural_key,
            pg_id=str(g.id),
            shastra_natural_key=shastra_nk,
            gatha_number=g.gatha_number,
            database=database,
        )


async def _wipe_all(driver: AsyncDriver, database: str) -> None:
    async with driver.session(database=database) as session:
        await session.run("MATCH (n) DETACH DELETE n")


async def run_resync(
    session: AsyncSession,
    driver: AsyncDriver,
    scope: str,
    database: str = "jainkb",
) -> None:
    if scope == "full":
        await _wipe_all(driver, database)
        await _resync_keywords(session, driver, database)
        await _resync_topics(session, driver, database)
        await _resync_shastras(session, driver, database)
    elif scope == "keyword":
        await _resync_keywords(session, driver, database)
    elif scope == "topic":
        await _resync_topics(session, driver, database)
    elif scope == "shastra":
        await _resync_shastras(session, driver, database)
    else:
        raise ValueError(f"Unknown scope: {scope!r}")
