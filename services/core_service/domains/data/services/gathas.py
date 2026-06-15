from __future__ import annotations

import asyncio
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import (
    GATHA_HINDI_CHHAND,
    GATHA_PRAKRIT,
    GATHA_SANSKRIT,
    GATHA_TEEKA_BHAAVARTH_HINDI,
    GATHA_TEEKA_BHAAVARTH_SHORTFONT,
    GATHA_TEEKA_HINDI,
    GATHA_TEEKA_SANSKRIT,
    GATHA_WORD_MEANINGS,
    KALASH_BHAAVARTH_HINDI,
    KALASH_BHAAVARTH_SHORTFONT,
    KALASH_HINDI,
    KALASH_SANSKRIT,
    KALASH_WORD_MEANINGS,
    TEEKA_GATHA_MAPPING,
)
from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.postgres.kalashas import Kalash
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.teekas import Teeka


async def get_adjacent_gathas(
    session: AsyncSession,
    shastra_nk: str,
    current_nk: str,
) -> tuple[Gatha | None, Gatha | None]:
    """Return (previous, next) gathas sorted numerically for both legacy and compound shastras."""
    from jain_kb_common.shastra_identifiers import (
        get_identifier_fields,
        extract_identifier_values_from_suffix,
    )

    shastra_row = await session.execute(
        select(Shastra).where(Shastra.natural_key == shastra_nk)
    )
    shastra = shastra_row.scalar_one_or_none()
    if shastra is None:
        return None, None

    result = await session.execute(
        select(Gatha).where(Gatha.shastra_id == shastra.id)
    )
    all_gathas = list(result.scalars())
    if not all_gathas:
        return None, None

    fields = get_identifier_fields(shastra_nk, "gatha")

    def _sort_key(g: Gatha) -> tuple:
        if fields:
            suffix = g.natural_key[len(shastra_nk) + 1:]
            vals = extract_identifier_values_from_suffix(shastra_nk, suffix)
            if not vals:
                return tuple(float("inf") for _ in fields)
            parts: list = []
            for f in fields:
                v = vals.get(f, "")
                try:
                    parts.append(int(v))
                except (ValueError, TypeError):
                    parts.append(float("inf"))
            return tuple(parts)
        try:
            return (int(g.gatha_number),)
        except (ValueError, TypeError):
            return (float("inf"),)

    all_gathas.sort(key=_sort_key)

    current_idx = next((i for i, g in enumerate(all_gathas) if g.natural_key == current_nk), None)
    if current_idx is None:
        return None, None

    prev_g = all_gathas[current_idx - 1] if current_idx > 0 else None
    next_g = all_gathas[current_idx + 1] if current_idx < len(all_gathas) - 1 else None
    return prev_g, next_g


async def get_by_ident(session: AsyncSession, ident: str) -> Gatha | None:
    try:
        uid = uuid.UUID(ident)
        return await session.get(Gatha, uid)
    except ValueError:
        result = await session.execute(
            select(Gatha).where(Gatha.natural_key == ident)
        )
        return result.scalar_one_or_none()


