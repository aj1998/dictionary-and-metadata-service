from __future__ import annotations

import logging
import uuid
from typing import Any, TypedDict

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.anuyogas import Anuyoga
from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.shastras import Shastra, ShastrasAnuyoga

logger = logging.getLogger(__name__)


class ShastraDetail(TypedDict):
    shastra: Shastra
    author: Author | None
    anuyogas: list[Anuyoga]
    total_gathas: int
    total_teekas: int


async def get_by_ident(session: AsyncSession, ident: str) -> Shastra | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Shastra, uid)
    except ValueError:
        result = await session.execute(select(Shastra).where(Shastra.natural_key == ident))
        return result.scalar_one_or_none()


async def get_detail(session: AsyncSession, shastra: Shastra) -> ShastraDetail:
    author: Author | None = None
    if shastra.author_id:
        author = await session.get(Author, shastra.author_id)

    anuyoga_rows = await session.execute(
        select(Anuyoga)
        .join(ShastrasAnuyoga, ShastrasAnuyoga.anuyoga_id == Anuyoga.id)
        .where(ShastrasAnuyoga.shastra_id == shastra.id)
    )
    anuyogas = list(anuyoga_rows.scalars())

    total_gathas = await session.scalar(
        text("SELECT COUNT(*) FROM gathas WHERE shastra_id = :sid").bindparams(sid=shastra.id)
    ) or 0
    total_teekas = await session.scalar(
        text("SELECT COUNT(*) FROM teekas WHERE shastra_id = :sid").bindparams(sid=shastra.id)
    ) or 0

    return ShastraDetail(
        shastra=shastra,
        author=author,
        anuyogas=anuyogas,
        total_gathas=int(total_gathas),
        total_teekas=int(total_teekas),
    )


async def list_shastras(
    session: AsyncSession,
    limit: int,
    offset: int,
    author_id: uuid.UUID | None = None,
    anuyoga: str | None = None,
    q: str | None = None,
) -> tuple[list[Shastra], int]:
    stmt = select(Shastra)
    cnt_stmt = select(func.count()).select_from(Shastra)

    if author_id is not None:
        stmt = stmt.where(Shastra.author_id == author_id)
        cnt_stmt = cnt_stmt.where(Shastra.author_id == author_id)

    if anuyoga is not None:
        anuyoga_sub = (
            select(ShastrasAnuyoga.shastra_id)
            .join(Anuyoga, Anuyoga.id == ShastrasAnuyoga.anuyoga_id)
            .where(Anuyoga.kind == anuyoga)
        )
        stmt = stmt.where(Shastra.id.in_(anuyoga_sub))
        cnt_stmt = cnt_stmt.where(Shastra.id.in_(anuyoga_sub))

    if q is not None:
        trgm = text("shastra_title_trgm(:q, title)").bindparams(q=q)
        # Use a safe jsonb cast for pg_trgm similarity on JSON text
        # Cast title JSONB to text and use similarity
        like_filter = text(
            "title::text ILIKE :pattern"
        ).bindparams(pattern=f"%{q}%")
        stmt = stmt.where(like_filter)
        cnt_stmt = cnt_stmt.where(like_filter)

    total = await session.scalar(cnt_stmt)
    rows = await session.execute(stmt.order_by(Shastra.natural_key).limit(limit).offset(offset))
    return list(rows.scalars()), int(total or 0)


_FUZZY_MIN_SIMILARITY = 0.25
_FUZZY_HARD_CAP = 50


class FuzzyShastraMatch(TypedDict):
    shastra: Shastra
    similarity: float
    # Why this shastra surfaced: "name" (own title/nk), "author", "teeka", or
    # "teekakar" (a teeka's commentator).
    match_field: str
    # Human-readable detail for the badge — the matched teeka or teekakar name,
    # or None (author name is already available on the response's author field).
    match_detail: str | None


