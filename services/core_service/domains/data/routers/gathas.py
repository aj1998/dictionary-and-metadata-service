from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ....deps import get_mongo_db, get_session
from ..schemas.common import Pagination, ShastraRef
from ..schemas.gathas import GathaDetail, GathaListResponse, GathaSummary
from ..services import gathas as svc

router = APIRouter(prefix="/v1", tags=["gathas"])

_CACHE_CONTROL = "public, max-age=60"

_ALL_INCLUDE = {"teeka_mapping", "teeka_sanskrit", "teeka_hindi", "teeka_bhaavarth", "kalashas"}


def _parse_include(include: str | None) -> set[str]:
    if not include:
        return set()
    return {v.strip() for v in include.split(",") if v.strip() in _ALL_INCLUDE}


def parse_gatha_path_param(shastra_nk: str, raw: str) -> dict:
    """Map URL path segment (e.g. '1,2') to identifier_values dict for compound shastras."""
    from jain_kb_common.shastra_identifiers import get_identifier_fields

    fields = get_identifier_fields(shastra_nk, "gatha")
    if not fields:
        return {"__legacy__": raw}
    parts = raw.split(",")
    if len(parts) != len(fields):
        raise HTTPException(
            status_code=400,
            detail=f"expected {len(fields)} values for {fields}, got {len(parts)}",
        )
    return dict(zip(fields, parts))


def gatha_nk_for_request(shastra_nk: str, raw: str) -> str:
    """Resolve URL path segment to the full Postgres natural key."""
    from jain_kb_common.shastra_identifiers import build_compound_suffix, get_identifier_fields

    fields = get_identifier_fields(shastra_nk, "gatha")
    if not fields:
        return f"{shastra_nk}:गाथा:{raw}"
    values = parse_gatha_path_param(shastra_nk, raw)
    suffix = build_compound_suffix(shastra_nk, values, kind="gatha")
    if not suffix:
        raise HTTPException(status_code=400, detail="could not build compound NK")
    return f"{shastra_nk}:{suffix}"


def _compact_for_gatha(shastra_nk: str, gatha) -> str:
    """Return the URL-path compact form for a gatha (e.g. '1,2' or '8')."""
    from jain_kb_common.shastra_identifiers import (
        extract_identifier_values_from_suffix,
        get_identifier_fields,
    )

    fields = get_identifier_fields(shastra_nk, "gatha")
    if not fields:
        return gatha.gatha_number
    suffix = gatha.natural_key[len(shastra_nk) + 1:]
    vals = extract_identifier_values_from_suffix(shastra_nk, suffix)
    if not vals:
        return gatha.gatha_number
    return ",".join(vals.get(f, "") for f in fields)


def _build_identifier_block(shastra_nk: str, gatha) -> dict:
    """Build the 'identifier' response block for a gatha detail response."""
    from jain_kb_common.shastra_identifiers import (
        canonical_segment_name,
        extract_identifier_values_from_suffix,
        get_identifier_fields,
    )

    fields = get_identifier_fields(shastra_nk, "gatha")
    if not fields:
        return {
            "fields": [{"name": "गाथा", "label": "गाथा", "value": gatha.gatha_number}],
            "compact": gatha.gatha_number,
            "is_compound": False,
        }

    suffix = gatha.natural_key[len(shastra_nk) + 1:]
    vals = extract_identifier_values_from_suffix(shastra_nk, suffix)
    if not vals:
        return {"fields": [], "compact": gatha.gatha_number, "is_compound": True}

    field_entries = []
    compact_parts = []
    for f in fields:
        val = vals.get(f, "")
        field_entries.append({
            "name": f,
            "label": canonical_segment_name(shastra_nk, f),
            "value": val,
        })
        compact_parts.append(val)

    return {
        "fields": field_entries,
        "compact": ",".join(compact_parts),
        "is_compound": True,
    }


