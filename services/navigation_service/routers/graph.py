from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver

from ..config import settings
from ..deps import get_neo4j_driver
from ..schemas.neighbors import ShortestPathResponse
from ..services import traversal as trav_svc

router = APIRouter(prefix="/v1", tags=["graph"])


@router.get("/graph/shortest_path", response_model=ShortestPathResponse)
async def shortest_path(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> ShortestPathResponse:
    nodes = await trav_svc.get_shortest_path(
        driver,
        from_nk=from_,
        to_nk=to,
        database=settings.NEO4J_DATABASE,
    )
    if nodes is None:
        raise HTTPException(404, detail={"code": "no_path", "message": "No path found within depth 6"})
    return ShortestPathResponse(
        from_=from_,
        to=to,
        path_length=len(nodes) - 1,
        nodes=nodes,
    )