async def fuzzy_search_shastras(
    session: AsyncSession,
    q: str,
    limit: int,
    min_similarity: float = _FUZZY_MIN_SIMILARITY,
) -> list[FuzzyShastraMatch]:
    """pg_trgm similarity search over a shastra and its related metadata.

    A shastra matches on any of:
      - its own ``natural_key`` / ``title`` text;
      - any of its teekas' names (so searching a teeka name like ``राजवार्तिक``
        surfaces the parent shastra ``तत्त्वार्थसूत्र``). The teeka name is taken
        both from the full ``natural_key`` and from the part after ``:`` so the
        bare name matches without the shastra prefix diluting the trigram score;
      - any of its teekas' teekakar (commentator) names (so searching
        ``अकलंक`` surfaces ``तत्त्वार्थसूत्र``, whose राजवार्तिक teeka is by आचार्य
        अकलंकदेव);
      - its author's ``natural_key`` / ``display_name`` text (so searching an
        author name like ``कुन्दकुन्द`` surfaces all of their shastras).
    """
    capped = min(limit, _FUZZY_HARD_CAP)
    sql = text("""
        WITH teeka_sim AS (
            SELECT DISTINCT ON (shastra_id) shastra_id, sim, kind, detail
            FROM (
                SELECT
                    t.shastra_id,
                    GREATEST(name_sim, teekakar_sim) AS sim,
                    CASE WHEN teekakar_sim > name_sim THEN 'teekakar' ELSE 'teeka' END AS kind,
                    CASE WHEN teekakar_sim > name_sim THEN teekakar_name ELSE teeka_name END AS detail
                FROM (
                    SELECT
                        t.shastra_id,
                        GREATEST(
                            similarity(t.natural_key, :q),
                            similarity(split_part(t.natural_key, ':', 2), :q)
                        ) AS name_sim,
                        COALESCE(NULLIF(split_part(t.natural_key, ':', 2), ''), t.natural_key) AS teeka_name,
                        COALESCE(GREATEST(
                            similarity(ta.natural_key, :q),
                            similarity(ta.display_text, :q),
                            -- word_similarity matches a name fragment within a
                            -- longer name (अकलंक → "आचार्य अकलंकदेव"); gate at
                            -- 0.5 so coincidental single-syllable overlaps
                            -- (कुन्दकुन्द vs नेमिचंद्र ≈ 0.4) don't leak in.
                            (CASE WHEN word_similarity(:q, ta.display_text) >= 0.5
                                  THEN word_similarity(:q, ta.display_text) ELSE 0 END)
                        ), 0) AS teekakar_sim,
                        ta.display_text AS teekakar_name
                    FROM teekas t
                    LEFT JOIN LATERAL (
                        SELECT
                            au.natural_key,
                            COALESCE(
                                (SELECT string_agg(elem->>'text', ' ')
                                 FROM jsonb_array_elements(au.display_name) AS elem),
                                ''
                            ) AS display_text
                        FROM authors au
                        WHERE au.id = t.teekakar_id
                    ) ta ON TRUE
                ) t
            ) m
            ORDER BY shastra_id, sim DESC
        ),
        author_sim AS (
            SELECT
                id AS author_id,
                GREATEST(
                    similarity(natural_key, :q),
                    similarity(
                        COALESCE(
                            (SELECT string_agg(elem->>'text', ' ')
                             FROM jsonb_array_elements(display_name) AS elem),
                            ''
                        ),
                        :q
                    ),
                    -- Fragment match within a longer author name, gated at 0.5
                    -- (see teekakar_sim note) to avoid coincidental overlaps.
                    (CASE WHEN word_similarity(
                              :q,
                              COALESCE(
                                  (SELECT string_agg(elem->>'text', ' ')
                                   FROM jsonb_array_elements(display_name) AS elem),
                                  ''
                              )
                          ) >= 0.5
                          THEN word_similarity(
                              :q,
                              COALESCE(
                                  (SELECT string_agg(elem->>'text', ' ')
                                   FROM jsonb_array_elements(display_name) AS elem),
                                  ''
                              )
                          ) ELSE 0 END)
                ) AS sim
            FROM authors
        ),
        ranked AS (
            SELECT
                s.id,
                GREATEST(
                    similarity(s.natural_key, :q),
                    similarity(s.title::text, :q)
                ) AS name_sim,
                COALESCE(ts.sim, 0) AS teeka_sim,
                ts.kind AS teeka_kind,
                ts.detail AS teeka_detail,
                COALESCE(a.sim, 0) AS author_sim
            FROM shastras s
            LEFT JOIN teeka_sim ts ON ts.shastra_id = s.id
            LEFT JOIN author_sim a ON a.author_id = s.author_id
        )
        SELECT
            id::text AS id,
            GREATEST(name_sim, teeka_sim, author_sim) AS sim,
            name_sim, teeka_sim, teeka_kind, teeka_detail, author_sim
        FROM ranked
        WHERE GREATEST(name_sim, teeka_sim, author_sim) >= :min_sim
        ORDER BY sim DESC
        LIMIT :limit
    """)
    rows = list(await session.execute(sql, {"q": q, "min_sim": min_similarity, "limit": capped}))
    logger.debug("fuzzy_search_shastras q=%r min_sim=%.2f → %d rows", q, min_similarity, len(rows))
    if not rows:
        return []
    id_order = [uuid.UUID(row.id) for row in rows]
    shastra_rows = await session.execute(select(Shastra).where(Shastra.id.in_(id_order)))
    shastra_map = {s.id: s for s in shastra_rows.scalars()}

    out: list[FuzzyShastraMatch] = []
    for row in rows:
        sid = uuid.UUID(row.id)
        shastra = shastra_map.get(sid)
        if shastra is None:
            continue
        # Priority on ties: the shastra's own name wins (no badge needed), then
        # author, then teeka — so a badge only appears when the match came from
        # a related entity rather than the shastra's own title.
        name_sim = float(row.name_sim)
        author_sim = float(row.author_sim)
        teeka_sim = float(row.teeka_sim)
        if name_sim >= author_sim and name_sim >= teeka_sim:
            match_field, match_detail = "name", None
        elif author_sim >= teeka_sim:
            match_field, match_detail = "author", None
        else:
            # teeka_kind is "teeka" (matched the teeka name) or "teekakar"
            # (matched the commentator); detail carries the matched name.
            match_field, match_detail = row.teeka_kind, row.teeka_detail
        out.append(FuzzyShastraMatch(
            shastra=shastra,
            similarity=float(row.sim),
            match_field=match_field,
            match_detail=match_detail,
        ))
    return out


