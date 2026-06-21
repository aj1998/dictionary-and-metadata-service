from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/keyword_resolve_batch"

_ATMA_NATURAL_KEY = "आत्मा"

_MONGO_DOC_MIXED = {
    "natural_key": _ATMA_NATURAL_KEY,
    "page_sections": [
        {
            "section_index": 0,
            "definitions": [
                {
                    "definition_index": 0,
                    "blocks": [
                        {
                            "kind": "hindi_text",
                            "text_devanagari": "यह आत्मा का हिंदी विवरण है।",
                            "hindi_translation": None,
                        },
                        {
                            "kind": "sanskrit_text",
                            "text_devanagari": "आत्मसंस्कृतम्।",
                            "hindi_translation": "आत्मा का संस्कृत अर्थ।",
                        },
                        {
                            "kind": "see_also",
                            "text_devanagari": "",
                            "target_keyword": "मोक्ष",
                        },
                    ],
                }
            ],
        }
    ],
}

_MONGO_DOC_LONG = {
    "natural_key": _ATMA_NATURAL_KEY,
    "page_sections": [
        {
            "section_index": 0,
            "definitions": [
                {
                    "definition_index": 0,
                    "blocks": [
                        {
                            "kind": "hindi_text",
                            "text_devanagari": "अ" * 2000,  # longer than BLOCK_TEXT_CAP
                        },
                    ],
                }
            ],
        }
    ],
}

_MONGO_DOC_MULTI_BLOCKS = {
    "natural_key": _ATMA_NATURAL_KEY,
    "page_sections": [
        {
            "section_index": 0,
            "definitions": [
                {
                    "definition_index": 0,
                    "blocks": [
                        {"kind": "hindi_text", "text_devanagari": "पहला हिंदी खंड।"},
                        {"kind": "hindi_text", "text_devanagari": "दूसरा हिंदी खंड।"},
                        {"kind": "hindi_text", "text_devanagari": "तीसरा हिंदी खंड।"},
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
@pytest.mark.parametrize("client_with_mongo", [[ _MONGO_DOC_MIXED]], indirect=True)
async def test_translations_included_see_also_excluded(client_with_mongo: AsyncClient) -> None:
    """Hindi prose + the Hindi meaning of sanskrit verse are included; the
    raw sanskrit and the see_also pointer are excluded."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, _ATMA_NATURAL_KEY)

    resp = await client_with_mongo.post(
        URL,
        json={"tokens": [_ATMA_NATURAL_KEY], "include_definitions": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    r = data["resolutions"][0]
    assert r["match_kind"] == "exact"
    assert r["definitions"] is not None
    assert len(r["definitions"]) == 2  # hindi_text + sanskrit translation; see_also dropped
    kinds_texts = {d["text_hi"] for d in r["definitions"]}
    assert "यह आत्मा का हिंदी विवरण है।" in kinds_texts
    assert "आत्मा का संस्कृत अर्थ।" in kinds_texts  # hindi_translation of the sanskrit block
    assert "आत्मसंस्कृतम्।" not in kinds_texts  # raw sanskrit not emitted


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [[_MONGO_DOC_LONG]], indirect=True)
async def test_block_text_truncated_to_1500(client_with_mongo: AsyncClient) -> None:
    """Block text is truncated to 1500 chars and suffixed with '…' (1501 total)."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, _ATMA_NATURAL_KEY)

    resp = await client_with_mongo.post(
        URL,
        json={"tokens": [_ATMA_NATURAL_KEY], "include_definitions": True},
    )
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["definitions"] is not None
    assert len(r["definitions"]) == 1
    text = r["definitions"][0]["text_hi"]
    assert text.endswith("…"), "truncated text must end with '…'"
    assert len(text) == 1501  # 1500 content chars + '…'


@pytest.mark.asyncio
@pytest.mark.parametrize("client_with_mongo", [[_MONGO_DOC_MULTI_BLOCKS]], indirect=True)
async def test_definitions_per_keyword_limits_blocks(client_with_mongo: AsyncClient) -> None:
    """definitions_per_keyword=1 returns only 1 block."""
    factory = client_with_mongo.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, _ATMA_NATURAL_KEY)

    resp = await client_with_mongo.post(
        URL,
        json={
            "tokens": [_ATMA_NATURAL_KEY],
            "include_definitions": True,
            "definitions_per_keyword": 1,
        },
    )
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["definitions"] is not None
    assert len(r["definitions"]) == 1
    assert r["definitions"][0]["text_hi"] == "पहला हिंदी खंड।"


@pytest.mark.asyncio
async def test_include_definitions_false_returns_none(client: AsyncClient) -> None:
    """include_definitions=False means definitions field is None."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_keyword(factory, _ATMA_NATURAL_KEY)

    resp = await client.post(
        URL,
        json={"tokens": [_ATMA_NATURAL_KEY], "include_definitions": False},
    )
    assert resp.status_code == 200
    r = resp.json()["resolutions"][0]
    assert r["definitions"] is None
