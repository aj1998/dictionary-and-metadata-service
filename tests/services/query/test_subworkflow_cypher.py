"""Regression tests for the subworkflow Cypher property names + param types.

These guard the live-data bugs where the per-gatha topics query matched a
non-existent `Gatha.number` property (actual: `gatha_number`, a string) and the
shastras_for_topic query referenced `g.number` / `s.name_hi` (actual:
`g.gatha_number` / `s.title_hi`). Mocked endpoint tests cannot catch these
because they stub the driver — so we assert the Cypher text and bound params
directly.
"""

from __future__ import annotations

import pytest

from services.query_service.pipeline import subworkflow as sw


class _SpyResult:
    async def data(self) -> list[dict]:
        return []


class _SpySession:
    def __init__(self, sink: dict) -> None:
        self._sink = sink

    async def run(self, cypher: str, **params: object) -> _SpyResult:
        self._sink["cypher"] = cypher
        self._sink["params"] = params
        return _SpyResult()

    async def __aenter__(self) -> "_SpySession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _SpyDriver:
    def __init__(self, sink: dict) -> None:
        self._sink = sink

    def session(self, database: str | None = None) -> _SpySession:
        return _SpySession(self._sink)


@pytest.mark.asyncio
async def test_topics_in_gatha_uses_gatha_number_string() -> None:
    sink: dict = {}
    await sw.fetch_topics_in_shastra(
        driver=_SpyDriver(sink),
        shastra_nk="नियमसार",
        gatha_number=15,
        limit=25,
        database="neo4j",
    )
    assert "gatha_number: $gatha_n" in sink["cypher"], "matches the real Gatha property"
    assert "{number: $gatha_n}" not in sink["cypher"], "must not use non-existent `number`"
    # Neo4j stores gatha_number as a string → integer must be coerced.
    assert sink["params"]["gatha_n"] == "15"
    assert isinstance(sink["params"]["gatha_n"], str)


@pytest.mark.asyncio
async def test_shastras_for_topic_uses_real_props() -> None:
    sink: dict = {}
    await sw.fetch_shastras_for_topic(
        driver=_SpyDriver(sink),
        topic_nk="रत्नत्रय का स्वरूप",
        limit_shastras=10,
        limit_gathas_per_shastra=10,
        database="neo4j",
    )
    cypher = sink["cypher"]
    assert "g.gatha_number" in cypher, "gatha number comes from g.gatha_number"
    assert "s.title_hi" in cypher, "shastra display name is s.title_hi"
    assert "g.number" not in cypher
    assert "s.name_hi" not in cypher
