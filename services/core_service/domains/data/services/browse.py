from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.postgres.kalashas import Kalash
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.teekas import Teeka


async def list_shastras(session: AsyncSession) -> list[dict]:
    rows = await session.execute(select(Shastra).order_by(Shastra.natural_key))
    shastras = list(rows.scalars())
    result = []
    for s in shastras:
        author = await session.get(Author, s.author_id) if s.author_id else None
        total_gathas = await session.scalar(
            text("SELECT COUNT(*) FROM gathas WHERE shastra_id = :sid").bindparams(sid=s.id)
        ) or 0
        total_teekas = await session.scalar(
            text("SELECT COUNT(*) FROM teekas WHERE shastra_id = :sid").bindparams(sid=s.id)
        ) or 0
        result.append({
            "shastra": s,
            "author": author,
            "total_gathas": int(total_gathas),
            "total_teekas": int(total_teekas),
        })
    return result


async def get_shastra_index(session: AsyncSession, natural_key: str) -> dict | None:
    row = await session.execute(select(Shastra).where(Shastra.natural_key == natural_key))
    shastra = row.scalar_one_or_none()
    if shastra is None:
        return None

    gatha_rows = await session.execute(
        select(Gatha)
        .where(Gatha.shastra_id == shastra.id)
        .order_by(Gatha.natural_key)
    )
    gathas = list(gatha_rows.scalars())

    adhikaar_map: dict[str, list[dict]] = {}
    no_adhikaar_key = "__none__"
    for g in gathas:
        key = str(g.adhikaar) if g.adhikaar else no_adhikaar_key
        adhikaar_map.setdefault(key, []).append({
            "adhikaar_obj": g.adhikaar,
            "natural_key": g.natural_key,
            "gatha_number": g.gatha_number,
            "heading": g.heading,
        })

    adhikaars = []
    for key, items in adhikaar_map.items():
        adhikaars.append({
            "adhikaar": items[0]["adhikaar_obj"],
            "gathas": [
                {
                    "natural_key": i["natural_key"],
                    "gatha_number": i["gatha_number"],
                    "heading": i["heading"],
                }
                for i in items
            ],
        })

    return {"shastra": shastra, "adhikaars": adhikaars}


async def get_teeka_index(session: AsyncSession, natural_key: str) -> dict | None:
    row = await session.execute(select(Teeka).where(Teeka.natural_key == natural_key))
    teeka = row.scalar_one_or_none()
    if teeka is None:
        return None

    shastra = await session.get(Shastra, teeka.shastra_id)
    teekakar = await session.get(Author, teeka.teekakar_id) if teeka.teekakar_id else None

    gatha_rows = await session.execute(
        select(Gatha)
        .where(Gatha.shastra_id == teeka.shastra_id)
        .order_by(Gatha.natural_key)
    )
    gathas = list(gatha_rows.scalars())

    kalash_rows = await session.execute(
        select(Kalash)
        .where(Kalash.teeka_id == teeka.id)
        .order_by(Kalash.natural_key)
    )
    kalashas = list(kalash_rows.scalars())

    kalash_by_prefix: dict[str, list[Kalash]] = {}
    for k in kalashas:
        # kalash natural key: <shastra>:<teekakar>:kalash:<num>
        # We attach kalashas after the gatha they logically follow
        # Simple approach: attach all kalashas after the last gatha they precede by number
        kalash_by_prefix.setdefault(k.natural_key, []).append(k)

    entries = []
    for g in gathas:
        entries.append({
            "kind": "gatha",
            "natural_key": g.natural_key,
            "gatha_number": g.gatha_number,
            "heading": g.heading,
        })

    for k in kalashas:
        entries.append({
            "kind": "kalash",
            "natural_key": k.natural_key,
            "kalash_number": k.kalash_number,
        })

    return {
        "teeka": teeka,
        "shastra": shastra,
        "teekakar": teekakar,
        "entries": entries,
    }
