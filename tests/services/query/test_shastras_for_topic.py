from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/shastras_for_topic"

_SHASTRAS_ROWS = [
    {
        "shastra_nk": "samaysaar",
        "name_hi": "समयसार",
        "total_mentions": 5,
        "gathas": [
            {"number": 6, "page_number": 42},
            {"number": 49, "page_number": 110},
            {"number": 72, "page_number": None},
        ],
    },
    {
        "shastra_nk": "pravachansaar",
        "name_hi": "प्रवचनसार",
        "total_mentions": 2,
        "gathas": [
            {"number": 10, "page_number": 15},
        ],
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], _SHASTRAS_ROWS)],
    indirect=True,
)
async def test_shastras_for_topic_basic(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """Basic: returns shastras sorted by total_mentions DESC, correct shape."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "topic_natural_key": "द्रव्य/स्वतंत्रता",
        "include_gathas": True,
        "limit_shastras": 10,
        "limit_gathas_per_shastra": 10,
    })
    assert resp.status_code == 200
    data = resp.json()

    assert data["topic_natural_key"] == "द्रव्य/स्वतंत्रता"
    assert "shastras" in data
    assert "tool_trace_id" in data

    shastras = data["shastras"]
    assert len(shastras) == 2
    assert shastras[0]["shastra_natural_key"] == "samaysaar"
    assert shastras[0]["total_mentions"] == 5
    assert shastras[0]["name_hi"] == "समयसार"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], _SHASTRAS_ROWS)],
    indirect=True,
)
async def test_shastras_for_topic_gathas_capped(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """limit_gathas_per_shastra caps the gatha list per shastra."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "topic_natural_key": "द्रव्य/स्वतंत्रता",
        "include_gathas": True,
        "limit_shastras": 10,
        "limit_gathas_per_shastra": 2,
    })
    assert resp.status_code == 200
    shastras = resp.json()["shastras"]
    # samaysaar mock has 3 gathas; cap is 2
    samaysaar = next(s for s in shastras if s["shastra_natural_key"] == "samaysaar")
    assert len(samaysaar["gathas"]) <= 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], _SHASTRAS_ROWS)],
    indirect=True,
)
async def test_shastras_for_topic_include_gathas_false(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """include_gathas=false → gathas list is empty."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "topic_natural_key": "द्रव्य/स्वतंत्रता",
        "include_gathas": False,
    })
    assert resp.status_code == 200
    for s in resp.json()["shastras"]:
        assert s["gathas"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], _SHASTRAS_ROWS)],
    indirect=True,
)
async def test_shastras_for_topic_gatha_fields(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """Each gatha entry has 'number' and 'page_number' (nullable)."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "topic_natural_key": "द्रव्य/स्वतंत्रता",
        "include_gathas": True,
        "limit_gathas_per_shastra": 10,
    })
    assert resp.status_code == 200
    samaysaar = next(
        s for s in resp.json()["shastras"] if s["shastra_natural_key"] == "samaysaar"
    )
    g0 = samaysaar["gathas"][0]
    assert "number" in g0
    assert "page_number" in g0
    assert g0["number"] == 6
    assert g0["page_number"] == 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], [])],
    indirect=True,
)
async def test_shastras_for_topic_missing_input(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """No topic_natural_key and no keywords → 422."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "include_gathas": True,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_with_neo4j_subworkflow",
    [([], _SHASTRAS_ROWS)],
    indirect=True,
)
async def test_shastras_for_topic_via_keywords(
    client_with_neo4j_subworkflow: AsyncClient,
) -> None:
    """keywords input: resolves via topics_match (Postgres), then queries Neo4j.
    Since topics table is empty, no hit → empty shastras list returned."""
    resp = await client_with_neo4j_subworkflow.post(URL, json={
        "keywords": ["स्वतंत्रता"],
        "include_gathas": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    # No topics in Postgres → resolved to empty, shastras should be []
    assert data["topic_natural_key"] == ""
    assert data["shastras"] == []
