"""Idempotent apply layer: NJ would_write envelope → Postgres + Mongo + Neo4j."""

from __future__ import annotations

import unicodedata
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.upserts import (
    stable_id,
    upsert_gatha_hindi_chhand,
    upsert_gatha_prakrit,
    upsert_gatha_sanskrit,
    upsert_gatha_teeka_bhaavarth_hindi,
    upsert_gatha_teeka_sanskrit,
    upsert_kalash_hindi,
    upsert_kalash_sanskrit,
    upsert_kalash_word_meanings,
    upsert_teeka_gatha_mapping,
)
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.teekas import Teeka
from jain_kb_common.db.postgres.upserts import (
    upsert_author,
    upsert_gatha,
    upsert_kalash,
    upsert_publication,
    upsert_shastra,
    upsert_teeka,
    upsert_teeka_chapter,
)
from jain_kb_common.db.neo4j.upserts import (
    sync_gatha,
    sync_gatha_teeka,
    sync_gatha_teeka_bhaavarth,
    sync_kalash,
    sync_kalash_bhaavarth,
    sync_publication,
    sync_shastra,
    sync_teeka,
)
from jain_kb_common.db.neo4j.stubs import sync_stub_node


def _nfc(v: str) -> str:
    return unicodedata.normalize("NFC", v)


def _nfc_deep(v: Any) -> Any:
    if isinstance(v, str):
        return _nfc(v)
    if isinstance(v, list):
        return [_nfc_deep(i) for i in v]
    if isinstance(v, dict):
        return {k: _nfc_deep(val) for k, val in v.items()}
    return v


async def _resolve_author_id(session: AsyncSession, natural_key: str) -> uuid.UUID | None:
    res = await session.execute(select(Author.id).where(Author.natural_key == natural_key))
    return res.scalar_one_or_none()


async def _resolve_shastra_id(session: AsyncSession, natural_key: str) -> uuid.UUID | None:
    res = await session.execute(select(Shastra.id).where(Shastra.natural_key == natural_key))
    return res.scalar_one_or_none()


async def _resolve_teeka_id(session: AsyncSession, natural_key: str) -> uuid.UUID | None:
    res = await session.execute(select(Teeka.id).where(Teeka.natural_key == natural_key))
    return res.scalar_one_or_none()


async def _resolve_gatha_id(session: AsyncSession, natural_key: str) -> uuid.UUID | None:
    res = await session.execute(select(Gatha.id).where(Gatha.natural_key == natural_key))
    return res.scalar_one_or_none()


