from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from ....config import settings
from ....deps import get_neo4j_driver, get_session
from ..schemas.neighbors import (
    KeywordItem,
    NeighborItem,
    NeighborsResponse,
    TopicKeywordsResponse,
)
from ..services import traversal as trav_svc

router = APIRouter(prefix="/v1", tags=["topics"])


@router.get("/topics/{natural_key}/neighbors", response_model=NeighborsResponse)
async def get_topic_neighbors(
    natural_key: str,
    depth: int = Query(1, ge=1, le=3),
    edge_types: str = Query("IS_A,PART_OF,RELATED_TO"),
    exclude_stubs: bool = Query(True),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> NeighborsResponse:
    et_list = [et.strip() for et in edge_types.split(",") if et.strip()]
    neighbors = await trav_svc.get_topic_neighbors(
        driver,
        topic_nk=natural_key,
        edge_types=et_list,
        depth=depth,
        exclude_stubs=exclude_stubs,
        database=settings.NEO4J_DATABASE,
    )
    return NeighborsResponse(
        topic_natural_key=natural_key,
        neighbors=[
            NeighborItem(
                natural_key=n["natural_key"],
                display_text_hi=n.get("display_text_hi"),
                label=n.get("label", "Topic"),
                edge_type=n["edge_type"],
                edge_direction=n["edge_direction"],  # type: ignore[arg-type]
                weight=n.get("weight", 1.0),
                is_stub=n["is_stub"],
            )
            for n in neighbors
        ],
    )


@router.get("/topics/{natural_key}/keywords", response_model=TopicKeywordsResponse)
async def get_topic_keywords(
    natural_key: str,
    exclude_stubs: bool = Query(True),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> TopicKeywordsResponse:
    keywords = await trav_svc.get_topic_keywords(
        driver,
        topic_nk=natural_key,
        exclude_stubs=exclude_stubs,
        database=settings.NEO4J_DATABASE,
    )
    return TopicKeywordsResponse(
        topic_natural_key=natural_key,
        keywords=[
            KeywordItem(
                natural_key=k["natural_key"],
                display_text=k.get("display_text"),
                edge_type=k["edge_type"],
                is_stub=k["is_stub"],
            )
            for k in keywords
        ],
    )
