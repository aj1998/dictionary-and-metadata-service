from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_neo4j_driver, get_session
from ..schemas.neighbors import KeywordTopicsResponse, TopicItem
from ..schemas.resolution import ResolveResponse
from ..services import resolution as res_svc
from ..services import traversal as trav_svc
from ..config import settings

router = APIRouter(prefix="/v1", tags=["keywords"])


@router.get("/keywords/{token}/resolve", response_model=ResolveResponse)
async def resolve_keyword(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> ResolveResponse:
    nk, kind = await res_svc.resolve_token(session, token)
    return ResolveResponse(
        input=token,
        matched_keyword_natural_key=nk,
        match_kind=kind,  # type: ignore[arg-type]
    )


@router.get("/keywords/{natural_key}/topics", response_model=KeywordTopicsResponse)
async def get_keyword_topics(
    natural_key: str,
    depth: int = Query(1, ge=1, le=2),
    edge_types: str = Query("HAS_TOPIC,MENTIONS_KEYWORD"),
    exclude_stubs: bool = Query(True),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> KeywordTopicsResponse:
    et_list = [et.strip() for et in edge_types.split(",") if et.strip()]
    topics = await trav_svc.get_keyword_topics(
        driver,
        keyword_nk=natural_key,
        edge_types=et_list,
        depth=depth,
        exclude_stubs=exclude_stubs,
        database=settings.NEO4J_DATABASE,
    )
    return KeywordTopicsResponse(
        keyword_natural_key=natural_key,
        topics=[
            TopicItem(
                natural_key=t["natural_key"],
                display_text_hi=t.get("display_text_hi"),
                edge_type=t["edge_type"],
                is_stub=t["is_stub"],
            )
            for t in topics
        ],
    )
