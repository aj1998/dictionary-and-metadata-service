from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from ....config import settings
from ....deps import get_mongo_db, get_neo4j_driver, get_session, require_admin
from ..schemas.admin import (
    AliasCreate,
    AliasResponse,
    ResyncResponse,
    ResyncScope,
    StubAuditResponse,
    StubItem,
    TopicEdgeCreate,
    TopicEdgeDelete,
    TopicEdgeResponse,
)
from ..services import aliases as alias_svc
from ..services import edges as edge_svc
from ..services import resync as resync_svc
from jain_kb_common.db.neo4j.schema_check import UnknownEdgeTypeError

router = APIRouter(prefix="/v1/admin", tags=["admin"])

# ── Alias endpoints ────────────────────────────────────────────────────────────

@router.post("/keywords/{keyword_id}/aliases", response_model=AliasResponse)
async def add_alias(
    keyword_id: uuid.UUID,
    body: AliasCreate,
    session: AsyncSession = Depends(get_session),
    driver: AsyncDriver = Depends(get_neo4j_driver),
    _: None = Depends(require_admin),
) -> AliasResponse:
    try:
        alias = await alias_svc.add_alias(
            session,
            driver,
            keyword_id=keyword_id,
            alias_text=body.alias_text,
            source=body.source,
            database=settings.NEO4J_DATABASE,
        )
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc

    from jain_kb_common.db.postgres.keywords import Keyword
    kw = await session.get(Keyword, keyword_id)

    return AliasResponse(
        id=alias.id,
        alias_text=alias.alias_text,
        source=alias.source,
        keyword_natural_key=kw.natural_key if kw else "",
        created_at=alias.created_at,
    )


@router.delete("/keywords/{keyword_id}/aliases/{alias_id}", status_code=204)
async def remove_alias(
    keyword_id: uuid.UUID,
    alias_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    driver: AsyncDriver = Depends(get_neo4j_driver),
    _: None = Depends(require_admin),
) -> None:
    try:
        await alias_svc.remove_alias(
            session,
            driver,
            keyword_id=keyword_id,
            alias_id=alias_id,
            database=settings.NEO4J_DATABASE,
        )
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc


# ── Topic edge endpoints ───────────────────────────────────────────────────────

@router.post("/topics/{natural_key}/edges", response_model=TopicEdgeResponse)
async def add_topic_edge(
    natural_key: str,
    body: TopicEdgeCreate,
    driver: AsyncDriver = Depends(get_neo4j_driver),
    _: None = Depends(require_admin),
) -> TopicEdgeResponse:
    try:
        await edge_svc.add_topic_edge(
            driver,
            source_nk=natural_key,
            target_nk=body.target_topic_natural_key,
            edge_type=body.edge_type,
            weight=body.weight,
            database=settings.NEO4J_DATABASE,
        )
    except (UnknownEdgeTypeError, ValueError) as exc:
        raise HTTPException(400, detail={"code": "invalid_edge_type", "message": str(exc)}) from exc

    return TopicEdgeResponse(
        source_topic_natural_key=natural_key,
        target_topic_natural_key=body.target_topic_natural_key,
        edge_type=body.edge_type,
        weight=body.weight,
        source="admin",
    )


@router.delete("/topics/{natural_key}/edges", status_code=204)
async def remove_topic_edge(
    natural_key: str,
    body: TopicEdgeDelete,
    driver: AsyncDriver = Depends(get_neo4j_driver),
    _: None = Depends(require_admin),
) -> None:
    try:
        await edge_svc.remove_topic_edge(
            driver,
            source_nk=natural_key,
            target_nk=body.target_topic_natural_key,
            edge_type=body.edge_type,
            database=settings.NEO4J_DATABASE,
        )
    except (UnknownEdgeTypeError, ValueError) as exc:
        raise HTTPException(400, detail={"code": "invalid_edge_type", "message": str(exc)}) from exc


# ── Graph resync ───────────────────────────────────────────────────────────────

@router.post("/graph/resync", response_model=ResyncResponse)
async def graph_resync(
    scope: ResyncScope = Query(...),
    x_confirm: str | None = Header(None, alias="X-Confirm"),
    session: AsyncSession = Depends(get_session),
    driver: AsyncDriver = Depends(get_neo4j_driver),
    mongo=Depends(get_mongo_db),
    _: None = Depends(require_admin),
) -> ResyncResponse:
    if scope == "full" and x_confirm != "resync-full":
        raise HTTPException(
            400,
            detail={
                "code": "confirmation_required",
                "message": "Full resync requires header X-Confirm: resync-full",
            },
        )

    task_id = str(uuid.uuid4())
    await resync_svc.run_resync(
        session,
        driver,
        scope=scope,
        database=settings.NEO4J_DATABASE,
        mongo_db=mongo,
    )
    return ResyncResponse(status="completed", scope=scope, task_id=task_id)


# ── Stub audit ─────────────────────────────────────────────────────────────────

@router.get("/graph/stubs", response_model=StubAuditResponse)
async def list_stubs(
    label: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    driver: AsyncDriver = Depends(get_neo4j_driver),
    _: None = Depends(require_admin),
) -> StubAuditResponse:
    label_filter = f":{label}" if label else ""
    cypher = f"""
MATCH (n{label_filter})
WHERE coalesce(n.is_stub, false) = true
RETURN n.natural_key AS natural_key,
       labels(n)[0] AS label,
       n.stub_source AS stub_source,
       toString(n.created_at) AS created_at
ORDER BY n.created_at DESC
SKIP $offset
LIMIT $limit
"""
    count_cypher = f"""
MATCH (n{label_filter})
WHERE coalesce(n.is_stub, false) = true
RETURN count(n) AS total
"""
    async with driver.session(database=settings.NEO4J_DATABASE) as neo4j_session:
        total_result = await neo4j_session.run(count_cypher)
        total_record = await total_result.single()
        total = int(total_record["total"]) if total_record else 0

        items_result = await neo4j_session.run(cypher, offset=offset, limit=limit)
        records = await items_result.data()

    items = [
        StubItem(
            natural_key=r["natural_key"] or "",
            label=r["label"] or "",
            stub_source=r.get("stub_source"),
            created_at=r.get("created_at"),
        )
        for r in records
    ]
    return StubAuditResponse(
        pagination={"total": total, "limit": limit, "offset": offset},
        items=items,
    )