async def apply_nj_shastra_payload(
    *,
    envelope: dict,
    pg_session: AsyncSession,
    mongo_db,
    neo4j_driver,
    ingestion_run_id: uuid.UUID | None = None,
    neo4j_database: str = "jainkb",
) -> None:
    """
    Idempotently apply one NJ shastra would_write envelope to Postgres, Mongo, Neo4j.
    Safe to call twice with the same envelope (no net DB changes on second call).
    """
    envelope = _nfc_deep(envelope)
    ww = envelope["would_write"]
    pg = ww["postgres"]
    mongo = ww["mongo"]
    neo = ww["neo4j"]
    run_id_str = str(ingestion_run_id) if ingestion_run_id else None

    # UUID resolution caches: natural_key → uuid
    author_ids: dict[str, uuid.UUID] = {}
    shastra_ids: dict[str, uuid.UUID] = {}
    teeka_ids: dict[str, uuid.UUID] = {}
    gatha_ids: dict[str, uuid.UUID] = {}

    # --- Postgres: metadata entities ---
    for row in pg.get("authors", []):
        aid = await upsert_author(
            pg_session,
            natural_key=row["natural_key"],
            display_name=row.get("display_name", []),
            kind=row.get("kind", "acharya"),
        )
        author_ids[row["natural_key"]] = aid

    for row in pg.get("shastras", []):
        author_nk = row.get("author_natural_key", "")
        author_id = author_ids.get(author_nk) or await _resolve_author_id(pg_session, author_nk)
        if author_id is None:
            raise ValueError(f"Author not found: {author_nk}")
        sid = await upsert_shastra(
            pg_session,
            natural_key=row["natural_key"],
            title=row.get("title", []),
            author_id=author_id,
        )
        shastra_ids[row["natural_key"]] = sid

    for row in pg.get("teekas", []):
        shastra_nk = row.get("shastra_natural_key", "")
        shastra_id = shastra_ids.get(shastra_nk) or await _resolve_shastra_id(pg_session, shastra_nk)
        if shastra_id is None:
            raise ValueError(f"Shastra not found: {shastra_nk}")
        teekakar_nk = row.get("teekakar_natural_key", "")
        teekakar_id = author_ids.get(teekakar_nk) or await _resolve_author_id(pg_session, teekakar_nk)
        tid = await upsert_teeka(
            pg_session,
            natural_key=row["natural_key"],
            shastra_id=shastra_id,
            teekakar_id=teekakar_id,
            role=row.get("role"),
        )
        teeka_ids[row["natural_key"]] = tid

    for row in pg.get("publications", []):
        teeka_nk = row.get("teeka_natural_key", "")
        teeka_id = teeka_ids.get(teeka_nk) or await _resolve_teeka_id(pg_session, teeka_nk)
        if teeka_id is None:
            raise ValueError(f"Teeka not found: {teeka_nk}")
        await upsert_publication(
            pg_session,
            natural_key=row["natural_key"],
            teeka_id=teeka_id,
            publisher_id=row.get("publisher_id", ""),
        )

    # --- Gathas: Postgres + Mongo + Neo4j ---
    shastra_nk_default = pg.get("shastras", [{}])[0].get("natural_key", "")

    for row in pg.get("gathas", []):
        shastra_nk = row.get("shastra_natural_key", shastra_nk_default)
        shastra_id = shastra_ids.get(shastra_nk) or await _resolve_shastra_id(pg_session, shastra_nk)
        if shastra_id is None:
            raise ValueError(f"Shastra not found for gatha: {shastra_nk}")
        gid = await upsert_gatha(
            pg_session,
            natural_key=row["natural_key"],
            shastra_id=shastra_id,
            gatha_number=row.get("gatha_number", ""),
            adhikaar=row.get("adhikaar"),
            heading=row.get("heading"),
        )
        gatha_ids[row["natural_key"]] = gid

    # Mongo: all non-kalash gatha collections
    for coll_name in (
        "gatha_prakrit", "gatha_sanskrit", "gatha_hindi_chhand",
        "teeka_gatha_mapping", "gatha_teeka_sanskrit", "gatha_teeka_bhaavarth_hindi",
    ):
        for doc in mongo.get(coll_name, []):
            d = _make_mongo_doc(doc, run_id_str)
            nk = doc["natural_key"]
            if coll_name == "gatha_prakrit":
                await upsert_gatha_prakrit(mongo_db, natural_key=nk, doc=d)
            elif coll_name == "gatha_sanskrit":
                await upsert_gatha_sanskrit(mongo_db, natural_key=nk, doc=d)
            elif coll_name == "gatha_hindi_chhand":
                await upsert_gatha_hindi_chhand(mongo_db, natural_key=nk, doc=d)
            elif coll_name == "teeka_gatha_mapping":
                await upsert_teeka_gatha_mapping(mongo_db, natural_key=nk, doc=d)
            elif coll_name == "gatha_teeka_sanskrit":
                await upsert_gatha_teeka_sanskrit(mongo_db, natural_key=nk, doc=d)
            elif coll_name == "gatha_teeka_bhaavarth_hindi":
                await upsert_gatha_teeka_bhaavarth_hindi(mongo_db, natural_key=nk, doc=d)

    # --- Kalashes: Postgres + Mongo + Neo4j ---
    # Index kalash mongo docs by kalash_natural_key for cross-referencing
    kalash_san_by_nk: dict[str, dict] = {}
    kalash_hi_by_nk: dict[str, dict] = {}
    kalash_wm_by_nk: dict[str, dict] = {}

    for doc in mongo.get("kalash_sanskrit", []):
        nk = doc["kalash_natural_key"]
        d = _make_mongo_doc(doc, run_id_str)
        await upsert_kalash_sanskrit(mongo_db, natural_key=doc["natural_key"], doc=d)
        kalash_san_by_nk[nk] = doc

    for doc in mongo.get("kalash_hindi", []):
        nk = doc["kalash_natural_key"]
        d = _make_mongo_doc(doc, run_id_str)
        await upsert_kalash_hindi(mongo_db, natural_key=doc["natural_key"], doc=d)
        kalash_hi_by_nk[nk] = doc

    for doc in mongo.get("kalash_word_meanings", []):
        nk = doc["kalash_natural_key"]
        d = _make_mongo_doc(doc, run_id_str)
        await upsert_kalash_word_meanings(
            mongo_db,
            natural_key=doc["natural_key"],
            kalash_natural_key=nk,
            teeka_natural_key=doc.get("teeka_natural_key", ""),
            kalash_number=doc.get("kalash_number", ""),
            entries=doc.get("entries", []),
            ingestion_run_id=run_id_str,
        )
        kalash_wm_by_nk[nk] = doc

    for row in pg.get("kalashas", []):
        kalash_nk = row["natural_key"]
        teeka_nk = row.get("teeka_natural_key", "")
        teeka_id = teeka_ids.get(teeka_nk) or await _resolve_teeka_id(pg_session, teeka_nk)
        if teeka_id is None:
            raise ValueError(f"Teeka not found for kalash: {teeka_nk}")

        gatha_nk = row.get("gatha_natural_key")
        gatha_id = None
        if gatha_nk:
            gatha_id = gatha_ids.get(gatha_nk) or await _resolve_gatha_id(pg_session, gatha_nk)

        san_doc = kalash_san_by_nk.get(kalash_nk)
        hi_doc = kalash_hi_by_nk.get(kalash_nk)

        kid = await upsert_kalash(
            pg_session,
            natural_key=kalash_nk,
            teeka_id=teeka_id,
            kalash_number=row.get("kalash_number", ""),
            gatha_id=gatha_id,
            sanskrit_doc_id=str(stable_id(san_doc["natural_key"])) if san_doc else None,
            hindi_doc_id=str(stable_id(hi_doc["natural_key"])) if hi_doc else None,
        )

        await sync_kalash(
            neo4j_driver,
            natural_key=kalash_nk,
            pg_id=str(kid),
            teeka_natural_key=teeka_nk,
            kalash_number=row.get("kalash_number", ""),
            database=neo4j_database,
        )

    # --- Teeka chapters: Postgres only ---
    for row in pg.get("teeka_chapters", []):
        teeka_nk = row.get("teeka_natural_key", "")
        teeka_id = teeka_ids.get(teeka_nk) or await _resolve_teeka_id(pg_session, teeka_nk)
        if teeka_id is None:
            raise ValueError(f"Teeka not found for chapter: {teeka_nk}")

        start_nk = row.get("start_gatha_natural_key", "")
        end_nk = row.get("end_gatha_natural_key")
        start_gid = gatha_ids.get(start_nk) or await _resolve_gatha_id(pg_session, start_nk)
        end_gid = None
        if end_nk:
            end_gid = gatha_ids.get(end_nk) or await _resolve_gatha_id(pg_session, end_nk)

        if start_gid is None:
            raise ValueError(f"Start gatha not found for chapter: {start_nk}")

        await upsert_teeka_chapter(
            pg_session,
            natural_key=row["natural_key"],
            teeka_id=teeka_id,
            chapter_number=row.get("chapter_number", 0),
            name=row.get("name", []),
            start_gatha_id=start_gid,
            end_gatha_id=end_gid,
        )

    await pg_session.commit()

    # --- Neo4j: structural nodes ---
    shastra_row = pg.get("shastras", [{}])[0] if pg.get("shastras") else {}
    if shastra_row:
        shastra_pg_id = str(shastra_ids.get(shastra_row.get("natural_key", ""), ""))
        title_list = shastra_row.get("title", [])
        title_hi = next((t["text"] for t in title_list if t.get("lang") == "hin"), "")
        await sync_shastra(
            neo4j_driver,
            natural_key=shastra_row["natural_key"],
            pg_id=shastra_pg_id,
            title_hi=title_hi,
            author_natural_key=shastra_row.get("author_natural_key"),
            database=neo4j_database,
        )

    for row in pg.get("teekas", []):
        teeka_nk = row["natural_key"]
        await sync_teeka(
            neo4j_driver,
            natural_key=teeka_nk,
            pg_id=str(teeka_ids.get(teeka_nk, "")),
            shastra_natural_key=row.get("shastra_natural_key", ""),
            teekakar_natural_key=row.get("teekakar_natural_key"),
            database=neo4j_database,
        )

    for row in pg.get("publications", []):
        pub_nk = row["natural_key"]
        await sync_publication(
            neo4j_driver,
            natural_key=pub_nk,
            pg_id=str(stable_id(pub_nk)),
            teeka_natural_key=row.get("teeka_natural_key", ""),
            publisher_id=row.get("publisher_id", ""),
            database=neo4j_database,
        )

    for row in pg.get("gathas", []):
        gatha_nk = row["natural_key"]
        gid = gatha_ids.get(gatha_nk)
        heading_list = row.get("heading", [])
        heading_hi = next((t["text"] for t in heading_list if t.get("lang") == "hin"), None)
        await sync_gatha(
            neo4j_driver,
            natural_key=gatha_nk,
            pg_id=str(gid) if gid else "",
            shastra_natural_key=row.get("shastra_natural_key", ""),
            gatha_number=row.get("gatha_number", ""),
            heading_hi=heading_hi,
            database=neo4j_database,
        )

    # Nodes and edges from envelope not covered by dedicated sync functions above
    from jain_kb_common.db.neo4j.stubs import sync_reference_edge
    for node in neo.get("nodes", []):
        label = node.get("label")
        props = node.get("props", {})
        nk = node.get("key")
        if label == "Topic":
            await sync_stub_node(
                neo4j_driver,
                label="Topic",
                natural_key=nk,
                props=props,
                stub_source="nj_ingestion",
                database=neo4j_database,
            )
        elif label == "GathaTeeka":
            await sync_gatha_teeka(
                neo4j_driver,
                natural_key=nk,
                teeka_natural_key=props.get("teeka_natural_key", ""),
                gatha_natural_key=props.get("gatha_natural_key", ""),
                database=neo4j_database,
            )
        elif label == "GathaTeekaBhaavarth":
            await sync_gatha_teeka_bhaavarth(
                neo4j_driver,
                natural_key=nk,
                publication_natural_key=props.get("publication_natural_key", ""),
                gatha_natural_key=props.get("gatha_natural_key", ""),
                database=neo4j_database,
            )
        elif label == "KalashBhaavarth":
            await sync_kalash_bhaavarth(
                neo4j_driver,
                natural_key=nk,
                publication_natural_key=props.get("publication_natural_key", ""),
                kalash_number=props.get("kalash_number", ""),
                database=neo4j_database,
            )

    for edge in neo.get("edges", []):
        etype = edge.get("type")
        frm = edge.get("from", {})
        to = edge.get("to", {})
        frm_key = frm.get("key")
        to_key = to.get("key")
        if not frm_key or not to_key:
            continue
        if etype == "MENTIONS_TOPIC":
            await sync_reference_edge(
                neo4j_driver,
                edge_type="MENTIONS_TOPIC",
                src_label=frm.get("label", "Gatha"),
                src_nk=frm_key,
                tgt_label=to.get("label", "Topic"),
                tgt_nk=to_key,
                database=neo4j_database,
            )


def _make_mongo_doc(doc: dict, run_id_str: str | None) -> dict:
    """Strip envelope-only fields and inject ingestion_run_id."""
    d = {k: v for k, v in doc.items() if k not in ("collection", "natural_key")}
    if run_id_str:
        d["ingestion_run_id"] = run_id_str
    return d
