from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.hydration.topic_extracts import count_displayable_extract_blocks

from ....deps import get_mongo_db, get_session
from ..schemas.common import KeywordRef, Pagination
from ..schemas.topics import TopicDetail, TopicListResponse, TopicParentRef, TopicSummary
from ..services import topics as svc

router = APIRouter(prefix="/v1", tags=["topics"])

_CACHE_CONTROL = "public, max-age=60"


@router.get("/topics", response_model=TopicListResponse)
async def list_topics(
    response: Response,
    q: str | None = Query(None),
    parent_keyword_id: uuid.UUID | None = Query(None),
    source: str | None = Query(None),
    is_leaf: bool | None = Query(None),
    has_topic_path: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> TopicListResponse:
    items, total = await svc.list_topics(
        session, limit, offset, q=q,
        parent_keyword_id=parent_keyword_id,
        source=source, is_leaf=is_leaf,
        has_topic_path=has_topic_path,
    )
    response.headers["Cache-Control"] = _CACHE_CONTROL

    # Count only displayable extract blocks (excludes see_also/table + text-less
    # blocks) so the count and the "पढ़ें" affordance match what the modal
    # renders. Shared with the query-service search cards.
    nks = [t.natural_key for t in items]
    extract_counts = await count_displayable_extract_blocks(mongo, nks)

    result = []
    for t in items:
        pk = None
        if t.parent_keyword_id:
            from jain_kb_common.db.postgres.keywords import Keyword
            kw = await session.get(Keyword, t.parent_keyword_id)
            if kw:
                pk = KeywordRef(id=kw.id, natural_key=kw.natural_key, display_text=kw.display_text)
        result.append(TopicSummary(
            id=t.id,
            natural_key=t.natural_key,
            display_text=t.display_text,
            source=t.source,
            is_leaf=t.is_leaf,
            topic_path=t.topic_path,
            parent_keyword=pk,
            extract_count=extract_counts.get(t.natural_key, 0),
        ))

    return TopicListResponse(
        pagination=Pagination(total=total, limit=limit, offset=offset),
        items=result,
    )


@router.get("/topics/{ident}", response_model=TopicDetail)
async def get_topic(
    ident: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> TopicDetail:
    topic = await svc.get_by_ident(session, ident)
    if topic is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Topic '{ident}' not found"})
    detail = await svc.get_detail(session, mongo, topic)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    pk = None
    if detail["parent_keyword"]:
        kw = detail["parent_keyword"]
        pk = KeywordRef(id=kw.id, natural_key=kw.natural_key, display_text=kw.display_text)

    pt = None
    if detail["parent_topic"]:
        p = detail["parent_topic"]
        pt = TopicParentRef(id=p.id, natural_key=p.natural_key, display_text=p.display_text)

    return TopicDetail(
        id=topic.id,
        natural_key=topic.natural_key,
        display_text=topic.display_text,
        source=topic.source,
        is_leaf=topic.is_leaf,
        is_synthetic=topic.is_synthetic,
        topic_path=topic.topic_path,
        parent_keyword=pk,
        parent_topic=pt,
        extracts=detail["extracts"],
    )
