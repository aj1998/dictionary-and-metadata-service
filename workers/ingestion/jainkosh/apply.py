"""Idempotent apply layer: WouldWriteEnvelope → Postgres + Mongo + Neo4j."""
from __future__ import annotations

import unicodedata
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.upserts import (
    upsert_keyword_definition,
    upsert_topic_extract,
    upsert_raw_html_snapshot,
    stable_id,
)
from jain_kb_common.db.postgres.enums import IngestionSource
from jain_kb_common.db.postgres.keywords import Keyword
from jain_kb_common.db.postgres.topics import Topic

import logging
_log = logging.getLogger(__name__)
from jain_kb_common.db.postgres.upserts import (
    upsert_keyword,
    upsert_keyword_alias,
    upsert_topic,
)
from jain_kb_common.db.neo4j.stubs import sync_stub_node, sync_reference_edge, delete_placeholder_stub
from jain_kb_common.db.neo4j.upserts import (
    sync_keyword,
    sync_topic,
    sync_has_topic_edge,
    sync_part_of_edge,
    sync_related_to_edge,
)


def _nfc(v: str) -> str:
    return unicodedata.normalize("NFC", v)


def _nfc_str(v: Any) -> Any:
    if isinstance(v, str):
        return _nfc(v)
    if isinstance(v, list):
        return [_nfc_str(i) for i in v]
    if isinstance(v, dict):
        return {k: _nfc_str(val) for k, val in v.items()}
    return v


async def _resolve_topic_stubs(
    pg_session: AsyncSession,
    neo4j_nodes: list[dict],
    neo4j_edges: list[dict],
) -> tuple[list[dict], list[dict], set[str]]:
    """Resolve cross-page Topic stubs that carry resolve_key to actual natural_keys.

    During parsing, cross-page Topic references are emitted as stub nodes with
    ``resolve_key`` (e.g. ``"स्वभाव:2"``) because the heading text of the target
    topic is not available in the current keyword's HTML page.  When the target
    keyword has already been ingested (its topics exist in Postgres), this function
    looks up the real ``natural_key`` by ``(parent_keyword_natural_key, topic_path)``
    and replaces the placeholder with it.  If the target keyword has not yet been
    ingested, the resolve_key itself is used as a fallback (preserving the previous
    behaviour).

    Returns a 3-tuple: (resolved_nodes, resolved_edges, resolved_placeholders).
    ``resolved_placeholders`` is the set of resolve_key strings that were successfully
    mapped to a *different* actual key — callers should delete the old placeholder
    stub nodes so they do not pollute the graph.
    """
    # Collect unique (parent_kw, topic_path) pairs from resolve_key stub nodes.
    rk_lookup: dict[str, tuple[str, str]] = {}
    for node in neo4j_nodes:
        rk = node.get("resolve_key")
        if rk and node.get("is_stub_seed") and node.get("label") == "Topic":
            props = node.get("props", {})
            parent_kw = props.get("parent_keyword_natural_key", "")
            tp = props.get("topic_path", "")
            if parent_kw and tp:
                rk_lookup[rk] = (parent_kw, tp)

    if not rk_lookup:
        return neo4j_nodes, neo4j_edges, set()

    # Query Postgres for actual natural_keys.
    rk_to_actual: dict[str, str] = {}
    for rk, (parent_kw, tp) in rk_lookup.items():
        res = await pg_session.execute(
            select(Topic.natural_key)
            .join(Keyword, Topic.parent_keyword_id == Keyword.id)
            .where(Keyword.natural_key == parent_kw, Topic.topic_path == tp)
        )
        actual_nk = res.scalars().first()
        if actual_nk:
            _log.debug("resolve_key %s → %s", rk, actual_nk)
            rk_to_actual[rk] = actual_nk
        else:
            _log.debug("resolve_key %s: target not in Postgres yet, using placeholder", rk)
            rk_to_actual[rk] = rk

    # Track which placeholders were actually resolved to a different key.
    resolved_placeholders: set[str] = {rk for rk, actual in rk_to_actual.items() if actual != rk}

    # Update nodes: replace resolve_key with the resolved (or fallback) key.
    resolved_nodes: list[dict] = []
    for node in neo4j_nodes:
        rk = node.get("resolve_key")
        if rk and node.get("is_stub_seed") and node.get("label") == "Topic":
            actual_key = rk_to_actual.get(rk, rk)
            new_node = {k: v for k, v in node.items() if k != "resolve_key"}
            new_node["key"] = actual_key
            resolved_nodes.append(new_node)
        else:
            resolved_nodes.append(node)

    # Update edges: replace resolve_key in the ``to`` field.
    resolved_edges: list[dict] = []
    for edge in neo4j_edges:
        to = edge.get("to", {})
        rk = to.get("resolve_key")
        if rk:
            actual_key = rk_to_actual.get(rk, rk)
            new_to = {k: v for k, v in to.items() if k != "resolve_key"}
            new_to["key"] = actual_key
            resolved_edges.append({**edge, "to": new_to})
        else:
            resolved_edges.append(edge)

    return resolved_nodes, resolved_edges, resolved_placeholders


