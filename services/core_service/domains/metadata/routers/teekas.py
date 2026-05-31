from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_session, require_admin
from ..schemas.common import AnuyogaSummary, AuthorSummary, Pagination, ShastraSummary
from ..schemas.publications import PublicationListResponse, PublicationResponse
from ..schemas.teekas import (
    TeekaCreate,
    TeekaListResponse,
    TeekaResponse,
    TeekaStats,
    TeekaSummaryResponse,
    TeekaUpdate,
)
from ..services import publications as pub_svc
from ..services import teekas as svc

router = APIRouter(prefix="/v1", tags=["teekas"])


def _limit_offset(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset


def _build_teeka_response(detail: dict) -> TeekaResponse:
    t = detail["teeka"]
    shastra = detail["shastra"]
    shastra_author = detail["shastra_author"]
    shastra_anuyogas = detail["shastra_anuyogas"]
    teekakar = detail["teekakar"]
    return TeekaResponse(
        id=t.id,
        natural_key=t.natural_key,
        shastra=ShastraSummary(
            id=shastra.id,
            natural_key=shastra.natural_key,
            title=shastra.title,
            author=AuthorSummary(
                id=shastra_author.id,
                natural_key=shastra_author.natural_key,
                display_name=shastra_author.display_name,
                kind=shastra_author.kind,
            ) if shastra_author else None,
            anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in shastra_anuyogas],
        ) if shastra else None,
        teekakar=AuthorSummary(
            id=teekakar.id,
            natural_key=teekakar.natural_key,
            display_name=teekakar.display_name,
            kind=teekakar.kind,
        ) if teekakar else None,
        publisher=t.publisher,
        translator=t.translator,
        editor=t.editor,
        cataloguesearch_shastra_id=t.cataloguesearch_shastra_id,
        public_url=t.public_url,
        publisher_url=t.publisher_url,
        stats=TeekaStats(total_publications=detail["total_publications"]),
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _build_teeka_summary(t: object, detail: dict, similarity: float | None = None) -> TeekaSummaryResponse:
    shastra = detail["shastra"]
    shastra_author = detail["shastra_author"]
    shastra_anuyogas = detail["shastra_anuyogas"]
    teekakar = detail["teekakar"]
    return TeekaSummaryResponse(
        id=t.id,  # type: ignore[attr-defined]
        natural_key=t.natural_key,  # type: ignore[attr-defined]
        shastra=ShastraSummary(
            id=shastra.id,
            natural_key=shastra.natural_key,
            title=shastra.title,
            author=AuthorSummary(
                id=shastra_author.id,
                natural_key=shastra_author.natural_key,
                display_name=shastra_author.display_name,
                kind=shastra_author.kind,
            ) if shastra_author else None,
            anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in shastra_anuyogas],
        ) if shastra else None,
        teekakar=AuthorSummary(
            id=teekakar.id,
            natural_key=teekakar.natural_key,
            display_name=teekakar.display_name,
            kind=teekakar.kind,
        ) if teekakar else None,
        similarity=similarity,
    )


@router.get("/teekas", response_model=TeekaListResponse)
async def list_teekas(
    shastra_id: uuid.UUID | None = None,
    teekakar_id: uuid.UUID | None = None,
    q: str | None = None,
    fuzzy: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> TeekaListResponse:
    limit, offset = lo
    if fuzzy and q is not None:
        results = await svc.fuzzy_search_teekas(session, q, limit)
        items = []
        for t, sim in results:
            detail = await svc.get_detail(session, t)
            items.append(_build_teeka_summary(t, detail, similarity=sim))
        return TeekaListResponse(
            items=items,
            pagination=Pagination(total=len(items), limit=min(limit, 50), offset=0),
        )
    teekas, total = await svc.list_teekas(session, limit, offset, shastra_id, teekakar_id, q)
    items = []
    for t in teekas:
        detail = await svc.get_detail(session, t)
        items.append(_build_teeka_summary(t, detail))
    return TeekaListResponse(
        items=items,
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.get("/teekas/{ident}", response_model=TeekaResponse)
async def get_teeka(
    ident: str,
    session: AsyncSession = Depends(get_session),
) -> TeekaResponse:
    teeka = await svc.get_by_ident(session, ident)
    if teeka is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Teeka '{ident}' not found"})
    detail = await svc.get_detail(session, teeka)
    return _build_teeka_response(detail)


@router.get("/teekas/{ident}/publications", response_model=PublicationListResponse)
async def list_publications_for_teeka(
    ident: str,
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> PublicationListResponse:
    teeka = await svc.get_by_ident(session, ident)
    if teeka is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Teeka '{ident}' not found"})
    limit, offset = lo
    pubs, total = await pub_svc.list_by_teeka(session, teeka.id, limit, offset)
    from ..schemas.common import TeekaSummary
    teeka_summary = TeekaSummary(id=teeka.id, natural_key=teeka.natural_key)
    items = [
        PublicationResponse(
            id=p.id,
            natural_key=p.natural_key,
            teeka=teeka_summary,
            publisher_id=p.publisher_id,
            publisher=p.publisher,
            public_url=p.public_url,
            publisher_url=p.publisher_url,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in pubs
    ]
    return PublicationListResponse(
        items=items,
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.post("/admin/teekas", response_model=TeekaResponse, status_code=201)
async def create_teeka(
    body: TeekaCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> TeekaResponse:
    try:
        teeka = await svc.create_teeka(
            session,
            {
                "natural_key": body.natural_key,
                "shastra_id": body.shastra_id,
                "teekakar_id": body.teekakar_id,
                "publisher": [lt.model_dump() for lt in body.publisher] if body.publisher else None,
                "translator": [lt.model_dump() for lt in body.translator] if body.translator else None,
                "editor": [lt.model_dump() for lt in body.editor] if body.editor else None,
                "cataloguesearch_shastra_id": body.cataloguesearch_shastra_id,
                "public_url": body.public_url,
                "publisher_url": body.publisher_url,
            },
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, detail={"code": "conflict", "message": "natural_key already exists"})
    detail = await svc.get_detail(session, teeka)
    return _build_teeka_response(detail)


@router.patch("/admin/teekas/{teeka_id}", response_model=TeekaResponse)
async def update_teeka(
    teeka_id: str,
    body: TeekaUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> TeekaResponse:
    teeka = await svc.get_by_ident(session, teeka_id)
    if teeka is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Teeka not found"})
    patch: dict = {}
    if body.shastra_id is not None:
        patch["shastra_id"] = body.shastra_id
    if body.teekakar_id is not None:
        patch["teekakar_id"] = body.teekakar_id
    if body.publisher is not None:
        patch["publisher"] = [lt.model_dump() for lt in body.publisher]
    if body.translator is not None:
        patch["translator"] = [lt.model_dump() for lt in body.translator]
    if body.editor is not None:
        patch["editor"] = [lt.model_dump() for lt in body.editor]
    if body.cataloguesearch_shastra_id is not None:
        patch["cataloguesearch_shastra_id"] = body.cataloguesearch_shastra_id
    if body.public_url is not None:
        patch["public_url"] = body.public_url
    if body.publisher_url is not None:
        patch["publisher_url"] = body.publisher_url
    teeka = await svc.update_teeka(session, teeka, patch)
    await session.commit()
    detail = await svc.get_detail(session, teeka)
    return _build_teeka_response(detail)
