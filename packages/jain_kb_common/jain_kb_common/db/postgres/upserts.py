import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .authors import Author
from .books import Book
from .enums import AuthorKind, IngestionSource
from .gathas import Gatha
from .keywords import Keyword
from .pravachans import Pravachan
from .shastras import Shastra
from .teekas import Teeka
from .topics import Topic


async def upsert_author(
    session: AsyncSession,
    *,
    natural_key: str,
    display_name: Any,
    kind: AuthorKind,
    bio: Any = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Author)
        .values(
            natural_key=natural_key,
            display_name=display_name,
            kind=kind,
            bio=bio,
        )
        .on_conflict_do_update(
            index_elements=[Author.natural_key],
            set_={
                "display_name": display_name,
                "kind": kind,
                "bio": bio,
                "updated_at": func.now(),
            },
        )
        .returning(Author.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_shastra(
    session: AsyncSession,
    *,
    natural_key: str,
    title: Any,
    author_id: uuid.UUID,
    source_url: str | None = None,
    description: Any = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Shastra)
        .values(
            natural_key=natural_key,
            title=title,
            author_id=author_id,
            source_url=source_url,
            description=description,
        )
        .on_conflict_do_update(
            index_elements=[Shastra.natural_key],
            set_={
                "title": title,
                "author_id": author_id,
                "source_url": source_url,
                "description": description,
                "updated_at": func.now(),
            },
        )
        .returning(Shastra.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_teeka(
    session: AsyncSession,
    *,
    natural_key: str,
    shastra_id: uuid.UUID,
    teekakar_id: uuid.UUID | None = None,
    publisher: Any = None,
    translator: Any = None,
    editor: Any = None,
    cataloguesearch_shastra_id: str | None = None,
    public_url: str | None = None,
    publisher_url: str | None = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Teeka)
        .values(
            natural_key=natural_key,
            shastra_id=shastra_id,
            teekakar_id=teekakar_id,
            publisher=publisher,
            translator=translator,
            editor=editor,
            cataloguesearch_shastra_id=cataloguesearch_shastra_id,
            public_url=public_url,
            publisher_url=publisher_url,
        )
        .on_conflict_do_update(
            index_elements=[Teeka.natural_key],
            set_={
                "shastra_id": shastra_id,
                "teekakar_id": teekakar_id,
                "publisher": publisher,
                "translator": translator,
                "editor": editor,
                "cataloguesearch_shastra_id": cataloguesearch_shastra_id,
                "public_url": public_url,
                "publisher_url": publisher_url,
                "updated_at": func.now(),
            },
        )
        .returning(Teeka.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_book(
    session: AsyncSession,
    *,
    natural_key: str,
    title: Any,
    shastra_id: uuid.UUID | None = None,
    publisher: Any = None,
    translator: Any = None,
    editor: Any = None,
    public_url: str | None = None,
    publisher_url: str | None = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Book)
        .values(
            natural_key=natural_key,
            title=title,
            shastra_id=shastra_id,
            publisher=publisher,
            translator=translator,
            editor=editor,
            public_url=public_url,
            publisher_url=publisher_url,
        )
        .on_conflict_do_update(
            index_elements=[Book.natural_key],
            set_={
                "title": title,
                "shastra_id": shastra_id,
                "publisher": publisher,
                "translator": translator,
                "editor": editor,
                "public_url": public_url,
                "publisher_url": publisher_url,
                "updated_at": func.now(),
            },
        )
        .returning(Book.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_pravachan(
    session: AsyncSession,
    *,
    natural_key: str,
    title: Any,
    shastra_id: uuid.UUID | None = None,
    speaker_id: uuid.UUID | None = None,
    publisher: Any = None,
    translator: Any = None,
    editor: Any = None,
    public_url: str | None = None,
    publisher_url: str | None = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Pravachan)
        .values(
            natural_key=natural_key,
            title=title,
            shastra_id=shastra_id,
            speaker_id=speaker_id,
            publisher=publisher,
            translator=translator,
            editor=editor,
            public_url=public_url,
            publisher_url=publisher_url,
        )
        .on_conflict_do_update(
            index_elements=[Pravachan.natural_key],
            set_={
                "title": title,
                "shastra_id": shastra_id,
                "speaker_id": speaker_id,
                "publisher": publisher,
                "translator": translator,
                "editor": editor,
                "public_url": public_url,
                "publisher_url": publisher_url,
                "updated_at": func.now(),
            },
        )
        .returning(Pravachan.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_keyword(
    session: AsyncSession,
    *,
    natural_key: str,
    display_text: str,
    source_url: str | None = None,
    definition_doc_ids: list[str] | None = None,
    graph_node_id: str | None = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Keyword)
        .values(
            natural_key=natural_key,
            display_text=display_text,
            source_url=source_url,
            definition_doc_ids=definition_doc_ids or [],
            graph_node_id=graph_node_id,
        )
        .on_conflict_do_update(
            index_elements=[Keyword.natural_key],
            set_={
                "display_text": display_text,
                "source_url": source_url,
                "definition_doc_ids": definition_doc_ids or [],
                "graph_node_id": graph_node_id,
                "updated_at": func.now(),
            },
        )
        .returning(Keyword.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_topic(
    session: AsyncSession,
    *,
    natural_key: str,
    display_text: Any,
    source: IngestionSource,
    parent_keyword_id: uuid.UUID | None = None,
    extract_doc_ids: list[str] | None = None,
    graph_node_id: str | None = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Topic)
        .values(
            natural_key=natural_key,
            display_text=display_text,
            source=source,
            parent_keyword_id=parent_keyword_id,
            extract_doc_ids=extract_doc_ids or [],
            graph_node_id=graph_node_id,
        )
        .on_conflict_do_update(
            index_elements=[Topic.natural_key],
            set_={
                "display_text": display_text,
                "source": source,
                "parent_keyword_id": parent_keyword_id,
                "extract_doc_ids": extract_doc_ids or [],
                "graph_node_id": graph_node_id,
                "updated_at": func.now(),
            },
        )
        .returning(Topic.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_gatha(
    session: AsyncSession,
    *,
    natural_key: str,
    shastra_id: uuid.UUID,
    gatha_number: str,
    adhikaar: Any = None,
    heading: Any = None,
    prakrit_doc_id: str | None = None,
    sanskrit_doc_id: str | None = None,
    hindi_chhand_doc_ids: list[str] | None = None,
    prakrit_word_meanings_doc_id: str | None = None,
    sanskrit_word_meanings_doc_id: str | None = None,
    teeka_mapping_doc_ids: list[str] | None = None,
    keyword_ids: list[str] | None = None,
    topic_ids: list[str] | None = None,
) -> uuid.UUID:
    stmt = (
        pg_insert(Gatha)
        .values(
            natural_key=natural_key,
            shastra_id=shastra_id,
            gatha_number=gatha_number,
            adhikaar=adhikaar,
            heading=heading,
            prakrit_doc_id=prakrit_doc_id,
            sanskrit_doc_id=sanskrit_doc_id,
            hindi_chhand_doc_ids=hindi_chhand_doc_ids or [],
            prakrit_word_meanings_doc_id=prakrit_word_meanings_doc_id,
            sanskrit_word_meanings_doc_id=sanskrit_word_meanings_doc_id,
            teeka_mapping_doc_ids=teeka_mapping_doc_ids or [],
            keyword_ids=keyword_ids or [],
            topic_ids=topic_ids or [],
        )
        .on_conflict_do_update(
            index_elements=[Gatha.natural_key],
            set_={
                "shastra_id": shastra_id,
                "gatha_number": gatha_number,
                "adhikaar": adhikaar,
                "heading": heading,
                "prakrit_doc_id": prakrit_doc_id,
                "sanskrit_doc_id": sanskrit_doc_id,
                "hindi_chhand_doc_ids": hindi_chhand_doc_ids or [],
                "prakrit_word_meanings_doc_id": prakrit_word_meanings_doc_id,
                "sanskrit_word_meanings_doc_id": sanskrit_word_meanings_doc_id,
                "teeka_mapping_doc_ids": teeka_mapping_doc_ids or [],
                "keyword_ids": keyword_ids or [],
                "topic_ids": topic_ids or [],
                "updated_at": func.now(),
            },
        )
        .returning(Gatha.id)
    )
    res = await session.execute(stmt)
    return res.scalar_one()
