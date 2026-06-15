import os
import sys

import pytest
from sqlalchemy import select

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)

from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.enums import AuthorKind, IngestionSource
from jain_kb_common.db.postgres.keywords import Keyword
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.upserts import (
    upsert_author,
    upsert_keyword,
    upsert_shastra,
)

_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))
skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="DATABASE_URL not set")


@skip_no_db
async def test_initial_insert_stamps_source(async_session):
    """Upserting a new row with source=jainkosh sets sources=['jainkosh']."""
    await upsert_keyword(
        async_session,
        natural_key="आत्मा-src1",
        display_text="आत्मा",
        source=IngestionSource.jainkosh,
    )
    await async_session.commit()

    row = await async_session.scalar(
        select(Keyword).where(Keyword.natural_key == "आत्मा-src1")
    )
    assert row is not None
    assert row.sources == ["jainkosh"]


@skip_no_db
async def test_same_source_upsert_is_idempotent(async_session):
    """Re-upserting with the same source keeps sources=['jainkosh'] without duplicates."""
    nk = "आत्मा-src2"
    for _ in range(2):
        await upsert_keyword(
            async_session,
            natural_key=nk,
            display_text="आत्मा",
            source=IngestionSource.jainkosh,
        )
        await async_session.commit()
        async_session.expire_all()

    row = await async_session.scalar(select(Keyword).where(Keyword.natural_key == nk))
    assert row is not None
    assert row.sources == ["jainkosh"]
    assert len(row.sources) == 1


@skip_no_db
async def test_different_source_upsert_unions(async_session):
    """Upserting a shastra with jainkosh then nj produces sources={jainkosh, nj}."""
    author_id = await upsert_author(
        async_session,
        natural_key="kundkund-src3",
        display_name=[{"lang": "hi", "text": "कुन्दकुन्द"}],
        kind=AuthorKind.acharya,
        source=IngestionSource.jainkosh,
    )
    nk = "samaysaar-src3"
    await upsert_shastra(
        async_session,
        natural_key=nk,
        title=[{"lang": "hi", "text": "समयसार"}],
        author_id=author_id,
        source=IngestionSource.jainkosh,
    )
    await async_session.commit()

    await upsert_shastra(
        async_session,
        natural_key=nk,
        title=[{"lang": "hi", "text": "समयसार"}],
        author_id=author_id,
        source=IngestionSource.nj,
    )
    await async_session.commit()
    async_session.expire_all()

    row = await async_session.scalar(select(Shastra).where(Shastra.natural_key == nk))
    assert row is not None
    assert set(row.sources) == {"jainkosh", "nj"}


@skip_no_db
async def test_source_none_leaves_sources_untouched(async_session):
    """Upserting with source=None does not modify the existing sources array."""
    nk = "आत्मा-src4"
    await upsert_keyword(
        async_session,
        natural_key=nk,
        display_text="आत्मा",
        source=IngestionSource.nj,
    )
    await async_session.commit()

    # Re-upsert without source (e.g. graph_sync re-sync)
    await upsert_keyword(
        async_session,
        natural_key=nk,
        display_text="आत्मा updated",
        source=None,
    )
    await async_session.commit()
    async_session.expire_all()

    row = await async_session.scalar(select(Keyword).where(Keyword.natural_key == nk))
    assert row is not None
    assert row.sources == ["nj"]
    assert row.display_text == "आत्मा updated"


@skip_no_db
async def test_multiple_upserts_do_not_accumulate_duplicates(async_session):
    """Three upserts with the same two sources produce exactly two distinct sources."""
    author_id = await upsert_author(
        async_session,
        natural_key="kundkund-src5",
        display_name=[{"lang": "hi", "text": "कुन्दकुन्द"}],
        kind=AuthorKind.acharya,
        source=IngestionSource.jainkosh,
    )
    nk = "pravachansaar-src5"
    for src in [IngestionSource.jainkosh, IngestionSource.nj, IngestionSource.jainkosh]:
        await upsert_shastra(
            async_session,
            natural_key=nk,
            title=[{"lang": "hi", "text": "प्रवचनसार"}],
            author_id=author_id,
            source=src,
        )
        await async_session.commit()
        async_session.expire_all()

    row = await async_session.scalar(select(Shastra).where(Shastra.natural_key == nk))
    assert row is not None
    assert set(row.sources) == {"jainkosh", "nj"}
    assert len(row.sources) == 2
