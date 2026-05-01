import os
import sys
import uuid

import pytest
from sqlalchemy import select, func

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "packages", "jain_kb_common"),
)

from jain_kb_common.db.postgres.authors import Author
from jain_kb_common.db.postgres.books import Book
from jain_kb_common.db.postgres.enums import AuthorKind, IngestionSource
from jain_kb_common.db.postgres.gathas import Gatha
from jain_kb_common.db.postgres.keywords import Keyword
from jain_kb_common.db.postgres.pravachans import Pravachan
from jain_kb_common.db.postgres.shastras import Shastra
from jain_kb_common.db.postgres.teekas import Teeka
from jain_kb_common.db.postgres.topics import Topic
from jain_kb_common.db.postgres.upserts import (
    upsert_author,
    upsert_book,
    upsert_gatha,
    upsert_keyword,
    upsert_pravachan,
    upsert_shastra,
    upsert_teeka,
    upsert_topic,
)

_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))
skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="DATABASE_URL not set")


@skip_no_db
async def test_upsert_author_idempotent(async_session):
    nk = "test-author-1"
    id1 = await upsert_author(
        async_session,
        natural_key=nk,
        display_name=[{"lang": "en", "text": "Original"}],
        kind=AuthorKind.acharya,
    )
    id2 = await upsert_author(
        async_session,
        natural_key=nk,
        display_name=[{"lang": "en", "text": "Updated"}],
        kind=AuthorKind.scholar,
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Author.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Author).where(Author.natural_key == nk))
    assert row is not None
    assert row.display_name == [{"lang": "en", "text": "Updated"}]
    assert row.kind == AuthorKind.scholar


@skip_no_db
async def test_upsert_keyword_idempotent(async_session):
    nk = "आत्मा"
    id1 = await upsert_keyword(
        async_session,
        natural_key=nk,
        display_text="आत्मा",
        source_url="https://jainkosh.org/wiki/आत्मा",
        definition_doc_ids=["doc1"],
    )
    id2 = await upsert_keyword(
        async_session,
        natural_key=nk,
        display_text="आत्मा",
        source_url="https://jainkosh.org/wiki/आत्मा",
        definition_doc_ids=["doc1", "doc2"],
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Keyword.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Keyword).where(Keyword.natural_key == nk))
    assert row is not None
    assert row.definition_doc_ids == ["doc1", "doc2"]


@skip_no_db
async def test_upsert_shastra_idempotent(async_session):
    author_id = await upsert_author(
        async_session,
        natural_key="kundkund",
        display_name=[{"lang": "hi", "text": "कुन्दकुन्द"}],
        kind=AuthorKind.acharya,
    )
    nk = "pravachansaar"
    id1 = await upsert_shastra(
        async_session,
        natural_key=nk,
        title=[{"lang": "hi", "text": "प्रवचनसार"}],
        author_id=author_id,
        source_url="https://example.com/v1",
    )
    id2 = await upsert_shastra(
        async_session,
        natural_key=nk,
        title=[{"lang": "hi", "text": "प्रवचनसार"}, {"lang": "en", "text": "Pravachansaar"}],
        author_id=author_id,
        source_url="https://example.com/v2",
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Shastra.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Shastra).where(Shastra.natural_key == nk))
    assert row is not None
    assert row.source_url == "https://example.com/v2"


@skip_no_db
async def test_upsert_teeka_idempotent(async_session):
    author_id = await upsert_author(
        async_session,
        natural_key="amritchandra",
        display_name=[{"lang": "hi", "text": "अमृतचन्द्र"}],
        kind=AuthorKind.acharya,
    )
    shastra_id = await upsert_shastra(
        async_session,
        natural_key="pravachansaar-t",
        title=[{"lang": "hi", "text": "प्रवचनसार"}],
        author_id=author_id,
    )
    nk = "pravachansaar:amritchandra"
    id1 = await upsert_teeka(
        async_session,
        natural_key=nk,
        shastra_id=shastra_id,
        teekakar_id=author_id,
        public_url="https://example.com/v1",
    )
    id2 = await upsert_teeka(
        async_session,
        natural_key=nk,
        shastra_id=shastra_id,
        teekakar_id=author_id,
        public_url="https://example.com/v2",
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Teeka.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Teeka).where(Teeka.natural_key == nk))
    assert row is not None
    assert row.public_url == "https://example.com/v2"


@skip_no_db
async def test_upsert_book_idempotent(async_session):
    nk = "jain-dharma-book"
    id1 = await upsert_book(
        async_session,
        natural_key=nk,
        title=[{"lang": "en", "text": "Jain Dharma v1"}],
    )
    id2 = await upsert_book(
        async_session,
        natural_key=nk,
        title=[{"lang": "en", "text": "Jain Dharma v2"}],
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Book.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Book).where(Book.natural_key == nk))
    assert row is not None
    assert row.title == [{"lang": "en", "text": "Jain Dharma v2"}]


@skip_no_db
async def test_upsert_pravachan_idempotent(async_session):
    nk = "test-pravachan"
    id1 = await upsert_pravachan(
        async_session,
        natural_key=nk,
        title=[{"lang": "hi", "text": "प्रवचन v1"}],
    )
    id2 = await upsert_pravachan(
        async_session,
        natural_key=nk,
        title=[{"lang": "hi", "text": "प्रवचन v2"}],
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Pravachan.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Pravachan).where(Pravachan.natural_key == nk))
    assert row is not None
    assert row.title == [{"lang": "hi", "text": "प्रवचन v2"}]


@skip_no_db
async def test_upsert_topic_idempotent(async_session):
    nk = "jainkosh:आत्मा:बहिरात्मा"
    id1 = await upsert_topic(
        async_session,
        natural_key=nk,
        display_text=[{"lang": "hi", "text": "बहिरात्मा v1"}],
        source=IngestionSource.jainkosh,
    )
    id2 = await upsert_topic(
        async_session,
        natural_key=nk,
        display_text=[{"lang": "hi", "text": "बहिरात्मा v2"}],
        source=IngestionSource.jainkosh,
        extract_doc_ids=["mongo123"],
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Topic.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Topic).where(Topic.natural_key == nk))
    assert row is not None
    assert row.extract_doc_ids == ["mongo123"]


@skip_no_db
async def test_upsert_gatha_idempotent(async_session):
    author_id = await upsert_author(
        async_session,
        natural_key="kundkund-g",
        display_name=[{"lang": "hi", "text": "कुन्दकुन्द"}],
        kind=AuthorKind.acharya,
    )
    shastra_id = await upsert_shastra(
        async_session,
        natural_key="pravachansaar-g",
        title=[{"lang": "hi", "text": "प्रवचनसार"}],
        author_id=author_id,
    )
    nk = "pravachansaar:039"
    id1 = await upsert_gatha(
        async_session,
        natural_key=nk,
        shastra_id=shastra_id,
        gatha_number="039",
        prakrit_doc_id="mongo-v1",
    )
    id2 = await upsert_gatha(
        async_session,
        natural_key=nk,
        shastra_id=shastra_id,
        gatha_number="039",
        prakrit_doc_id="mongo-v2",
        keyword_ids=["kw-uuid-1"],
    )
    await async_session.commit()

    count = await async_session.scalar(
        select(func.count()).where(Gatha.natural_key == nk)
    )
    assert count == 1
    assert id1 == id2

    row = await async_session.scalar(select(Gatha).where(Gatha.natural_key == nk))
    assert row is not None
    assert row.prakrit_doc_id == "mongo-v2"
    assert row.keyword_ids == ["kw-uuid-1"]
