from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/topics_match"

_TOPIC_NK = "द्रव्य/स्वतंत्रता/लक्षण"
# Real jainkosh topic anchors are numbered section-paths (e.g. #3.1), read
# verbatim from the topic_extracts doc — the API never reconstructs them.
_TOPIC_SOURCE_URL = "https://www.jainkosh.org/wiki/द्रव्य#3.1"

_MONGO_DOCS_WITH_URL = [
    {
        "natural_key": _TOPIC_NK,
        "source_url": _TOPIC_SOURCE_URL,
        "blocks": [
            {"kind": "hindi_text", "text_devanagari": "द्रव्य का स्वतंत्र लक्षण यह है।", "references": []},
        ],
    }
]

_MONGO_DOCS_NO_URL = [
    {
        "natural_key": _TOPIC_NK,
        "blocks": [
            {"kind": "hindi_text", "text_devanagari": "द्रव्य का स्वतंत्र लक्षण यह है।", "references": []},
        ],
    }
]


async def _insert_topic(factory, natural_key: str) -> None:
    tid = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO topics (id, natural_key, display_text, source, is_leaf, is_synthetic, extract_doc_ids) "
                "VALUES (:id, :nk, '[{\"lang\":\"hi\",\"script\":\"devanagari\",\"text\":\"लक्षण\"}]'::jsonb, "
                "'jainkosh'::ingestion_source, true, false, '[]'::jsonb)"
            ),
            {"id": tid, "nk": natural_key},
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS_WITH_URL], indirect=True)
async def test_topic_source_url_returned(client_with_mongo: AsyncClient) -> None:
    """A matched topic exposes the source_url from its topic_extracts doc."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _TOPIC_NK)

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "content_only": False,
        "include_extracts": True,
        "include_references": False,
    })
    assert resp.status_code == 200
    match = next((m for m in resp.json()["matches"] if m["topic_natural_key"] == _TOPIC_NK), None)
    assert match is not None
    assert match["source_url"] == _TOPIC_SOURCE_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS_WITH_URL], indirect=True)
async def test_topic_source_url_returned_without_extracts(client_with_mongo: AsyncClient) -> None:
    """source_url is populated even when extracts are not requested."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _TOPIC_NK)

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    match = next((m for m in resp.json()["matches"] if m["topic_natural_key"] == _TOPIC_NK), None)
    assert match is not None
    assert match["source_url"] == _TOPIC_SOURCE_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS_NO_URL], indirect=True)
async def test_topic_source_url_null_when_absent(client_with_mongo: AsyncClient) -> None:
    """When the topic doc has no source_url, the field is null."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _TOPIC_NK)

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "content_only": False,
        "include_extracts": True,
        "include_references": False,
    })
    assert resp.status_code == 200
    match = next((m for m in resp.json()["matches"] if m["topic_natural_key"] == _TOPIC_NK), None)
    assert match is not None
    assert match["source_url"] is None