async def get_author_for(session: AsyncSession, shastra: Shastra) -> Author | None:
    if not shastra.author_id:
        return None
    return await session.get(Author, shastra.author_id)


async def get_anuyogas_for(session: AsyncSession, shastra: Shastra) -> list[Anuyoga]:
    rows = await session.execute(
        select(Anuyoga)
        .join(ShastrasAnuyoga, ShastrasAnuyoga.anuyoga_id == Anuyoga.id)
        .where(ShastrasAnuyoga.shastra_id == shastra.id)
    )
    return list(rows.scalars())


async def create_shastra(
    session: AsyncSession, data: dict[str, Any], anuyoga_ids: list[uuid.UUID]
) -> Shastra:
    shastra = Shastra(**data)
    session.add(shastra)
    await session.flush()
    for aid in anuyoga_ids:
        session.add(ShastrasAnuyoga(shastra_id=shastra.id, anuyoga_id=aid))
    await session.flush()
    await session.refresh(shastra)
    return shastra


async def update_shastra(
    session: AsyncSession,
    shastra: Shastra,
    data: dict[str, Any],
    anuyoga_ids: list[uuid.UUID] | None,
) -> Shastra:
    for k, v in data.items():
        setattr(shastra, k, v)
    if anuyoga_ids is not None:
        await session.execute(
            ShastrasAnuyoga.__table__.delete().where(  # type: ignore[attr-defined]
                ShastrasAnuyoga.shastra_id == shastra.id
            )
        )
        for aid in anuyoga_ids:
            session.add(ShastrasAnuyoga(shastra_id=shastra.id, anuyoga_id=aid))
    await session.flush()
    await session.refresh(shastra)
    return shastra
