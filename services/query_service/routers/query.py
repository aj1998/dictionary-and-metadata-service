from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_mongo_db, get_neo4j_driver, get_session
from ..pipeline import resolve as resolve_pipeline
from ..pipeline import topics_match as tm_pipeline
from ..pipeline import graphrag as graphrag_pipeline
from ..pipeline import subworkflow as sw_pipeline
from ..schemas.keyword_resolve import (
    DefinitionBlock,
    KeywordResolveBatchRequest,
    KeywordResolveBatchResponse,
    Resolution as ResolutionSchema,
    Suggestion,
)
from ..schemas.topic_match import (
    ExtractBlock,
    GraphRAGRequest,
    GraphRAGResponse,
    NeighborGatha,
    NeighborKeyword,
    NeighborTopic,
    RankedTopicItem,
    TopicMatchItem,
    TopicNeighbors,
    TopicReference,
    TopicsMatchRequest,
    TopicsMatchResponse,
)
from ..schemas.subworkflow import (
    GathaRef,
    ShastrasForTopicRequest,
    ShastrasForTopicResponse,
    ShastraTopicItem,
    TopicMentionItem,
    TopicsInShastraRequest,
    TopicsInShastraResponse,
)
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/query", tags=["query"])

MAX_TOKENS = 32
MAX_FUZZY_TOP_K = 20


@router.post("/keyword_resolve_batch", response_model=KeywordResolveBatchResponse)
async def keyword_resolve_batch(
    body: KeywordResolveBatchRequest,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> KeywordResolveBatchResponse:
    if len(body.tokens) > MAX_TOKENS:
        raise HTTPException(
            422,
            detail={"code": "tokens_too_many", "message": f"Max {MAX_TOKENS} tokens"},
        )

    fuzzy_top_k = min(body.fuzzy_top_k, MAX_FUZZY_TOP_K)

    t0 = time.monotonic()
    trace_id = str(uuid.uuid4())

    resolutions = await resolve_pipeline.resolve_tokens(
        session,
        body.tokens,
        fuzzy_top_k=fuzzy_top_k,
        min_similarity=body.min_similarity,
    )

    definitions_map: dict[str, list] = {}
    if body.include_definitions:
        matched_nks = [r.keyword_natural_key for r in resolutions if r.keyword_natural_key]
        if matched_nks:
            definitions_map = await resolve_pipeline.fetch_definitions_batch(
                mongo, matched_nks, body.definitions_per_keyword
            )

    response_resolutions = []
    counts: dict[str, int] = {"exact": 0, "alias": 0, "suffix_strip": 0, "fuzzy": 0, "none": 0}

    for r in resolutions:
        kind = r.match_kind
        if kind in counts:
            counts[kind] += 1
        else:
            counts["none"] += 1

        defs = None
        if body.include_definitions and r.keyword_natural_key:
            raw_defs = definitions_map.get(r.keyword_natural_key, [])
            defs = [DefinitionBlock(**d) for d in raw_defs]

        suggs = None
        if kind == "none" and r.suggestions:
            suggs = [Suggestion(**s) for s in r.suggestions]

        response_resolutions.append(ResolutionSchema(
            input_token=r.input_token,
            match_kind=kind,  # type: ignore[arg-type]
            keyword_natural_key=r.keyword_natural_key,
            keyword_id=r.keyword_id,
            definitions=defs,
            suggestions=suggs,
        ))

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "keyword_resolve_batch trace=%s tokens=%d exact=%d alias=%d suffix=%d none=%d ms=%d",
        trace_id,
        len(body.tokens),
        counts["exact"],
        counts["alias"],
        counts["suffix_strip"],
        counts["none"],
        elapsed_ms,
    )
    logger.debug("per-token: %s", [(r.input_token, r.match_kind) for r in resolutions])

    return KeywordResolveBatchResponse(resolutions=response_resolutions, tool_trace_id=trace_id)