async def list_gathas(
    session: AsyncSession,
    limit: int,
    offset: int,
    shastra_id: str | None = None,
    q: str | None = None,
) -> tuple[list[Gatha], int]:
    stmt = select(Gatha)
    cnt = select(func.count()).select_from(Gatha)

    if shastra_id is not None:
        try:
            sid = uuid.UUID(shastra_id)
            stmt = stmt.where(Gatha.shastra_id == sid)
            cnt = cnt.where(Gatha.shastra_id == sid)
        except ValueError:
            from sqlalchemy import select as sa_select
            shastra_row = await session.execute(
                sa_select(Shastra).where(Shastra.natural_key == shastra_id)
            )
            s = shastra_row.scalar_one_or_none()
            if s:
                stmt = stmt.where(Gatha.shastra_id == s.id)
                cnt = cnt.where(Gatha.shastra_id == s.id)
            else:
                return [], 0

    if q is not None:
        from sqlalchemy import text as sa_text
        q_filter = sa_text(
            "gatha_number ILIKE :pat OR adhikaar::text ILIKE :pat OR heading::text ILIKE :pat"
        ).bindparams(pat=f"%{q}%")
        stmt = stmt.where(q_filter)
        cnt = cnt.where(q_filter)

    total = await session.scalar(cnt)
    rows = await session.execute(
        stmt.order_by(Gatha.natural_key).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


def _strip_id(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


async def get_detail(
    session: AsyncSession,
    mongo: AsyncIOMotorDatabase,
    gatha: Gatha,
    include: set[str],
) -> dict:
    shastra_task = session.get(Shastra, gatha.shastra_id)
    prakrit_task = mongo[GATHA_PRAKRIT].find_one({"natural_key": f"{gatha.natural_key}:prakrit"})
    sanskrit_task = mongo[GATHA_SANSKRIT].find_one({"natural_key": f"{gatha.natural_key}:sanskrit"})
    chhand_task = mongo[GATHA_HINDI_CHHAND].find(
        {"gatha_natural_key": gatha.natural_key}
    ).to_list(None)
    wm_prakrit_task = mongo[GATHA_WORD_MEANINGS].find_one(
        {"natural_key": f"{gatha.natural_key}:word_meanings:prakrit"}
    )
    wm_sanskrit_task = mongo[GATHA_WORD_MEANINGS].find_one(
        {"natural_key": f"{gatha.natural_key}:word_meanings:sanskrit"}
    )

    base_tasks = [shastra_task, prakrit_task, sanskrit_task, chhand_task, wm_prakrit_task, wm_sanskrit_task]
    include_keys = []

    if "teeka_mapping" in include:
        include_keys.append("teeka_mapping")
        base_tasks.append(
            mongo[TEEKA_GATHA_MAPPING].find({"gatha_natural_key": gatha.natural_key}).to_list(None)
        )
    # teeka_* docs use {gatha_teeka_natural_key, gatha_number} rather than a
    # gatha_natural_key field. Build a shared filter from the shastra prefix.
    # Exclude secondary-kalash extra-gatha docs (NK contains ":कलश:") — those
    # share gatha_number with a real gatha but belong to the kalashes payload.
    # Build a per-gatha teeka query. Teeka NKs are emitted as
    # `{publication_nk}:{mongo_seg}` where `mongo_seg` is either the compound
    # gatha suffix (e.g. "अधिकार:1:गाथा:001") or the leading-zero-stripped
    # bare gatha number for legacy shastras. Anchoring the regex on this
    # suffix avoids the over-match that collapsed multiple adhikaars' gatha 1
    # into a single result.
    from jain_kb_common.shastra_identifiers import get_identifier_fields as _gid_fields
    import re as _re
    if ":गाथा:" in gatha.natural_key:
        _pre_gatha = gatha.natural_key.split(":गाथा:")[0]
        _parts = _pre_gatha.split(":")
        shastra_nk_prefix = _parts[0]
        if not _gid_fields(shastra_nk_prefix, "gatha"):
            shastra_nk_prefix = _pre_gatha
        # Bare gatha number for legacy fallback / shortfont NK building.
        bare_gatha_num = gatha.natural_key.rsplit(":गाथा:", 1)[1].split(":", 1)[0]
        try:
            bare_gatha_num = str(int(bare_gatha_num))
        except ValueError:
            pass
        # mongo_seg matches the ingestion-time per-gatha segment.
        if _gid_fields(shastra_nk_prefix, "gatha"):
            mongo_seg = gatha.natural_key[len(shastra_nk_prefix) + 1:]
        else:
            mongo_seg = bare_gatha_num
    else:
        shastra_nk_prefix = ""
        bare_gatha_num = str(gatha.gatha_number)
        mongo_seg = bare_gatha_num
    teeka_query: dict = {
        "gatha_teeka_natural_key": {
            "$regex": f"^{_re.escape(shastra_nk_prefix)}:.*:{_re.escape(mongo_seg)}$"
            if shastra_nk_prefix
            else f":{_re.escape(mongo_seg)}$",
            "$not": {"$regex": ":कलश:"},
        }
    }

    if "teeka_sanskrit" in include:
        include_keys.append("teeka_sanskrit")
        base_tasks.append(
            mongo[GATHA_TEEKA_SANSKRIT].find(teeka_query).to_list(None)
        )
    if "teeka_hindi" in include:
        include_keys.append("teeka_hindi")
        base_tasks.append(
            mongo[GATHA_TEEKA_HINDI].find(teeka_query).to_list(None)
        )
    if "teeka_bhaavarth" in include:
        include_keys.append("teeka_bhaavarth")
        base_tasks.append(
            mongo[GATHA_TEEKA_BHAAVARTH_HINDI].find(teeka_query).to_list(None)
        )
        include_keys.append("__teeka_bhaavarth_sf__")
        base_tasks.append(
            mongo[GATHA_TEEKA_BHAAVARTH_SHORTFONT].find(
                {"gatha_natural_key": gatha.natural_key}
            ).to_list(None)
        )

    results = await asyncio.gather(*base_tasks)
    shastra, prakrit, sanskrit, chhand, wm_prakrit, wm_sanskrit = results[:6]
    extra_results = results[6:]

    word_meanings = {
        "prakrit": _strip_id(wm_prakrit),
        "sanskrit": _strip_id(wm_sanskrit),
    }

    chhand_clean = [_strip_id(d) for d in (chhand or [])]

    out: dict = {
        "gatha": gatha,
        "shastra": shastra,
        "prakrit": _strip_id(prakrit),
        "sanskrit": _strip_id(sanskrit),
        "hindi_chhand": chhand_clean,
        "word_meanings": word_meanings,
    }

    for key, result in zip(include_keys, extra_results):
        if not key.startswith("__"):
            out[key] = [_strip_id(d) for d in (result or [])]

    # Attach shortfont entries to each teeka_bhaavarth doc.
    # Shortfont docs are indexed by bhaavarth_natural_key which uses the Neo4j NK pattern:
    # {publication_natural_key}:गाथा:टीका:भावार्थ:{gatha_number}
    if "teeka_bhaavarth" in out and "__teeka_bhaavarth_sf__" in include_keys:
        sf_idx = include_keys.index("__teeka_bhaavarth_sf__")
        sf_docs = extra_results[sf_idx] or []
        sf_by_nk = {
            d["bhaavarth_natural_key"]: d.get("entries", [])
            for d in sf_docs
            if d.get("bhaavarth_natural_key")
        }
        for bh in out["teeka_bhaavarth"]:
            pub_nk = bh.get("publication_natural_key", "")
            bh_nk = f"{pub_nk}:गाथा:टीका:भावार्थ:{bare_gatha_num}" if pub_nk else ""
            bh["shortfont_entries"] = sf_by_nk.get(bh_nk, [])

    if "kalashas" in include:
        out["kalashas"] = await _get_kalashas_for_gatha(session, mongo, gatha)

    return out


async def _get_kalashas_for_gatha(
    session: AsyncSession,
    mongo: AsyncIOMotorDatabase,
    gatha: Gatha,
) -> list[dict]:
    rows_result = await session.execute(
        select(Kalash, Teeka.natural_key, Teeka.role)
        .join(Teeka, Kalash.teeka_id == Teeka.id)
        .where(Kalash.gatha_id == gatha.id)
        .order_by(cast(Kalash.kalash_number, Integer), Teeka.role)
    )
    rows = list(rows_result.all())
    if not rows:
        return []

    async def _fetch_kalash_docs(kalash: Kalash, teeka_nk: str, teeka_role: str | None) -> dict:
        is_secondary = teeka_role == "secondary"
        if is_secondary:
            # Secondary kalashas (e.g. Jaysenacharya's extra gathas) store content in
            # gatha_prakrit / gatha_teeka_sanskrit / gatha_teeka_bhaavarth_hindi
            pra_task = mongo[GATHA_PRAKRIT].find_one({"gatha_natural_key": kalash.natural_key})
            san_task = mongo[GATHA_TEEKA_SANSKRIT].find_one(
                {"natural_key": f"{kalash.natural_key}:टीका:san"}
            )
            bh_task = mongo[GATHA_TEEKA_BHAAVARTH_HINDI].find(
                {"gatha_teeka_natural_key": kalash.natural_key}
            ).to_list(None)
            sf_task = mongo[GATHA_TEEKA_BHAAVARTH_SHORTFONT].find(
                {"gatha_natural_key": kalash.natural_key}
            ).to_list(None)
            # Secondary-kalash pages (e.g. samaysaar 011.html — Jaysenacharya
            # standalone gathas) also carry their own अन्वयार्थ / शब्दार्थ
            # block; the NJ envelope emits a teeka_gatha_mapping doc keyed by
            # the kalash NK. Fetch it so the UI can render the शब्दार्थ section
            # in the संबंधित panel for secondary kalashes too.
            tgm_task = mongo[TEEKA_GATHA_MAPPING].find_one(
                {"gatha_natural_key": kalash.natural_key}
            )
            prakrit_doc, sanskrit_doc, bhaavarth_docs, sf_docs, tgm_doc = await asyncio.gather(
                pra_task, san_task, bh_task, sf_task, tgm_task
            )
            # Attach shortfont entries to each bhaavarth doc.
            bh_list = [_strip_id(d) for d in (bhaavarth_docs or [])]
            if sf_docs:
                sf_by_nk = {
                    d["bhaavarth_natural_key"]: d.get("entries", [])
                    for d in sf_docs
                    if d.get("bhaavarth_natural_key")
                }
                for bh in bh_list:
                    pub_nk = bh.get("publication_natural_key", "")
                    bh_nk = f"{pub_nk}:गाथा:टीका:भावार्थ:{kalash.kalash_number}" if pub_nk else ""
                    bh["shortfont_entries"] = sf_by_nk.get(bh_nk, [])
            secondary_word_meanings = None
            if tgm_doc:
                tagged = tgm_doc.get("tagged_terms") or []
                full_anv = tgm_doc.get("full_anyavaarth") or ""
                if tagged or full_anv:
                    secondary_word_meanings = {
                        "entries": tagged,
                        "full_anyavaarth": full_anv,
                    }
            return {
                "natural_key": kalash.natural_key,
                "kalash_number": kalash.kalash_number,
                "teeka_natural_key": teeka_nk,
                "is_secondary": True,
                "prakrit": _strip_id(prakrit_doc),
                "sanskrit": _strip_id(sanskrit_doc),
                "hindi": None,
                "bhaavarth": bh_list,
                "word_meanings": secondary_word_meanings,
            }
        san_task = mongo[KALASH_SANSKRIT].find_one({"natural_key": f"{kalash.natural_key}:san"})
        hin_task = mongo[KALASH_HINDI].find_one({"natural_key": f"{kalash.natural_key}:hi"})
        bh_task = mongo[KALASH_BHAAVARTH_HINDI].find(
            {"kalash_natural_key": kalash.natural_key}
        ).to_list(None)
        wm_task = mongo[KALASH_WORD_MEANINGS].find_one(
            {"natural_key": f"{kalash.natural_key}:word_meanings"}
        )
        sf_task = mongo[KALASH_BHAAVARTH_SHORTFONT].find_one(
            {"kalash_natural_key": kalash.natural_key}
        )
        sanskrit_doc, hindi_doc, bhaavarth_docs, wm_doc, sf_doc = await asyncio.gather(
            san_task, hin_task, bh_task, wm_task, sf_task
        )
        bh_list = [_strip_id(d) for d in (bhaavarth_docs or [])]
        if sf_doc:
            sf_entries = sf_doc.get("entries", [])
            for bh in bh_list:
                bh["shortfont_entries"] = sf_entries
        return {
            "natural_key": kalash.natural_key,
            "kalash_number": kalash.kalash_number,
            "teeka_natural_key": teeka_nk,
            "is_secondary": False,
            "prakrit": None,
            "sanskrit": _strip_id(sanskrit_doc),
            "hindi": _strip_id(hindi_doc),
            "bhaavarth": bh_list,
            "word_meanings": _strip_id(wm_doc),
        }

    return list(await asyncio.gather(*[_fetch_kalash_docs(k, tnk, trole) for k, tnk, trole in rows]))
