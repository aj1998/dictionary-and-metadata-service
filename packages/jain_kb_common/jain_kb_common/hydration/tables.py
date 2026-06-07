"""Hydration helpers for Table entities.

Fetches PG index row + Mongo full document and merges them into typed models.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import TABLES
from jain_kb_common.db.mongo.schemas import LangText
from jain_kb_common.db.postgres.tables import Table

logger = logging.getLogger(__name__)


class TableSummary(BaseModel):
    natural_key: str
    seq: int
    caption: list[LangText]


class TableResponse(BaseModel):
    natural_key: str
    pg_id: str
    source: str
    parent_natural_key: str
    parent_kind: str
    seq: int
    caption: list[LangText]
    source_url: str | None
    raw_html: str
    cells: list[list[str]]
    # 3-D list: rows × cols × resolved reference dicts per cell.
    cell_refs: list[list[list[dict]]] = []
    header_rows: int
    plaintext: str | None
    mentioned_keyword_natural_keys: list[str]
    mentioned_topic_natural_keys: list[str]


async def hydrate_tables_for_parent(
    pg: AsyncSession,
    mongo: object,
    *,
    parent_natural_key: str,
) -> list[TableSummary]:
    """Return ordered TableSummary list for a parent entity."""
    result = await pg.execute(
        select(Table)
        .where(Table.parent_natural_key == parent_natural_key)
        .order_by(Table.seq)
    )
    rows = list(result.scalars())
    summaries: list[TableSummary] = []
    for row in rows:
        caption = _parse_caption(row.caption)
        summaries.append(TableSummary(
            natural_key=row.natural_key,
            seq=row.seq,
            caption=caption,
        ))
    logger.debug(
        "hydrate_tables_for_parent parent=%s → %d tables",
        parent_natural_key, len(summaries),
    )
    return summaries


async def hydrate_table_full(
    pg: AsyncSession,
    mongo: object,
    *,
    natural_key: str,
) -> TableResponse | None:
    """Return a full TableResponse merging PG row + Mongo doc, or None if not found."""
    result = await pg.execute(
        select(Table).where(Table.natural_key == natural_key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    mongo_doc = await _fetch_mongo_doc(mongo, natural_key)

    if mongo_doc is None:
        logger.warning(
            "hydrate_table_full: Mongo doc missing for natural_key=%s; returning empty cells",
            natural_key,
        )

    return TableResponse(
        natural_key=row.natural_key,
        pg_id=str(row.id),
        source=row.source.value if hasattr(row.source, "value") else str(row.source),
        parent_natural_key=row.parent_natural_key,
        parent_kind=row.parent_kind,
        seq=row.seq,
        caption=_parse_caption(row.caption),
        source_url=row.source_url,
        raw_html=mongo_doc.get("raw_html", "") if mongo_doc else "",
        cells=mongo_doc.get("cells", []) if mongo_doc else [],
        cell_refs=mongo_doc.get("cell_refs", []) if mongo_doc else [],
        header_rows=mongo_doc.get("header_rows", 0) if mongo_doc else 0,
        plaintext=mongo_doc.get("plaintext") if mongo_doc else None,
        mentioned_keyword_natural_keys=(
            mongo_doc.get("mentioned_keyword_natural_keys", []) if mongo_doc else []
        ),
        mentioned_topic_natural_keys=(
            mongo_doc.get("mentioned_topic_natural_keys", []) if mongo_doc else []
        ),
    )


async def _fetch_mongo_doc(mongo: object, natural_key: str) -> dict | None:
    try:
        doc = await mongo[TABLES].find_one({"natural_key": natural_key})  # type: ignore[index]
        if doc:
            doc.pop("_id", None)
        return doc
    except Exception as exc:
        logger.error("hydrate_table_full: Mongo fetch failed for %s: %s", natural_key, exc)
        return None


def _parse_caption(raw: list | None) -> list[LangText]:
    if not raw:
        return []
    out: list[LangText] = []
    for item in raw:
        try:
            out.append(LangText(**item) if isinstance(item, dict) else item)
        except Exception:
            pass
    return out