@router.post("/topics_match", response_model=TopicsMatchResponse)
async def topics_match(
    body: TopicsMatchRequest,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> TopicsMatchResponse:
    t0 = time.monotonic()
    trace_id = str(uuid.uuid4())

    search_str = body.search_str
    hits = await tm_pipeline.search_topics_trigram(
        session,
        search_str=search_str,
        limit=body.limit,
        min_similarity=body.min_similarity,
        leaf_only=body.leaf_only,
    )

    extracts_map: dict[str, list[dict]] = {}
    raw_blocks_map: dict[str, list[dict]] = {}
    extract_counts: dict[str, int] = {}
    if hits:
        natural_keys = [h.natural_key for h in hits]
        # Always provide a total block count (mirrors the data-service topics
        # listing) so cards can show the count and gate the "पढ़ें" button.
        extract_counts = await tm_pipeline.count_topic_extract_blocks(mongo, natural_keys)
        if body.include_extracts:
            extracts_map = await tm_pipeline.fetch_topic_extracts_batch(mongo, natural_keys)
        if body.include_references:
            raw_blocks_map = await graphrag_pipeline._fetch_raw_blocks(mongo, natural_keys)

    matches: list[TopicMatchItem] = []
    for hit in hits:
        nk = hit.natural_key
        extracts_hi = None
        if body.include_extracts:
            blocks = extracts_map.get(nk, [])
            extracts_hi = [ExtractBlock(**b) for b in blocks]

        references = None
        if body.include_references:
            raw_blocks = raw_blocks_map.get(nk, [])
            refs = tm_pipeline.extract_references_from_blocks(raw_blocks)
            references = [TopicReference(**r) for r in refs]

        matches.append(TopicMatchItem(
            topic_natural_key=nk,
            topic_pg_id=hit.topic_pg_id,
            display_text_hi=tm_pipeline.get_display_text_hi(hit.display_text),
            ancestors_hi=tm_pipeline.ancestors_from_natural_key(nk),
            is_leaf=hit.is_leaf,
            source=hit.source,
            similarity=hit.similarity,
            score=hit.score,
            extract_count=extract_counts.get(nk, 0),
            extracts_hi=extracts_hi,
            references=references,
        ))

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "topics_match trace=%s search=%r hits=%d ms=%d",
        trace_id, search_str, len(matches), elapsed_ms,
    )

    return TopicsMatchResponse(matches=matches, tool_trace_id=trace_id)


@router.post("/graphrag", response_model=GraphRAGResponse)
async def graphrag(
    body: GraphRAGRequest,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
    neo4j: object = Depends(get_neo4j_driver),
) -> GraphRAGResponse:
    t0 = time.monotonic()
    trace_id = str(uuid.uuid4())

    ranked, unresolved = await graphrag_pipeline.run_graphrag(
        session=session,
        mongo_db=mongo,
        neo4j_driver=neo4j,
        neo4j_database=settings.NEO4J_DATABASE,
        tokens=body.tokens,
        max_hops=body.max_hops,
        limit=body.limit,
        edge_types=body.edge_types,
        include_extracts=body.include_extracts,
        include_neighbors=body.include_neighbors,
        include_references=body.include_references,
        fuzzy=body.fuzzy,
    )

    hydration = await graphrag_pipeline.hydrate_topics(
        mongo_db=mongo,
        neo4j_driver=neo4j,
        neo4j_database=settings.NEO4J_DATABASE,
        ranked=ranked,
        include_extracts=body.include_extracts,
        include_neighbors=body.include_neighbors,
        include_references=body.include_references,
    )

    ranked_items: list[RankedTopicItem] = []
    for r in ranked:
        h = hydration.get(r.topic_nk, {})

        extracts_hi = None
        if body.include_extracts:
            extracts_hi = [ExtractBlock(**b) for b in h.get("extracts_hi", [])]

        references = None
        if body.include_references:
            references = [TopicReference(**ref) for ref in h.get("references", [])]

        neighbors = None
        if body.include_neighbors:
            nb = h.get("neighbors", {})
            neighbors = TopicNeighbors(
                related_topics=[NeighborTopic(**t) for t in nb.get("related_topics", [])],
                mentioned_in_gathas=[NeighborGatha(**g) for g in nb.get("mentioned_in_gathas", [])],
                related_keywords=[NeighborKeyword(**k) for k in nb.get("related_keywords", [])],
            )

        ranked_items.append(RankedTopicItem(
            topic_natural_key=r.topic_nk,
            topic_pg_id=r.topic_pg_id,
            display_text_hi=r.heading_hi,
            ancestors_hi=r.ancestors_hi,
            score=r.score,
            overlap_count=r.overlap_count,
            matched_seed_keywords=r.matched_seed_keywords,
            is_leaf=r.is_leaf,
            source=r.source,
            extracts_hi=extracts_hi,
            references=references,
            neighbors=neighbors,
        ))

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "graphrag trace=%s tokens=%d ranked=%d unresolved=%d ms=%d",
        trace_id, len(body.tokens), len(ranked_items), len(unresolved), elapsed_ms,
    )

    return GraphRAGResponse(
        ranked_topics=ranked_items,
        unresolved_tokens=unresolved,
        tool_trace_id=trace_id,
    )


