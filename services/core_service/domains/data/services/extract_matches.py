from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import EXTRACT_MATCHES
from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.postgres.kalashas import Kalash

# Kalash extract-match target collections that originate from a Kalash node and
# therefore need their owning-gatha natural_key resolved at read-time (the
# matcher worker leaves `target.gatha_natural_key` null for these because the
# Neo4j Kalash stub doesn't carry that property — the Kalash→Gatha edge lives
# only in Postgres).
_KALASH_COLLECTIONS = {
    "kalash_sanskrit",
    "kalash_hindi",
    "kalash_bhaavarth_hindi",
}


async def get_by_natural_key(
    mongo: AsyncIOMotorDatabase,
    natural_key: str,
    session: AsyncSession | None = None,
) -> dict | None:
    doc = await mongo[EXTRACT_MATCHES].find_one({"natural_key": natural_key})
    if doc is None:
        return None
    doc.pop("_id", None)
    target = doc.get("target") or {}
    if (
        session is not None
        and target.get("collection") in _KALASH_COLLECTIONS
        and not target.get("gatha_natural_key")
    ):
        target_nk = target.get("natural_key") or ""
        # target.natural_key formats:
        #   kalash_sanskrit / kalash_hindi  → "{shastra}:{teeka}:कलश:{n}:{san|hi}"
        #   kalash_bhaavarth_hindi          → "{publication}:कलश:भावार्थ:{n}"
        # Strip the language / bhaavarth suffix to recover the Kalash natural_key
        # used in Postgres ("{shastra}:{teeka}:कलश:{n}").
        kalash_nk: str | None = None
        parts = target_nk.split(":")
        if "कलश" in parts:
            kidx = parts.index("कलश")
            if (
                target.get("collection") == "kalash_bhaavarth_hindi"
                and kidx + 2 < len(parts)
                and parts[kidx + 1] == "भावार्थ"
            ):
                # Publication-rooted bhaavarth key; we can't reconstruct the
                # canonical Kalash nk without the shastra/teeka prefix.
                kalash_nk = None
            else:
                kalash_nk = ":".join(parts[: kidx + 2])
        if kalash_nk:
            row = await session.execute(
                select(Gatha.natural_key)
                .join(Kalash, Kalash.gatha_id == Gatha.id)
                .where(Kalash.natural_key == kalash_nk)
            )
            gatha_nk = row.scalar_one_or_none()
            if gatha_nk:
                target["gatha_natural_key"] = gatha_nk
                doc["target"] = target
    return doc
