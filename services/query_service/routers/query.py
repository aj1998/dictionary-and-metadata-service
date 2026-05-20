from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_mongo_db, get_session
from ..pipeline import resolve as resolve_pipeline
from ..schemas.keyword_resolve import (
    DefinitionBlock,
    KeywordResolveBatchRequest,
    KeywordResolveBatchResponse,
    Resolution as ResolutionSchema,
    Suggestion,
)

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

    # Gather natural keys for definition lookup
    definitions_map: dict[str, list] = {}
    if body.include_definitions:
        matched_nks = [r.keyword_natural_key for r in resolutions if r.keyword_natural_key]
        if matched_nks:
            definitions_map = await resolve_pipeline.fetch_definitions_batch(
                mongo, matched_nks, body.definitions_per_keyword
            )

    # Build response in original token order
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