@router.post("/topics_in_shastra", response_model=TopicsInShastraResponse)
async def topics_in_shastra(
    body: TopicsInShastraRequest,
    neo4j: object = Depends(get_neo4j_driver),
) -> TopicsInShastraResponse:
    t0 = time.monotonic()
    trace_id = str(uuid.uuid4())

    rows = await sw_pipeline.fetch_topics_in_shastra(
        driver=neo4j,
        shastra_nk=body.shastra_natural_key,
        gatha_number=body.gatha_number,
        limit=body.limit,
        database=settings.NEO4J_DATABASE,
    )

    topics: list[TopicMentionItem] = []
    for row in rows:
        topics.append(TopicMentionItem(
            topic_natural_key=row.topic_nk,
            display_text_hi=row.display_text_hi,
            ancestors_hi=tm_pipeline.ancestors_from_natural_key(row.topic_nk),
            is_leaf=row.is_leaf,
            mention_count=row.mention_count,
        ))

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "topics_in_shastra trace=%s shastra=%s gatha=%s topics=%d ms=%d",
        trace_id, body.shastra_natural_key, body.gatha_number, len(topics), elapsed_ms,
    )

    return TopicsInShastraResponse(topics=topics, tool_trace_id=trace_id)


@router.post("/shastras_for_topic", response_model=ShastrasForTopicResponse)
async def shastras_for_topic(
    body: ShastrasForTopicRequest,
    session: AsyncSession = Depends(get_session),
    neo4j: object = Depends(get_neo4j_driver),
) -> ShastrasForTopicResponse:
    t0 = time.monotonic()
    trace_id = str(uuid.uuid4())

    topic_nk = body.topic_natural_key
    if topic_nk is None:
        # Fall back: resolve keywords via topics_match, take top-1
        search_str = " ".join(body.keywords or [])
        hits = await tm_pipeline.search_topics_trigram(
            session,
            search_str=search_str,
            limit=1,
            min_similarity=0.3,
            leaf_only=True,
        )
        if not hits:
            logger.info(
                "shastras_for_topic trace=%s keywords=%r resolved no topic",
                trace_id, body.keywords,
            )
            return ShastrasForTopicResponse(
                topic_natural_key="",
                shastras=[],
                tool_trace_id=trace_id,
            )
        topic_nk = hits[0].natural_key

    rows = await sw_pipeline.fetch_shastras_for_topic(
        driver=neo4j,
        topic_nk=topic_nk,
        limit_shastras=body.limit_shastras,
        limit_gathas_per_shastra=body.limit_gathas_per_shastra,
        database=settings.NEO4J_DATABASE,
    )

    shastras: list[ShastraTopicItem] = []
    for row in rows:
        gathas: list[GathaRef] = []
        if body.include_gathas:
            gatha_src = row.gathas[: body.limit_gathas_per_shastra]
            for g in gatha_src:
                try:
                    num = int(g.get("number") or 0)
                    page = g.get("page_number")
                    page_int: int | None = int(page) if page is not None else None
                except (TypeError, ValueError):
                    num = 0
                    page_int = None
                gathas.append(GathaRef(number=num, page_number=page_int))

        shastras.append(ShastraTopicItem(
            shastra_natural_key=row.shastra_nk,
            name_hi=row.name_hi,
            total_mentions=row.total_mentions,
            gathas=gathas,
        ))

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "shastras_for_topic trace=%s topic=%s shastras=%d ms=%d",
        trace_id, topic_nk, len(shastras), elapsed_ms,
    )

    return ShastrasForTopicResponse(
        topic_natural_key=topic_nk,
        shastras=shastras,
        tool_trace_id=trace_id,
    )