async def _resolve_keyword_id(session: AsyncSession, natural_key: str) -> uuid.UUID | None:
    res = await session.execute(select(Keyword.id).where(Keyword.natural_key == natural_key))
    return res.scalar_one_or_none()


async def _resolve_topic_id(session: AsyncSession, natural_key: str) -> uuid.UUID | None:
    res = await session.execute(select(Topic.id).where(Topic.natural_key == natural_key))
    return res.scalar_one_or_none()


async def apply_approved_keyword_payload(
    *,
    envelope: dict,
    pg_session: AsyncSession,
    mongo_db,
    neo4j_driver,
    ingestion_run_id: uuid.UUID | None = None,
    neo4j_database: str = "jainkb",
) -> None:
    """
    Idempotently apply one keyword's would_write payload to Postgres, Mongo, Neo4j.
    Safe to call twice with the same envelope (no net DB changes on second call).
    """
    envelope = _nfc_str(envelope)
    ww = envelope["would_write"]
    pg = ww["postgres"]
    mongo = ww["mongo"]
    neo = ww["neo4j"]

    # --- Postgres (single transaction) ---
    keyword_row = pg["keywords"][0]
    keyword_nk = keyword_row["natural_key"]
    keyword_id = await upsert_keyword(
        pg_session,
        natural_key=keyword_nk,
        display_text=keyword_nk,
        source_url=keyword_row.get("source_url"),
        definition_doc_ids=[str(stable_id(keyword_nk))],
    )

    # Topological sort: parents before children (handles None topic_path correctly)
    def _topo_sort(rows: list[dict]) -> list[dict]:
        nk_set = {r["natural_key"] for r in rows}
        nk_to_row = {r["natural_key"]: r for r in rows}
        visited: set[str] = set()
        result: list[dict] = []

        def visit(nk: str) -> None:
            if nk in visited:
                return
            visited.add(nk)
            row = nk_to_row.get(nk)
            if row is None:
                return
            parent_nk = row.get("parent_topic_natural_key")
            if parent_nk and parent_nk in nk_set:
                visit(parent_nk)
            result.append(row)

        for row in rows:
            visit(row["natural_key"])
        return result

    topic_rows = _topo_sort(pg.get("topics", []))
    # Map natural_key → uuid.UUID for parent resolution
    topic_id_map: dict[str, uuid.UUID] = {}

    for row in topic_rows:
        tnk = row["natural_key"]
        parent_kw_nk = row.get("parent_keyword_natural_key") or keyword_nk
        parent_kw_id: uuid.UUID | None = None
        if parent_kw_nk:
            if parent_kw_nk == keyword_nk:
                parent_kw_id = keyword_id
            else:
                parent_kw_id = await _resolve_keyword_id(pg_session, parent_kw_nk)

        parent_topic_nk = row.get("parent_topic_natural_key")
        parent_topic_id: uuid.UUID | None = None
        if parent_topic_nk:
            parent_topic_id = topic_id_map.get(parent_topic_nk) or await _resolve_topic_id(pg_session, parent_topic_nk)

        tid = await upsert_topic(
            pg_session,
            natural_key=tnk,
            display_text=row.get("display_text", []),
            source=IngestionSource.jainkosh,
            parent_keyword_id=parent_kw_id,
            topic_path=row.get("topic_path"),
            parent_topic_id=parent_topic_id,
            is_leaf=row.get("is_leaf", True),
            is_synthetic=row.get("is_synthetic", False),
        )
        topic_id_map[tnk] = tid

    for alias_row in pg.get("keyword_aliases", []):
        alias_text = alias_row.get("alias_text") or alias_row.get("alias")
        if alias_text:
            await upsert_keyword_alias(
                pg_session,
                keyword_id=keyword_id,
                alias=alias_text,
                source=alias_row.get("source", "jainkosh"),
            )

    await pg_session.commit()

    # Resolve cross-page Topic stubs now that Postgres has been committed.
    # If the target keyword was already ingested (earlier in the same run or a
    # prior run), the actual heading-based natural_key is returned; otherwise
    # the placeholder resolve_key is used as a fallback.
    neo4j_nodes, neo4j_edges, resolved_placeholders = await _resolve_topic_stubs(
        pg_session, neo.get("nodes", []), neo.get("edges", [])
    )

    # --- Mongo (after Postgres commit) ---
    run_id_str = str(ingestion_run_id) if ingestion_run_id else None

    kdef_docs = mongo.get("keyword_definitions", [])
    if kdef_docs:
        kdef = dict(kdef_docs[0])
        kdef["keyword_id"] = str(keyword_id)
        if run_id_str:
            kdef["ingestion_run_id"] = run_id_str
        kdef.pop("collection", None)
        kdef.pop("natural_key", None)
        await upsert_keyword_definition(mongo_db, natural_key=keyword_nk, doc=kdef)

    for te in mongo.get("topic_extracts", []):
        te_doc = dict(te)
        te_nk = te_doc.get("natural_key") or te_doc.get("natural_key", "")
        if run_id_str:
            te_doc["ingestion_run_id"] = run_id_str
        # inject parent_keyword_natural_key if missing
        if "parent_keyword_natural_key" not in te_doc:
            te_doc["parent_keyword_natural_key"] = keyword_nk
        te_doc.pop("collection", None)
        te_doc.pop("natural_key", None)
        await upsert_topic_extract(mongo_db, natural_key=te_nk, doc=te_doc)

    raw_html = mongo.get("raw_html_snapshots", [])
    if raw_html:
        snap = dict(raw_html[0])
        snap_nk = snap.get("natural_key", keyword_nk)
        if run_id_str:
            snap["ingestion_run_id"] = run_id_str
        snap.pop("collection", None)
        snap.pop("natural_key", None)
        await upsert_raw_html_snapshot(mongo_db, natural_key=snap_nk, doc=snap)

    # --- Neo4j ---
    kw_pg_id = str(keyword_id)
    await sync_keyword(
        neo4j_driver,
        natural_key=keyword_nk,
        pg_id=kw_pg_id,
        display_text=keyword_nk,
        source_url=keyword_row.get("source_url"),
        database=neo4j_database,
    )

    # Resolve display_text_hi from display_text list
    def _hi_text(display_text):
        if isinstance(display_text, list):
            for lt in display_text:
                if isinstance(lt, dict) and lt.get("lang") in ("hin", "hi"):
                    return lt.get("text", "")
            if display_text:
                return display_text[0].get("text", "") if isinstance(display_text[0], dict) else str(display_text[0])
        return str(display_text) if display_text else ""

    # Sync Topics (parents first, same order as Postgres)
    topic_nodes = [n for n in neo4j_nodes if n.get("label") == "Topic"]
    topic_node_map = {n["key"]: n for n in topic_nodes}

    for row in topic_rows:
        tnk = row["natural_key"]
        tid = topic_id_map.get(tnk)
        display_text = row.get("display_text", [])
        display_hi = _hi_text(display_text)
        topic_node = topic_node_map.get(tnk, {})
        node_props = topic_node.get("props", {})
        await sync_topic(
            neo4j_driver,
            natural_key=tnk,
            pg_id=str(tid) if tid else "",
            display_text_hi=node_props.get("display_text_hi") or display_hi,
            source="jainkosh",
            parent_keyword_natural_key=row.get("parent_keyword_natural_key") or keyword_nk,
            topic_path=row.get("topic_path"),
            is_leaf=row.get("is_leaf", True),
            database=neo4j_database,
        )

    # Write stub-seed and lazy nodes before edges so endpoints always exist
    for node in neo4j_nodes:
        if node.get("is_stub_seed") or node.get("lazy"):
            await sync_stub_node(
                neo4j_driver,
                label=node["label"],
                natural_key=node["key"],
                props=node.get("props", {}),
                database=neo4j_database,
            )

    # Wire edges from the envelope
    for edge in neo4j_edges:
        etype = edge.get("type")
        frm = edge.get("from", {})
        to = edge.get("to", {})
        frm_key = frm.get("key")
        to_key = to.get("key")

        if not frm_key or not to_key:
            continue

        if etype == "HAS_TOPIC" and frm.get("label") == "Keyword" and to.get("label") == "Topic":
            await sync_has_topic_edge(
                neo4j_driver, keyword_nk=frm_key, topic_nk=to_key, database=neo4j_database
            )
        elif etype == "PART_OF" and frm.get("label") == "Topic" and to.get("label") == "Topic":
            await sync_part_of_edge(
                neo4j_driver, child_nk=frm_key, parent_nk=to_key, database=neo4j_database
            )
        elif etype == "RELATED_TO":
            if edge.get("props", {}).get("target_exists", True):
                await sync_related_to_edge(
                    neo4j_driver,
                    source_nk=frm_key,
                    target_nk=to_key,
                    source_label=frm.get("label", "Topic"),
                    target_label=to.get("label", "Topic"),
                    database=neo4j_database,
                )
        elif etype in ("MENTIONS_TOPIC", "CONTAINS_DEFINITION"):
            src_label = frm.get("label", "")
            tgt_label = to.get("label", "")
            if src_label and tgt_label:
                await sync_reference_edge(
                    neo4j_driver,
                    edge_type=etype,
                    src_label=src_label,
                    src_nk=frm_key,
                    tgt_label=tgt_label,
                    tgt_nk=to_key,
                    edge_props=edge.get("props") or {},
                    database=neo4j_database,
                )

    # Delete numerical placeholder stub nodes that were resolved in this pass.
    # In pass 1, unresolved cross-page stubs fall back to using their resolve_key
    # (e.g. "स्वभाव:2") as the Neo4j natural_key.  In pass 2, these resolve to the
    # actual heading-based key; the old placeholder node (and all its edges) must be
    # removed or it persists as an orphaned stub in the graph.
    for placeholder_nk in resolved_placeholders:
        _log.debug("deleting resolved placeholder stub Topic %s", placeholder_nk)
        await delete_placeholder_stub(
            neo4j_driver, label="Topic", natural_key=placeholder_nk, database=neo4j_database
        )
