from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from neo4j import AsyncDriver

from ....config import settings
from ....deps import get_neo4j_driver
from ..schemas.neighbors import (
    MentionedKeywordItem,
    MentionedTopicItem,
    NodeMentionedKeywordsResponse,
    NodeMentionedTopicsResponse,
)
from ..services import traversal as trav_svc

router = APIRouter(prefix="/v1", tags=["nodes"])


@router.get("/nodes/{natural_key}/mentioned-topics", response_model=NodeMentionedTopicsResponse)
async def get_node_mentioned_topics(
    natural_key: str,
    exclude_stubs: bool = Query(False),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> NodeMentionedTopicsResponse:
    rows = await trav_svc.get_node_mentioned_topics(
        driver,
        source_nk=natural_key,
        exclude_stubs=exclude_stubs,
        database=settings.NEO4J_DATABASE,
    )
    return NodeMentionedTopicsResponse(
        source_natural_key=natural_key,
        topics=[MentionedTopicItem(**r) for r in rows],
    )


@router.get("/nodes/{natural_key}/mentioned-keywords", response_model=NodeMentionedKeywordsResponse)
async def get_node_mentioned_keywords(
    natural_key: str,
    exclude_stubs: bool = Query(False),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> NodeMentionedKeywordsResponse:
    rows = await trav_svc.get_node_mentioned_keywords(
        driver,
        source_nk=natural_key,
        exclude_stubs=exclude_stubs,
        database=settings.NEO4J_DATABASE,
    )
    return NodeMentionedKeywordsResponse(
        source_natural_key=natural_key,
        keywords=[MentionedKeywordItem(**r) for r in rows],
    )
