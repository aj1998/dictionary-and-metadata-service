from __future__ import annotations

import logging
import random

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver
from pydantic import BaseModel

from ....config import LANDING_SEED_KEYWORDS, settings
from ....deps import get_neo4j_driver
from ..schemas.neighbors import ShortestPathResponse
from ..services import traversal as trav_svc

router = APIRouter(prefix="/v1", tags=["graph"])
logger = logging.getLogger(__name__)


class GraphNode(BaseModel):
    nk: str
    kind: str
    title_hi: str
    title_en: str | None = None
    meta: dict[str, str] | None = None
    degree: int = 0


class GraphEdge(BaseModel):
    id: str
    src: str
    dst: str
    kind: str
    weight: float = 1.0


class GraphPayload(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    focus_nk: str
    depth: int


def _label_to_kind(label: str | None) -> str:
    normalized = (label or "Topic").lower()
    mapping = {"topic": "topic", "keyword": "keyword", "shastra": "shastra", "gatha": "gatha"}
    return mapping.get(normalized, "topic")


def _build_payload(
    records: list[dict],
    *,
    focus_nk: str,
    depth: int,
    focus_label: str | None = None,
) -> GraphPayload:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for row in records:
        src_nk = row.get("src_nk")
        if src_nk:
            src_node = nodes.get(src_nk)
            if not src_node:
                src_node = GraphNode(
                    nk=src_nk,
                    kind=_label_to_kind(row.get("src_label")),
                    title_hi=row.get("src_hi") or src_nk,
                    degree=0,
                )
                nodes[src_nk] = src_node
            src_node.degree += 1

        dst_nk = row.get("dst_nk")
        if dst_nk:
            dst_node = nodes.get(dst_nk)
            if not dst_node:
                dst_node = GraphNode(
                    nk=dst_nk,
                    kind=_label_to_kind(row.get("dst_label")),
                    title_hi=row.get("dst_hi") or dst_nk,
                    degree=0,
                )
                nodes[dst_nk] = dst_node
            dst_node.degree += 1

        if src_nk and dst_nk:
            rel_kind = row.get("rel_type") or "RELATED_TO"
            edges.append(
                GraphEdge(
                    id=f"{src_nk}|{rel_kind}|{dst_nk}",
                    src=src_nk,
                    dst=dst_nk,
                    kind=rel_kind,
                    weight=float(row.get("weight") or 1.0),
                )
            )

    if focus_nk not in nodes:
        # Use the label returned by the Cypher query if available, falling back to "topic"
        # so that isolated gatha/shastra focus nodes get the correct kind.
        nodes[focus_nk] = GraphNode(
            nk=focus_nk,
            kind=_label_to_kind(focus_label),
            title_hi=focus_nk,
            degree=0,
        )

    return GraphPayload(nodes=list(nodes.values()), edges=edges, focus_nk=focus_nk, depth=depth)


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


@router.get("/landing", response_model=GraphPayload)
async def landing(
    exclude_stubs: bool = Query(True),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> GraphPayload:
    stub_clause = "AND NOT (coalesce(s.is_stub, false) OR coalesce(t.is_stub, false))" if exclude_stubs else ""
    cypher = f"""
    MATCH (s)-[r:IS_A|PART_OF|RELATED_TO|HAS_TOPIC|MENTIONS_KEYWORD|MENTIONS_TOPIC|IN_SHASTRA]-(t)
    WHERE (s:Topic OR s:Keyword OR s:Shastra OR s:Gatha)
      AND (t:Topic OR t:Keyword OR t:Shastra OR t:Gatha)
      {stub_clause}
    RETURN coalesce(s.natural_key, '') AS src_nk,
           labels(s)[0] AS src_label,
           coalesce(s.display_text_hi, s.display_text, s.natural_key, '') AS src_hi,
           coalesce(t.natural_key, '') AS dst_nk,
           labels(t)[0] AS dst_label,
           coalesce(t.display_text_hi, t.display_text, t.natural_key, '') AS dst_hi,
           type(r) AS rel_type,
           coalesce(r.weight, 1.0) AS weight
    LIMIT 120
    """
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        records = await (await session.run(cypher)).data()
    focus_nk = records[0].get("src_nk") if records else "topic:landing"
    logger.info("Graph landing payload generated with %s records (exclude_stubs=%s)", len(records), exclude_stubs)
    return _build_payload(records, focus_nk=focus_nk or "topic:landing", depth=1)


@router.get("/landing/random", response_model=GraphPayload)
async def landing_random(
    depth: int = Query(2, ge=1, le=4),
    exclude_stubs: bool = Query(True),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> GraphPayload:
    seeds = list(LANDING_SEED_KEYWORDS)
    random.shuffle(seeds)
    attempts = seeds[:4]

    for seed_nk in attempts:
        payload = await expand(natural_key=seed_nk, depth=depth, exclude_stubs=exclude_stubs, driver=driver)
        if payload.edges:
            logger.info(
                "Graph landing/random: using seed=%s, depth=%s, nodes=%s, edges=%s",
                seed_nk, depth, len(payload.nodes), len(payload.edges),
            )
            return payload

    logger.warning("Graph landing/random: no seed available after %d attempts", len(attempts))
    raise HTTPException(503, detail={"code": "no_seed_available"})


@router.get("/expand/{natural_key}", response_model=GraphPayload)
async def expand(
    natural_key: str,
    depth: int = Query(2, ge=1, le=4),
    exclude_stubs: bool = Query(True),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> GraphPayload:
    stub_clause = "AND NOT (coalesce(s.is_stub, false) OR coalesce(t.is_stub, false))" if exclude_stubs else ""
    cypher = f"""
    MATCH (focus {{natural_key: $nk}})
    OPTIONAL MATCH p=(focus)-[r:IS_A|PART_OF|RELATED_TO|HAS_TOPIC|MENTIONS_KEYWORD|MENTIONS_TOPIC|IN_SHASTRA*1..4]-(n)
    WITH focus, p, n, relationships(p) AS rels, labels(focus)[0] AS focus_label
    WHERE p IS NULL OR length(p) <= $depth
    UNWIND CASE WHEN p IS NULL THEN [] ELSE rels END AS rel
    WITH focus, focus_label, startNode(rel) AS s, endNode(rel) AS t, rel
    WHERE true {stub_clause}
    RETURN coalesce(s.natural_key, '') AS src_nk,
           labels(s)[0] AS src_label,
           coalesce(s.display_text_hi, s.display_text, s.natural_key, '') AS src_hi,
           coalesce(t.natural_key, '') AS dst_nk,
           labels(t)[0] AS dst_label,
           coalesce(t.display_text_hi, t.display_text, t.natural_key, '') AS dst_hi,
           type(rel) AS rel_type,
           coalesce(rel.weight, 1.0) AS weight,
           focus_label
    LIMIT 500
    """
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        records = await (await session.run(cypher, nk=natural_key, depth=depth)).data()
    focus_label = records[0].get("focus_label") if records else None
    logger.info("Graph expand payload generated for nk=%s, depth=%s, records=%s (exclude_stubs=%s)", natural_key, depth, len(records), exclude_stubs)
    return _build_payload(records, focus_nk=natural_key, depth=depth, focus_label=focus_label)


@router.get("/preview/{natural_key}", response_model=GraphPayload)
async def preview(
    natural_key: str,
    hops: int = Query(1, ge=1, le=2),
    exclude_stubs: bool = Query(True),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> GraphPayload:
    payload = await expand(natural_key=natural_key, depth=hops, exclude_stubs=exclude_stubs, driver=driver)
    logger.info("Graph preview payload generated for nk=%s, hops=%s", natural_key, hops)
    return payload
