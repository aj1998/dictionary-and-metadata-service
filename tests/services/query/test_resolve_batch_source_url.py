from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/keyword_resolve_batch"

_ATMA_NATURAL_KEY = "आत्मा"
_ATMA_SOURCE_URL = "https://www.jainkosh.org/wiki/आत्मा"

_MONGO_DOC_WITH_URL = {
    "natural_key": _ATMA_NATURAL_KEY,
    "source_url": _ATMA_SOURCE_URL,
    "page_sections": [
        {
            "section_index": 0,
            "definitions": [
                {
                    "definition_index": 0,
                    "blocks": [
                        {"kind": "hindi_text", "text_devanagari": "यह आत्मा का हिंदी विवरण है।"},
                    ],
                }
            ],
        }
    ],
}

_MONGO_DOC_NO_URL = {
    "natural_key": _ATMA_NATURAL_KEY,
    "page_sections": [
        {
            "section_index": 0,
            "definitions": [
                {
                    "definition_index": 0,
                    "blocks": [
                        {"kind": "hindi_text", "text_devanagari": "यह आत्मा का हिंदी विवरण है।"},
                    ],
                }
            ],
        }
    ],
}


async def _insert_keyword(factory, natural_key: str) -> str:
    kid = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, sources, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, ARRAY[]::text[], '[]'::jsonb)"
            ),
            {"id": kid, "nk": natural_key, "dt": natural_key},
        )
        await session.commit()
    return kid


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [[_MONGO_DOC_WITH_URL]], indirect=True)
async def test_source_url_returned_with_definitions(client_with_mongo: AsyncClient) -> None:
    """A matched keyword exposes the source_url from its keyword_definitions doc."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, _ATMA_NATURAL_KEY)

    resp = await client_with_mongo.post(
        URL, json={"tokens": [_ATMA_NATURAL_KEY], "include_definitions": True}
    )
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["match_kind"] == "exact"
    assert r["source_url"] == _ATMA_SOURCE_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [[_MONGO_DOC_WITH_URL]], indirect=True)
async def test_source_url_returned_without_definitions(client_with_mongo: AsyncClient) -> None:
    """source_url is populated for a matched keyword even when definitions are not requested."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, _ATMA_NATURAL_KEY)

    resp = await client_with_mongo.post(
        URL, json={"tokens": [_ATMA_NATURAL_KEY], "include_definitions": False}
    )
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["definitions"] is None
    assert r["source_url"] == _ATMA_SOURCE_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [[_MONGO_DOC_NO_URL]], indirect=True)
async def test_source_url_null_when_absent(client_with_mongo: AsyncClient) -> None:
    """When the keyword doc has no source_url, the field is null (not an error)."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, _ATMA_NATURAL_KEY)

    resp = await client_with_mongo.post(
        URL, json={"tokens": [_ATMA_NATURAL_KEY], "include_definitions": True}
    )
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["source_url"] is None


@pytest.mark.asyncio
async def test_source_url_null_for_unmatched_token(client: AsyncClient) -> None:
    """An unmatched (none) token carries no source_url."""
    resp = await client.post(
        URL, json={"tokens": ["कोईअज्ञातशब्द"], "include_definitions": True}
    )
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["match_kind"] == "none"
    assert r["source_url"] is None
