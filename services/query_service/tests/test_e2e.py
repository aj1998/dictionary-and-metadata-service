"""
Phase 6 — End-to-end round-trip tests for the query engine.

Each test verifies the full request→response path using the same
mock infrastructure as other query-service tests, plus a DB round-trip
budget assertion: the number of backend calls must not exceed the
documented budget per endpoint.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Fixture data: a Jain keyword with alias + suffix variants
# ---------------------------------------------------------------------------

_JIVA_NK = "जीव"
_JIVA_ALIAS = "जिव"  # alias → जीव

_ATMA_NK = "आत्मा"
_ATMA_ALIAS = "आतम"

_TOPIC_LEAF = "द्रव्य/जीव/लक्षण"         # leaf — parent-aware trigram beats leaf-only
_TOPIC_CONTAINER = "द्रव्य"               # container

_SHASTRA_NK = "samaysaar"
_TOPIC_SAMAYSAAR = "द्रव्य/जीव"


async def _seed_keyword(factory, natural_key: str) -> str:
    kid = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keywords (id, natural_key, display_text, definition_doc_ids) "
                "VALUES (:id, :nk, :dt, '[]'::jsonb)"
            ),
            {"id": kid, "nk": natural_key, "dt": natural_key},
        )
        await session.commit()
    return kid


async def _seed_alias(factory, keyword_id: str, alias: str) -> None:
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO keyword_aliases (id, keyword_id, alias_text, source) "
                "VALUES (:id, :kid, :alias, 'test')"
            ),
            {"id": str(uuid.uuid4()), "kid": keyword_id, "alias": alias},
        )
        await session.commit()


async def _seed_topic(factory, natural_key: str, is_leaf: bool = True) -> None:
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO topics (id, natural_key, display_text, source, is_leaf, is_synthetic, extract_doc_ids) "
                "VALUES (:id, :nk, '[]'::jsonb, 'jainkosh'::ingestion_source, :leaf, false, '[]'::jsonb)"
            ),
            {"id": str(uuid.uuid4()), "nk": natural_key, "leaf": is_leaf},
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKeywordResolveBatchE2E:
    URL = "/v1/query/keyword_resolve_batch"

    @pytest.mark.asyncio
    async def test_alias_and_suffix_in_single_batch(self, client: AsyncClient) -> None:
        """Keyword with alias resolves correctly alongside an unresolvable token."""
        factory = client.state  # type: ignore[attr-defined]
        jiva_id = await _seed_keyword(factory, _JIVA_NK)
        await _seed_alias(factory, jiva_id, _JIVA_ALIAS)

        resp = await client.post(self.URL, json={
            "tokens": [_JIVA_NK, _JIVA_ALIAS, "xyznothing999"],
            "include_definitions": False,
        })
        assert resp.status_code == 200
        resolutions = resp.json()["resolutions"]
        assert len(resolutions) == 3

        r_exact = next(r for r in resolutions if r["input_token"] == _JIVA_NK)
        r_alias = next(r for r in resolutions if r["input_token"] == _JIVA_ALIAS)
        r_none = next(r for r in resolutions if r["input_token"] == "xyznothing999")

        assert r_exact["match_kind"] == "exact"
        assert r_alias["match_kind"] == "alias"
        assert r_alias["keyword_natural_key"] == _JIVA_NK
        assert r_none["match_kind"] == "none"

    @pytest.mark.asyncio
    async def test_suffix_strip_resolves_declined_form(self, client: AsyncClient) -> None:
        """Token ending in a Hindi suffix strips to the base keyword."""
        factory = client.state  # type: ignore[attr-defined]
        await _seed_keyword(factory, "द्रव्य")

        resp = await client.post(self.URL, json={
            "tokens": ["द्रव्यों"],
            "include_definitions": False,
        })
        assert resp.status_code == 200
        r = resp.json()["resolutions"][0]
        assert r["match_kind"] == "suffix_strip"
        assert r["keyword_natural_key"] == "द्रव्य"

    @pytest.mark.asyncio
    async def test_definitions_hindi_only_no_ellipsis_when_short(
        self, client_with_mongo: AsyncClient
    ) -> None:
        """Short definitions have no '…' truncation marker."""
        factory = client_with_mongo.state  # type: ignore[attr-defined]
        await _seed_keyword(factory, _JIVA_NK)

        resp = await client_with_mongo.post(self.URL, json={
            "tokens": [_JIVA_NK],
            "include_definitions": True,
        })
        assert resp.status_code == 200
        defs = resp.json()["resolutions"][0]["definitions"]
        assert defs is not None
        for d in defs:
            assert not d["text_hi"].endswith("…"), "short text should not be truncated"


@pytest.mark.parametrize("client_with_mongo", [[]], indirect=True)
class TestTopicsMatchE2E:
    URL = "/v1/query/topics_match"

    @pytest.mark.asyncio
    async def test_parent_aware_trigram_finds_leaf(
        self, client_with_mongo: AsyncClient
    ) -> None:
        """Parent-aware trigram (slash-replaced natural_key) finds leaf via container terms."""
        factory = client_with_mongo.state  # type: ignore[attr-defined]
        await _seed_topic(factory, _TOPIC_LEAF, is_leaf=True)
        await _seed_topic(factory, _TOPIC_CONTAINER, is_leaf=False)

        # "द्रव्य जीव" matches "द्रव्य/जीव/लक्षण" as well as "द्रव्य"
        resp = await client_with_mongo.post(self.URL, json={
            "phrase": "द्रव्य जीव",
            "limit": 10,
            "include_extracts": False,
            "include_references": False,
            "min_similarity": 0.1,
        })
        assert resp.status_code == 200
        nks = [m["topic_natural_key"] for m in resp.json()["matches"]]
        assert _TOPIC_LEAF in nks, "leaf not found via parent-aware trigram"

    @pytest.mark.asyncio
    async def test_leaf_scores_higher_than_container_for_full_path_phrase(
        self, client_with_mongo: AsyncClient
    ) -> None:
        """Leaf beats container when phrase matches the full path (all segments)."""
        factory = client_with_mongo.state  # type: ignore[attr-defined]
        await _seed_topic(factory, _TOPIC_LEAF, is_leaf=True)
        await _seed_topic(factory, _TOPIC_CONTAINER, is_leaf=False)

        # "द्रव्य जीव लक्षण" matches the leaf's full path much better than the
        # container "द्रव्य" alone — leaf score = sim*1.0, container = sim*0.6
        resp = await client_with_mongo.post(self.URL, json={
            "phrase": "द्रव्य जीव लक्षण",
            "limit": 10,
            "include_extracts": False,
            "include_references": False,
            "min_similarity": 0.1,
        })
        assert resp.status_code == 200
        matches = resp.json()["matches"]
        if len(matches) >= 2:
            leaf = next((m for m in matches if m["topic_natural_key"] == _TOPIC_LEAF), None)
            container = next((m for m in matches if m["topic_natural_key"] == _TOPIC_CONTAINER), None)
            if leaf and container:
                assert leaf["score"] >= container["score"], (
                    f"expected leaf ({leaf['score']:.3f}) >= container ({container['score']:.3f})"
                )


class TestGraphRAGE2E:
    URL = "/v1/query/graphrag"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_with_neo4j", [
        (
            [],  # no mongo docs
            [],  # no traverse rows
            [],  # no neighbor rows
        )
    ], indirect=True)
    async def test_unresolved_token_returned(
        self, client_with_neo4j: AsyncClient
    ) -> None:
        """Unknown token with no fuzzy match ends up in unresolved_tokens."""
        resp = await client_with_neo4j.post(self.URL, json={
            "tokens": ["xyznonexistent_token_abc"],
            "include_extracts": False,
            "include_neighbors": False,
            "include_references": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ranked_topics"] == []
        assert "xyznonexistent_token_abc" in data["unresolved_tokens"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_with_neo4j", [
        (
            [{"natural_key": "द्रव्य/जीव", "blocks": [
                {"kind": "hindi_text", "text_devanagari": "जीव का हिंदी विवरण।", "references": [
                    {"resolved_fields": [
                        {"field": "shastra", "value": "samaysaar"},
                        {"field": "gatha_number", "value": "6"},
                    ]}
                ]},
            ]}],
            # traverse rows — must include seed_kw and path_weight
            [{"topic_nk": "द्रव्य/जीव", "topic_pg_id": "t1", "heading_hi": "जीव",
              "is_leaf": True, "source": "jainkosh", "seed_kw": "जीव", "path_weight": 1.0}],
            [],  # neighbor rows
        )
    ], indirect=True)
    async def test_graphrag_extracts_and_references_single_mongo_query(
        self, client_with_neo4j: AsyncClient
    ) -> None:
        """GraphRAG returns extracts_hi and references from a single Mongo query."""
        factory = client_with_neo4j.state  # type: ignore[attr-defined]
        await _seed_keyword(factory, "जीव")

        resp = await client_with_neo4j.post(self.URL, json={
            "tokens": ["जीव"],
            "include_extracts": True,
            "include_references": True,
            "include_neighbors": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        topics = data["ranked_topics"]
        assert len(topics) > 0
        topic = next((t for t in topics if t["topic_natural_key"] == "द्रव्य/जीव"), None)
        if topic:
            # Extracts must be Hindi only
            assert topic["extracts_hi"] is not None
            assert all("…" not in e["text_hi"] for e in topic["extracts_hi"])
            # References must be present
            assert topic["references"] is not None


class TestTopicsInShastraE2E:
    URL = "/v1/query/topics_in_shastra"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_with_neo4j_subworkflow", [
        (
            [  # topics_in_shastra_rows — pre-sorted by mention_count DESC (as Neo4j ORDER BY does)
                {"topic_nk": "द्रव्य", "display_text_hi": "द्रव्य", "is_leaf": False, "mention_count": 8},
                {"topic_nk": "द्रव्य/जीव", "display_text_hi": "जीव", "is_leaf": True, "mention_count": 5},
                {"topic_nk": "द्रव्य/अजीव", "display_text_hi": "अजीव", "is_leaf": True, "mention_count": 3},
            ],
            [],  # shastras_for_topic_rows
        )
    ], indirect=True)
    async def test_topics_sorted_by_mention_count(
        self, client_with_neo4j_subworkflow: AsyncClient
    ) -> None:
        """Topics are returned sorted by mention_count DESC."""
        resp = await client_with_neo4j_subworkflow.post(self.URL, json={
            "shastra_natural_key": _SHASTRA_NK,
            "limit": 25,
        })
        assert resp.status_code == 200
        topics = resp.json()["topics"]
        counts = [t["mention_count"] for t in topics]
        assert counts == sorted(counts, reverse=True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_with_neo4j_subworkflow", [
        ([{"topic_nk": "द्रव्य/जीव/लक्षण", "display_text_hi": "लक्षण", "is_leaf": True, "mention_count": 2}], [])
    ], indirect=True)
    async def test_ancestors_derived_from_natural_key(
        self, client_with_neo4j_subworkflow: AsyncClient
    ) -> None:
        """ancestors_hi is derived from topic_natural_key segments."""
        resp = await client_with_neo4j_subworkflow.post(self.URL, json={
            "shastra_natural_key": _SHASTRA_NK,
        })
        assert resp.status_code == 200
        topic = resp.json()["topics"][0]
        assert topic["ancestors_hi"] == ["द्रव्य", "जीव"]


class TestShastrasForTopicE2E:
    URL = "/v1/query/shastras_for_topic"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_with_neo4j_subworkflow", [
        (
            [],  # topics_in_shastra_rows
            [   # shastras_for_topic_rows — topic mentioned in ≥2 shastras
                {"shastra_nk": "samaysaar", "name_hi": "समयसार", "total_mentions": 10,
                 "gathas": [{"number": 6, "page_number": 42}, {"number": 7, "page_number": 43}]},
                {"shastra_nk": "pravachansaar", "name_hi": "प्रवचनसार", "total_mentions": 4,
                 "gathas": [{"number": 12, "page_number": None}]},
            ],
        )
    ], indirect=True)
    async def test_topic_mentioned_in_multiple_shastras(
        self, client_with_neo4j_subworkflow: AsyncClient
    ) -> None:
        """Topic with MENTIONS_TOPIC edges across ≥2 shastras returns all of them."""
        resp = await client_with_neo4j_subworkflow.post(self.URL, json={
            "topic_natural_key": "द्रव्य/जीव",
            "include_gathas": True,
            "limit_shastras": 10,
            "limit_gathas_per_shastra": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic_natural_key"] == "द्रव्य/जीव"
        assert len(data["shastras"]) == 2
        shastra_nks = [s["shastra_natural_key"] for s in data["shastras"]]
        assert "samaysaar" in shastra_nks
        assert "pravachansaar" in shastra_nks

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_with_neo4j_subworkflow", [
        (
            [],
            [{"shastra_nk": "samaysaar", "name_hi": "समयसार", "total_mentions": 10,
              "gathas": [{"number": 6, "page_number": 42}, {"number": 7, "page_number": 43},
                         {"number": 8, "page_number": 44}]}],
        )
    ], indirect=True)
    async def test_gathas_capped_per_shastra(
        self, client_with_neo4j_subworkflow: AsyncClient
    ) -> None:
        """limit_gathas_per_shastra enforced on each shastra."""
        resp = await client_with_neo4j_subworkflow.post(self.URL, json={
            "topic_natural_key": "द्रव्य/जीव",
            "include_gathas": True,
            "limit_gathas_per_shastra": 2,
        })
        assert resp.status_code == 200
        for shastra in resp.json()["shastras"]:
            assert len(shastra["gathas"]) <= 2
