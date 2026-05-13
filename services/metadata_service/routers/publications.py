from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_session, require_admin
from ..schemas.common import Pagination, TeekaSummary
from ..schemas.publications import (
    PublicationCreate,
    PublicationListResponse,
    PublicationResponse,
    PublicationUpdate,
)
from ..services import publications as svc

router = APIRouter(prefix="/v1", tags=["publications"])


def _limit_offset(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset


@router.get("/publications", response_model=PublicationListResponse)
async def list_publications(
    teeka_id: str | None = None,
    publisher_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> PublicationListResponse:
    import uuid
    limit, offset = lo
    tid = uuid.UUID(teeka_id) if teeka_id else None
    pubs, total = await svc.list_publications(session, limit, offset, tid, publisher_id)
    items = []
    for p in pubs:
        teeka = await svc.get_teeka_for(session, p)
        items.append(PublicationResponse(
            id=p.id,
            natural_key=p.natural_key,
            teeka=TeekaSummary(id=teeka.id, natural_key=teeka.natural_key) if teeka else None,
            publisher_id=p.publisher_id,
            publisher=p.publisher,
            public_url=p.public_url,
            publisher_url=p.publisher_url,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))
    return PublicationListResponse(
        items=items,
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.get("/publications/{ident}", response_model=PublicationResponse)
async def get_publication(
    ident: str,
    session: AsyncSession = Depends(get_session),
) -> PublicationResponse:
    pub = await svc.get_by_ident(session, ident)
    if pub is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Publication '{ident}' not found"})
    teeka = await svc.get_teeka_for(session, pub)
    return PublicationResponse(
        id=pub.id,
        natural_key=pub.natural_key,
        teeka=TeekaSummary(id=teeka.id, natural_key=teeka.natural_key) if teeka else None,
        publisher_id=pub.publisher_id,
        publisher=pub.publisher,
        public_url=pub.public_url,
        publisher_url=pub.publisher_url,
        created_at=pub.created_at,
        updated_at=pub.updated_at,
    )


@router.post("/admin/publications", response_model=PublicationResponse, status_code=201)
async def create_publication(
    body: PublicationCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> PublicationResponse:
    try:
        pub = await svc.create_publication(
            session,
            {
                "natural_key": body.natural_key,
                "teeka_id": body.teeka_id,
                "publisher_id": body.publisher_id,
                "publisher": [lt.model_dump() for lt in body.publisher] if body.publisher else None,
                "public_url": body.public_url,
                "publisher_url": body.publisher_url,
            },
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, detail={"code": "conflict", "message": "natural_key already exists"})
    teeka = await svc.get_teeka_for(session, pub)
    return PublicationResponse(
        id=pub.id,
        natural_key=pub.natural_key,
        teeka=TeekaSummary(id=teeka.id, natural_key=teeka.natural_key) if teeka else None,
        publisher_id=pub.publisher_id,
        publisher=pub.publisher,
        public_url=pub.public_url,
        publisher_url=pub.publisher_url,
        created_at=pub.created_at,
        updated_at=pub.updated_at,
    )


@router.patch("/admin/publications/{pub_id}", response_model=PublicationResponse)
async def update_publication(
    pub_id: str,
    body: PublicationUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> PublicationResponse:
    pub = await svc.get_by_ident(session, pub_id)
    if pub is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Publication not found"})
    patch: dict = {}
    if body.teeka_id is not None:
        patch["teeka_id"] = body.teeka_id
    if body.publisher_id is not None:
        patch["publisher_id"] = body.publisher_id
    if body.publisher is not None:
        patch["publisher"] = [lt.model_dump() for lt in body.publisher]
    if body.public_url is not None:
        patch["public_url"] = body.public_url
    if body.publisher_url is not None:
        patch["publisher_url"] = body.publisher_url
    pub = await svc.update_publication(session, pub, patch)
    await session.commit()
    teeka = await svc.get_teeka_for(session, pub)
    return PublicationResponse(
        id=pub.id,
        natural_key=pub.natural_key,
        teeka=TeekaSummary(id=teeka.id, natural_key=teeka.natural_key) if teeka else None,
        publisher_id=pub.publisher_id,
        publisher=pub.publisher,
        public_url=pub.public_url,
        publisher_url=pub.publisher_url,
        created_at=pub.created_at,
        updated_at=pub.updated_at,
    )
