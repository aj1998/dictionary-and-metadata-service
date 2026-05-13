from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_session, require_admin
from ..schemas.common import AnuyogaSummary, AuthorSummary, Pagination, ShastraSummary
from ..schemas.pravachans import (
    PravachanCreate,
    PravachanListResponse,
    PravachanResponse,
    PravachanUpdate,
)
from ..services import pravachans as svc

router = APIRouter(prefix="/v1", tags=["pravachans"])


def _limit_offset(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset


async def _build_response(session, p) -> PravachanResponse:  # type: ignore[no-untyped-def]
    shastra = await svc.get_shastra_for(session, p)
    shastra_summary = None
    if shastra:
        shastra_author = await svc.get_shastra_author(session, shastra)
        shastra_anuyogas = await svc.get_shastra_anuyogas(session, shastra)
        shastra_summary = ShastraSummary(
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
        )
    speaker = await svc.get_speaker_for(session, p)
    return PravachanResponse(
        id=p.id,
        natural_key=p.natural_key,
        title=p.title,
        shastra=shastra_summary,
        speaker=AuthorSummary(
            id=speaker.id,
            natural_key=speaker.natural_key,
            display_name=speaker.display_name,
            kind=speaker.kind,
        ) if speaker else None,
        publisher=p.publisher,
        translator=p.translator,
        editor=p.editor,
        public_url=p.public_url,
        publisher_url=p.publisher_url,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/pravachans", response_model=PravachanListResponse)
async def list_pravachans(
    shastra_id: uuid.UUID | None = None,
    speaker_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> PravachanListResponse:
    limit, offset = lo
    pravachans, total = await svc.list_pravachans(session, limit, offset, shastra_id, speaker_id)
    items = [await _build_response(session, p) for p in pravachans]
    return PravachanListResponse(
        items=items,
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.get("/pravachans/{ident}", response_model=PravachanResponse)
async def get_pravachan(
    ident: str,
    session: AsyncSession = Depends(get_session),
) -> PravachanResponse:
    p = await svc.get_by_ident(session, ident)
    if p is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Pravachan '{ident}' not found"})
    return await _build_response(session, p)


@router.post("/admin/pravachans", response_model=PravachanResponse, status_code=201)
async def create_pravachan(
    body: PravachanCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> PravachanResponse:
    try:
        p = await svc.create_pravachan(
            session,
            {
                "natural_key": body.natural_key,
                "title": [lt.model_dump() for lt in body.title],
                "shastra_id": body.shastra_id,
                "speaker_id": body.speaker_id,
                "publisher": [lt.model_dump() for lt in body.publisher] if body.publisher else None,
                "translator": [lt.model_dump() for lt in body.translator] if body.translator else None,
                "editor": [lt.model_dump() for lt in body.editor] if body.editor else None,
                "public_url": body.public_url,
                "publisher_url": body.publisher_url,
            },
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, detail={"code": "conflict", "message": "natural_key already exists"})
    return await _build_response(session, p)


@router.patch("/admin/pravachans/{pravachan_id}", response_model=PravachanResponse)
async def update_pravachan(
    pravachan_id: str,
    body: PravachanUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> PravachanResponse:
    p = await svc.get_by_ident(session, pravachan_id)
    if p is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Pravachan not found"})
    patch: dict = {}
    if body.title is not None:
        patch["title"] = [lt.model_dump() for lt in body.title]
    if body.shastra_id is not None:
        patch["shastra_id"] = body.shastra_id
    if body.speaker_id is not None:
        patch["speaker_id"] = body.speaker_id
    if body.publisher is not None:
        patch["publisher"] = [lt.model_dump() for lt in body.publisher]
    if body.translator is not None:
        patch["translator"] = [lt.model_dump() for lt in body.translator]
    if body.editor is not None:
        patch["editor"] = [lt.model_dump() for lt in body.editor]
    if body.public_url is not None:
        patch["public_url"] = body.public_url
    if body.publisher_url is not None:
        patch["publisher_url"] = body.publisher_url
    p = await svc.update_pravachan(session, p, patch)
    await session.commit()
    return await _build_response(session, p)