@router.get("/gathas", response_model=GathaListResponse)
async def list_gathas(
    response: Response,
    shastra_id: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> GathaListResponse:
    items, total = await svc.list_gathas(session, limit, offset, shastra_id=shastra_id, q=q)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    from jain_kb_common.db.postgres.shastras import Shastra
    result = []
    shastra_cache: dict = {}
    for g in items:
        if g.shastra_id not in shastra_cache:
            s = await session.get(Shastra, g.shastra_id)
            shastra_cache[g.shastra_id] = s
        s = shastra_cache[g.shastra_id]
        if s is None:
            continue
        result.append(GathaSummary(
            id=g.id,
            natural_key=g.natural_key,
            gatha_number=g.gatha_number,
            shastra=ShastraRef(natural_key=s.natural_key, title=s.title),
            adhikaar=g.adhikaar,
            heading=g.heading,
        ))

    return GathaListResponse(
        pagination=Pagination(total=total, limit=limit, offset=offset),
        items=result,
    )


@router.get("/gathas/{ident}")
async def get_gatha(
    ident: str,
    response: Response,
    include: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> dict:
    gatha = await svc.get_by_ident(session, ident)
    if gatha is None:
        raise HTTPException(404, detail={"code": "not_found", "message": f"Gatha '{ident}' not found"})

    inc = _parse_include(include)
    detail = await svc.get_detail(session, mongo, gatha, inc)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    shastra = detail["shastra"]
    out: dict = {
        "id": gatha.id,
        "natural_key": gatha.natural_key,
        "gatha_number": gatha.gatha_number,
        "prakrit_verse_marker": gatha.prakrit_verse_marker,
        "shastra": ShastraRef(natural_key=shastra.natural_key, title=shastra.title).model_dump() if shastra else {"natural_key": "", "title": []},
        "adhikaar": gatha.adhikaar or [],
        "heading": gatha.heading or [],
        "prakrit": detail.get("prakrit"),
        "sanskrit": detail.get("sanskrit"),
        "hindi_chhand": detail.get("hindi_chhand", []),
        "word_meanings": detail.get("word_meanings"),
    }

    if "teeka_mapping" in inc:
        out["teeka_mapping"] = detail.get("teeka_mapping", [])
    if "teeka_sanskrit" in inc:
        out["teeka_sanskrit"] = detail.get("teeka_sanskrit", [])
    if "teeka_hindi" in inc:
        out["teeka_hindi"] = detail.get("teeka_hindi", [])
    if "teeka_bhaavarth" in inc:
        out["teeka_bhaavarth"] = detail.get("teeka_bhaavarth", [])
    if "kalashas" in inc:
        out["kalashas"] = detail.get("kalashas", [])

    return out


@router.get("/shastras/{shastra_nk}/gathas/{raw_id}/adjacent")
async def get_adjacent_gatha(
    shastra_nk: str,
    raw_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> dict:
    """Return prev/next gathas adjacent to the given gatha (compound-aware, numerically sorted)."""
    full_nk = gatha_nk_for_request(shastra_nk, raw_id)
    prev_g, next_g = await svc.get_adjacent_gathas(session, shastra_nk, full_nk)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    def _adjacent_item(g) -> dict | None:
        if g is None:
            return None
        return {
            "natural_key": g.natural_key,
            "compact": _compact_for_gatha(shastra_nk, g),
            "gatha_number": g.gatha_number,
        }

    return {
        "shastra_nk": shastra_nk,
        "current_nk": full_nk,
        "previous": _adjacent_item(prev_g),
        "next": _adjacent_item(next_g),
    }


@router.get("/shastras/{shastra_nk}/gathas/{raw_id}")
async def get_gatha_by_path(
    shastra_nk: str,
    raw_id: str,
    response: Response,
    include: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    mongo: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> dict:
    """Fetch a gatha by shastra NK + compact path segment (e.g. '1,2' or '8')."""
    full_nk = gatha_nk_for_request(shastra_nk, raw_id)

    gatha = await svc.get_by_ident(session, full_nk)
    if gatha is None:
        raise HTTPException(
            404,
            detail={"code": "not_found", "message": f"Gatha '{full_nk}' not found"},
        )

    inc = _parse_include(include)
    detail = await svc.get_detail(session, mongo, gatha, inc)
    response.headers["Cache-Control"] = _CACHE_CONTROL

    shastra = detail["shastra"]
    out: dict = {
        "id": str(gatha.id),
        "natural_key": gatha.natural_key,
        "gatha_number": gatha.gatha_number,
        "prakrit_verse_marker": gatha.prakrit_verse_marker,
        "shastra": ShastraRef(natural_key=shastra.natural_key, title=shastra.title).model_dump() if shastra else {"natural_key": "", "title": []},
        "adhikaar": gatha.adhikaar or [],
        "heading": gatha.heading or [],
        "prakrit": detail.get("prakrit"),
        "sanskrit": detail.get("sanskrit"),
        "hindi_chhand": detail.get("hindi_chhand", []),
        "word_meanings": detail.get("word_meanings"),
        "identifier": _build_identifier_block(shastra_nk, gatha),
    }

    if "teeka_mapping" in inc:
        out["teeka_mapping"] = detail.get("teeka_mapping", [])
    if "teeka_sanskrit" in inc:
        out["teeka_sanskrit"] = detail.get("teeka_sanskrit", [])
    if "teeka_hindi" in inc:
        out["teeka_hindi"] = detail.get("teeka_hindi", [])
    if "teeka_bhaavarth" in inc:
        out["teeka_bhaavarth"] = detail.get("teeka_bhaavarth", [])
    if "kalashas" in inc:
        out["kalashas"] = detail.get("kalashas", [])

    return out
