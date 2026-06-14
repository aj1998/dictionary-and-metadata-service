from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ....config import settings
from ....deps import get_session, require_admin
from ..schemas.common import AnuyogaSummary, AuthorSummary, Pagination
from ..schemas.shastras import (
    ShastraCreate,
    ShastraListResponse,
    ShastraResponse,
    ShastraStats,
    ShastraSummaryResponse,
    ShastraUpdate,
)
from ..schemas.teekas import TeekaListResponse, TeekaSummaryResponse
from ..services import shastras as svc
from ..services import teekas as teeka_svc
from ..services.shastra_pdf import (
    get_shastra_pdf_offsets,
    get_shastra_pdf_offsets_with_availability,
    resolve_pdf_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["shastras"])


def _limit_offset(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset


def _build_shastra_summary(detail: dict) -> ShastraSummaryResponse:
    s = detail["shastra"]
    author = detail.get("author")
    anuyogas = detail.get("anuyogas", [])
    return ShastraSummaryResponse(
        id=s.id,
        natural_key=s.natural_key,
        title=s.title,
        author=AuthorSummary(
            id=author.id,
            natural_key=author.natural_key,
            display_name=author.display_name,
            kind=author.kind,
        ) if author else None,
        anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in anuyogas],
    )


@router.get("/shastras", response_model=ShastraListResponse)
async def list_shastras(
    author_id: uuid.UUID | None = None,
    anuyoga: str | None = None,
    q: str | None = None,
    fuzzy: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> ShastraListResponse:
    limit, offset = lo
    if fuzzy and q is not None:
        results = await svc.fuzzy_search_shastras(session, q, limit)
        items = []
        for s, sim in results:
            author = await svc.get_author_for(session, s)
            anuyogas_list = await svc.get_anuyogas_for(session, s)
            items.append(ShastraSummaryResponse(
                id=s.id,
                natural_key=s.natural_key,
                title=s.title,
                author=AuthorSummary(
                    id=author.id,
                    natural_key=author.natural_key,
                    display_name=author.display_name,
                    kind=author.kind,
                ) if author else None,
                anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in anuyogas_list],
                similarity=sim,
            ))
        return ShastraListResponse(
            items=items,
            pagination=Pagination(total=len(items), limit=min(limit, 50), offset=0),
        )
    shastras, total = await svc.list_shastras(session, limit, offset, author_id, anuyoga, q)
    items = []
    for s in shastras:
        author = await svc.get_author_for(session, s)
        anuyogas_list = await svc.get_anuyogas_for(session, s)
        items.append(ShastraSummaryResponse(
            id=s.id,
            natural_key=s.natural_key,
            title=s.title,
            author=AuthorSummary(
                id=author.id,
                natural_key=author.natural_key,
                display_name=author.display_name,
                kind=author.kind,
            ) if author else None,
            anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in anuyogas_list],
        ))
    return ShastraListResponse(
        items=items,
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.api_route("/shastras/{ident}/pdf-file", methods=["GET", "HEAD"])
async def get_shastra_pdf_file(
    ident: str,
    pustak: str | None = Query(None),
) -> FileResponse:
    if settings.ORIGINAL_SHASTRA_PDF_DIR is None:
        raise HTTPException(503, detail={"code": "unavailable", "message": "PDF directory not configured"})

    resolved = resolve_pdf_path(settings.ORIGINAL_SHASTRA_PDF_DIR, ident, pustak)
    if resolved is None:
        raise HTTPException(400, detail={"code": "invalid_param", "message": "Invalid shastra_nk or pustak"})

    if not resolved.exists():
        logger.warning("PDF not found: %s (shastra_nk=%r pustak=%r)", resolved, ident, pustak)
        raise HTTPException(404, detail={"code": "not_found", "message": "PDF file not found"})

    file_size = resolved.stat().st_size
    logger.info("Serving PDF: %s size=%d shastra_nk=%r pustak=%r", resolved, file_size, ident, pustak)

    return FileResponse(
        path=str(resolved),
        media_type="application/pdf",
        filename=resolved.name,
        headers={
            "Content-Disposition": f'inline; filename="{resolved.name}"',
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/shastras/{ident}/pdf-offsets")
async def get_shastra_pdf_offsets_endpoint(ident: str) -> dict:
    """Return PDF page offsets for a shastra from the shastra.json registry.

    This does not require the shastra to be ingested in the DB — it serves
    the UI's OriginalShastraLink which only needs offset metadata.
    """
    offset, pustak, available = get_shastra_pdf_offsets_with_availability(ident)
    return {
        "pdf_page_offset": offset,
        "pustak_offsets": pustak,
        "available": available,
    }


@router.get("/shastras/{ident}", response_model=ShastraResponse)
async def get_shastra(
    ident: str,
    session: AsyncSession = Depends(get_session),
) -> ShastraResponse:
    shastra = await svc.get_by_ident(session, ident)
    if shastra is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Shastra '{ident}' not found"})
    detail = await svc.get_detail(session, shastra)
    author = detail["author"]
    pdf_page_offset, pustak_offsets = get_shastra_pdf_offsets(shastra.natural_key)
    return ShastraResponse(
        id=shastra.id,
        natural_key=shastra.natural_key,
        title=shastra.title,
        author=AuthorSummary(
            id=author.id,
            natural_key=author.natural_key,
            display_name=author.display_name,
            kind=author.kind,
        ) if author else None,
        anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in detail["anuyogas"]],
        source_url=shastra.source_url,
        description=shastra.description,
        stats=ShastraStats(
            total_gathas=detail["total_gathas"],
            total_teekas=detail["total_teekas"],
        ),
        created_at=shastra.created_at,
        updated_at=shastra.updated_at,
        pdf_page_offset=pdf_page_offset,
        pustak_offsets=pustak_offsets,
    )


@router.get("/shastras/{ident}/teekas", response_model=TeekaListResponse)
async def list_teekas_for_shastra(
    ident: str,
    session: AsyncSession = Depends(get_session),
    lo: tuple[int, int] = Depends(_limit_offset),
) -> TeekaListResponse:
    shastra = await svc.get_by_ident(session, ident)
    if shastra is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Shastra '{ident}' not found"})
    limit, offset = lo
    teekas, total = await teeka_svc.list_by_shastra(session, shastra.id, limit, offset)
    items = []
    for t in teekas:
        teekakar = None
        if t.teekakar_id:
            from jain_kb_common.db.postgres.authors import Author
            teekakar_obj = await session.get(Author, t.teekakar_id)
            if teekakar_obj:
                teekakar = AuthorSummary(
                    id=teekakar_obj.id,
                    natural_key=teekakar_obj.natural_key,
                    display_name=teekakar_obj.display_name,
                    kind=teekakar_obj.kind,
                )
        from ..schemas.common import ShastraSummary
        items.append(TeekaSummaryResponse(
            id=t.id,
            natural_key=t.natural_key,
            shastra=ShastraSummary(
                id=shastra.id,
                natural_key=shastra.natural_key,
                title=shastra.title,
            ),
            teekakar=teekakar,
        ))
    return TeekaListResponse(
        items=items,
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.post("/admin/shastras", response_model=ShastraResponse, status_code=201)
async def create_shastra(
    body: ShastraCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> ShastraResponse:
    try:
        shastra = await svc.create_shastra(
            session,
            {
                "natural_key": body.natural_key,
                "title": [lt.model_dump() for lt in body.title],
                "author_id": body.author_id,
                "source_url": body.source_url,
                "description": [lt.model_dump() for lt in body.description] if body.description else None,
            },
            body.anuyoga_ids,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, detail={"code": "conflict", "message": "natural_key already exists"})
    detail = await svc.get_detail(session, shastra)
    author = detail["author"]
    pdf_page_offset, pustak_offsets = get_shastra_pdf_offsets(shastra.natural_key)
    return ShastraResponse(
        id=shastra.id,
        natural_key=shastra.natural_key,
        title=shastra.title,
        author=AuthorSummary(
            id=author.id,
            natural_key=author.natural_key,
            display_name=author.display_name,
            kind=author.kind,
        ) if author else None,
        anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in detail["anuyogas"]],
        source_url=shastra.source_url,
        description=shastra.description,
        stats=ShastraStats(total_gathas=detail["total_gathas"], total_teekas=detail["total_teekas"]),
        created_at=shastra.created_at,
        updated_at=shastra.updated_at,
        pdf_page_offset=pdf_page_offset,
        pustak_offsets=pustak_offsets,
    )


@router.patch("/admin/shastras/{shastra_id}", response_model=ShastraResponse)
async def update_shastra(
    shastra_id: str,
    body: ShastraUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> ShastraResponse:
    shastra = await svc.get_by_ident(session, shastra_id)
    if shastra is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Shastra not found"})
    patch: dict = {}
    if body.title is not None:
        patch["title"] = [lt.model_dump() for lt in body.title]
    if body.author_id is not None:
        patch["author_id"] = body.author_id
    if body.source_url is not None:
        patch["source_url"] = body.source_url
    if body.description is not None:
        patch["description"] = [lt.model_dump() for lt in body.description]
    shastra = await svc.update_shastra(session, shastra, patch, body.anuyoga_ids)
    await session.commit()
    detail = await svc.get_detail(session, shastra)
    author = detail["author"]
    pdf_page_offset, pustak_offsets = get_shastra_pdf_offsets(shastra.natural_key)
    return ShastraResponse(
        id=shastra.id,
        natural_key=shastra.natural_key,
        title=shastra.title,
        author=AuthorSummary(
            id=author.id,
            natural_key=author.natural_key,
            display_name=author.display_name,
            kind=author.kind,
        ) if author else None,
        anuyogas=[AnuyogaSummary(kind=a.kind, display_name=a.display_name) for a in detail["anuyogas"]],
        source_url=shastra.source_url,
        description=shastra.description,
        stats=ShastraStats(total_gathas=detail["total_gathas"], total_teekas=detail["total_teekas"]),
        created_at=shastra.created_at,
        updated_at=shastra.updated_at,
        pdf_page_offset=pdf_page_offset,
        pustak_offsets=pustak_offsets,
    )
