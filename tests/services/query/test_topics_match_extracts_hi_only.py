from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/topics_match"

_TOPIC_NK = "द्रव्य/स्वतंत्रता/लक्षण"

_MONGO_DOCS = [
    {
        "natural_key": _TOPIC_NK,
        "blocks": [
            {
                "kind": "hindi_text",
                "text_devanagari": "द्रव्य का स्वतंत्र लक्षण यह है।",
                "references": [],
            },
            {
                "kind": "sanskrit_text",
                "text_devanagari": "द्रव्यं स्वतन्त्रम्।",
                "references": [],
            },
            {
                "kind": "hindi_gatha",
                "text_devanagari": "जो है सो है।",
                "references": [],
            },
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
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS], indirect=True)
async def test_only_hindi_blocks_in_extracts(client_with_mongo: AsyncClient) -> None:
    """Non-Hindi blocks (sanskrit_text) must not appear in extracts_hi."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _TOPIC_NK)

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "include_extracts": True,
        "include_references": False,
    })
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    match = next((m for m in matches if m["topic_natural_key"] == _TOPIC_NK), None)
    assert match is not None, f"Expected {_TOPIC_NK} in matches"
    extracts = match["extracts_hi"]
    assert extracts is not None
    # Only hindi_text and hindi_gatha should appear
    texts = [e["text_hi"] for e in extracts]
    assert any("द्रव्य का स्वतंत्र" in t for t in texts), "Expected hindi_text block"
    assert any("जो है सो है" in t for t in texts), "Expected hindi_gatha block"
    # Sanskrit block must not appear
    assert not any("द्रव्यं स्वतन्त्रम्" in t for t in texts), "Sanskrit block leaked"


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS], indirect=True)
async def test_include_extracts_false_returns_null(client_with_mongo: AsyncClient) -> None:
    """When include_extracts=False, extracts_hi should be null."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _TOPIC_NK)

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    match = next((m for m in matches if m["topic_natural_key"] == _TOPIC_NK), None)
    if match:
        assert match["extracts_hi"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS], indirect=True)
async def test_extract_count_counts_all_blocks(client_with_mongo: AsyncClient) -> None:
    """extract_count reflects the total block count (all kinds, not just Hindi),
    matching the data-service topics listing, even when include_extracts=False."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _TOPIC_NK)

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    match = next((m for m in resp.json()["matches"] if m["topic_natural_key"] == _TOPIC_NK), None)
    assert match is not None
    # 3 blocks total in the fixture (2 Hindi + 1 Sanskrit).
    assert match["extract_count"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [[]], indirect=True)
async def test_no_extracts_when_topic_not_in_mongo(client_with_mongo: AsyncClient) -> None:
    """When topic has no Mongo doc, extracts_hi should be empty list."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _TOPIC_NK)

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "include_extracts": True,
        "include_references": False,
    })
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    match = next((m for m in matches if m["topic_natural_key"] == _TOPIC_NK), None)
    if match:
        assert match["extracts_hi"] == []
