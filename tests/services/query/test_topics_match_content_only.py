"""topics_match content_only filter (query_engine/08 Part A).

content_only (default true) drops matches whose displayable extract count is 0
(containers / index rows) before applying the limit, so callers never anchor on
an empty topic.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/topics_match"

_WITH_CONTENT = "द्रव्य/स्वतंत्रता/लक्षण"
_NO_CONTENT = "द्रव्य/स्वतंत्रता/भेद"

_MONGO_DOCS = [
    {
        "natural_key": _WITH_CONTENT,
        "blocks": [
            {"kind": "hindi_text", "text_devanagari": "द्रव्य का लक्षण।", "references": []},
        ],
    },
    # _NO_CONTENT: only a see_also pointer → 0 displayable blocks.
    {
        "natural_key": _NO_CONTENT,
        "blocks": [
            {"kind": "see_also", "text_devanagari": "", "target_keyword": "गुण", "references": []},
        ],
    },
]


async def _insert_topic(factory, natural_key: str, leaf_text: str) -> None:
    tid = str(uuid.uuid4())
    disp = '[{"lang":"hi","script":"devanagari","text":"%s"}]' % leaf_text
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO topics (id, natural_key, display_text, source, is_leaf, is_synthetic, extract_doc_ids) "
                f"VALUES (:id, :nk, '{disp}'::jsonb, 'jainkosh'::ingestion_source, true, false, '[]'::jsonb)"
            ),
            {"id": tid, "nk": natural_key},
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS], indirect=True)
async def test_content_only_default_drops_empty_topics(client_with_mongo: AsyncClient) -> None:
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _WITH_CONTENT, "लक्षण")
    await _insert_topic(factory, _NO_CONTENT, "भेद")

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    nks = [m["topic_natural_key"] for m in resp.json()["matches"]]
    assert _WITH_CONTENT in nks
    assert _NO_CONTENT not in nks


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [_MONGO_DOCS], indirect=True)
async def test_content_only_false_keeps_empty_topics(client_with_mongo: AsyncClient) -> None:
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_topic(factory, _WITH_CONTENT, "लक्षण")
    await _insert_topic(factory, _NO_CONTENT, "भेद")

    resp = await client_with_mongo.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    nks = [m["topic_natural_key"] for m in resp.json()["matches"]]
    assert _WITH_CONTENT in nks
    assert _NO_CONTENT in nks
