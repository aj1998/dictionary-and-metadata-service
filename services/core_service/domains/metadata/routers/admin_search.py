from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_session, require_admin

router = APIRouter(prefix="/v1", tags=["admin"])

_VALID_TYPES = {"shastra", "author", "teeka", "book", "pravachan"}

_SEARCH_SQL = {
    "shastra": """
        SELECT id::text, natural_key, title::text AS display_raw, 'shastra' AS entity_type,
               similarity(title::text, :q) AS score
        FROM shastras
        WHERE title::text % :q OR title::text ILIKE :ilike
    """,
    "author": """
        SELECT id::text, natural_key, display_name::text AS display_raw, 'author' AS entity_type,
               similarity(display_name::text, :q) AS score
        FROM authors
        WHERE display_name::text % :q OR display_name::text ILIKE :ilike
    """,
    "teeka": """
        SELECT id::text, natural_key, natural_key AS display_raw, 'teeka' AS entity_type,
               similarity(natural_key, :q) AS score
        FROM teekas
        WHERE natural_key % :q OR natural_key ILIKE :ilike
    """,
    "book": """
        SELECT id::text, natural_key, title::text AS display_raw, 'book' AS entity_type,
               similarity(title::text, :q) AS score
        FROM books
        WHERE title::text % :q OR title::text ILIKE :ilike
    """,
    "pravachan": """
        SELECT id::text, natural_key, title::text AS display_raw, 'pravachan' AS entity_type,
               similarity(title::text, :q) AS score
        FROM pravachans
        WHERE title::text % :q OR title::text ILIKE :ilike
    """,
}


class SearchResult(BaseModel):
    entity_type: str
    id: str
    natural_key: str
    display: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


@router.get("/admin/search", response_model=SearchResponse)
async def admin_search(
    q: str = Query(..., min_length=1),
    types: str = Query("shastra,author,teeka,book,pravachan"),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> SearchResponse:
    requested = {t.strip() for t in types.split(",")} & _VALID_TYPES
    ilike = f"%{q}%"
    results: list[SearchResult] = []
    for entity_type in requested:
        rows = await session.execute(
            text(_SEARCH_SQL[entity_type]).bindparams(q=q, ilike=ilike)
        )
        for row in rows:
            results.append(SearchResult(
                entity_type=row.entity_type,
                id=row.id,
                natural_key=row.natural_key,
                display=row.display_raw,
                score=float(row.score),
            ))
    results.sort(key=lambda r: r.score, reverse=True)
    return SearchResponse(results=results)
