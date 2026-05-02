from __future__ import annotations

import os
import sys
import uuid

import pytest
import pytest_asyncio

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)

from jain_kb_common.db.neo4j import get_driver, close_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints
from jain_kb_common.db.neo4j.schema_check import validate_edge_type, UnknownEdgeTypeError
from jain_kb_common.db.neo4j.upserts import (
    sync_keyword,
    sync_topic,
    sync_gatha,
    sync_shastra,
)
from jain_kb_common.db.neo4j.queries import (
    resolve_token,
    traverse_topics,
    shortest_path,
)

NEO4J_URL = os.environ.get("NEO4J_URL", "")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
_NEO4J_AVAILABLE = bool(NEO4J_URL and NEO4J_PASSWORD)
skip_no_neo4j = pytest.mark.skipif(not _NEO4J_AVAILABLE, reason="NEO4J_URL/NEO4J_PASSWORD not set")

TEST_DB = "neo4j"


# ---------------------------------------------------------------------------
# schema_check (no DB required)
# ---------------------------------------------------------------------------

def test_validate_known_edge_types():
    for t in ["IS_A", "PART_OF", "RELATED_TO", "ALIAS_OF", "MENTIONS_KEYWORD", "HAS_TOPIC", "MENTIONS_TOPIC", "IN_SHASTRA"]:
        validate_edge_type(t)  # must not raise


def test_validate_unknown_edge_type_raises():
    with pytest.raises(UnknownEdgeTypeError):
        validate_edge_type("INVENTED_EDGE")


def test_validate_edge_type_case_sensitive():
    with pytest.raises(UnknownEdgeTypeError):
        validate_edge_type("is_a")


# ---------------------------------------------------------------------------
# Fixtures (require Neo4j)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def driver():
    if not _NEO4J_AVAILABLE:
        pytest.skip("NEO4J_URL/NEO4J_PASSWORD not set")
    drv = get_driver(url=NEO4J_URL, user=NEO4J_USER, password=NEO4J_PASSWORD)
    await ensure_constraints(drv, database=TEST_DB)
    yield drv
    # teardown — wipe all nodes added during the test
    async with drv.session(database=TEST_DB) as session:
        await session.run("MATCH (n) DETACH DELETE n")
    await close_driver()


# ---------------------------------------------------------------------------
# ensure_constraints
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_ensure_constraints_idempotent(driver):
    # Running twice must not raise
    await ensure_constraints(driver, database=TEST_DB)


# ---------------------------------------------------------------------------
# sync_keyword
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_keyword_creates_node(driver):
    pg_id = str(uuid.uuid4())
    await sync_keyword(
        driver,
        natural_key="आत्मा",
        pg_id=pg_id,
        display_text="आत्मा",
        source_url="https://jainkosh.org/wiki/आत्मा",
        database=TEST_DB,
    )
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (k:Keyword {natural_key: $nk}) RETURN k.pg_id AS pg_id", nk="आत्मा"
        )
        record = await result.single()
    assert record is not None
    assert record["pg_id"] == pg_id


@skip_no_neo4j
async def test_sync_keyword_idempotent(driver):
    pg_id = str(uuid.uuid4())
    await sync_keyword(driver, natural_key="अहिंसा", pg_id=pg_id, display_text="अहिंसा v1", database=TEST_DB)
    await sync_keyword(driver, natural_key="अहिंसा", pg_id=pg_id, display_text="अहिंसा v2", database=TEST_DB)

    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (k:Keyword {natural_key: $nk}) RETURN count(k) AS cnt, k.display_text AS text",
            nk="अहिंसा",
        )
        record = await result.single()
    assert record["cnt"] == 1
    assert record["text"] == "अहिंसा v2"


@skip_no_neo4j
async def test_sync_keyword_with_aliases(driver):
    pg_id = str(uuid.uuid4())
    alias_pg_id = str(uuid.uuid4())
    aliases = [{"alias_text": "आतम", "pg_id": alias_pg_id, "source": "jainkosh_redirect"}]
    await sync_keyword(driver, natural_key="आत्मा-alias", pg_id=pg_id, display_text="आत्मा", aliases=aliases, database=TEST_DB)

    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (a:Alias {alias_text: $alias})-[:ALIAS_OF]->(k:Keyword {natural_key: $nk}) RETURN a.source AS src",
            alias="आतम", nk="आत्मा-alias",
        )
        record = await result.single()
    assert record is not None
    assert record["src"] == "jainkosh_redirect"


# ---------------------------------------------------------------------------
# sync_topic
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_topic_creates_node(driver):
    kw_pg_id = str(uuid.uuid4())
    tp_pg_id = str(uuid.uuid4())
    await sync_keyword(driver, natural_key="आत्मा-t", pg_id=kw_pg_id, display_text="आत्मा", database=TEST_DB)
    await sync_topic(
        driver,
        natural_key="jainkosh:आत्मा-t:बहिरात्मादि",
        pg_id=tp_pg_id,
        display_text_hi="बहिरात्मादि 3 भेद",
        source="jainkosh",
        parent_keyword_natural_key="आत्मा-t",
        database=TEST_DB,
    )
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (t:Topic {natural_key: $nk}) RETURN t.pg_id AS pg_id",
            nk="jainkosh:आत्मा-t:बहिरात्मादि",
        )
        record = await result.single()
    assert record["pg_id"] == tp_pg_id


@skip_no_neo4j
async def test_sync_topic_creates_has_topic_edge(driver):
    kw_pg_id = str(uuid.uuid4())
    tp_pg_id = str(uuid.uuid4())
    await sync_keyword(driver, natural_key="आत्मा-e", pg_id=kw_pg_id, display_text="आत्मा", database=TEST_DB)
    await sync_topic(
        driver,
        natural_key="jainkosh:आत्मा-e:भेद",
        pg_id=tp_pg_id,
        display_text_hi="भेद",
        source="jainkosh",
        parent_keyword_natural_key="आत्मा-e",
        database=TEST_DB,
    )
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (k:Keyword {natural_key: $kw})-[:HAS_TOPIC]->(t:Topic {natural_key: $tp}) RETURN count(*) AS cnt",
            kw="आत्मा-e", tp="jainkosh:आत्मा-e:भेद",
        )
        record = await result.single()
    assert record["cnt"] == 1


@skip_no_neo4j
async def test_sync_topic_idempotent(driver):
    pg_id = str(uuid.uuid4())
    await sync_topic(driver, natural_key="topic:idem", pg_id=pg_id, display_text_hi="v1", source="jainkosh", database=TEST_DB)
    await sync_topic(driver, natural_key="topic:idem", pg_id=pg_id, display_text_hi="v2", source="jainkosh", database=TEST_DB)

    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (t:Topic {natural_key: $nk}) RETURN count(t) AS cnt, t.display_text_hi AS text",
            nk="topic:idem",
        )
        record = await result.single()
    assert record["cnt"] == 1
    assert record["text"] == "v2"


@skip_no_neo4j
async def test_sync_topic_with_mentioned_keywords(driver):
    kw_pg_id = str(uuid.uuid4())
    tp_pg_id = str(uuid.uuid4())
    await sync_keyword(driver, natural_key="धर्म", pg_id=kw_pg_id, display_text="धर्म", database=TEST_DB)
    await sync_topic(
        driver,
        natural_key="topic:mentions",
        pg_id=tp_pg_id,
        display_text_hi="test topic",
        source="jainkosh",
        mentioned_keyword_natural_keys=["धर्म"],
        database=TEST_DB,
    )
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (t:Topic {natural_key: $tp})-[:MENTIONS_KEYWORD]->(k:Keyword {natural_key: $kw}) RETURN count(*) AS cnt",
            tp="topic:mentions", kw="धर्म",
        )
        record = await result.single()
    assert record["cnt"] == 1


# ---------------------------------------------------------------------------
# sync_shastra
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_shastra_idempotent(driver):
    pg_id = str(uuid.uuid4())
    await sync_shastra(driver, natural_key="pravachansaar", pg_id=pg_id, title_hi="प्रवचनसार", author_natural_key="kundkund", database=TEST_DB)
    await sync_shastra(driver, natural_key="pravachansaar", pg_id=pg_id, title_hi="प्रवचनसार (updated)", author_natural_key="kundkund", database=TEST_DB)

    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (s:Shastra {natural_key: $nk}) RETURN count(s) AS cnt, s.title_hi AS title",
            nk="pravachansaar",
        )
        record = await result.single()
    assert record["cnt"] == 1
    assert record["title"] == "प्रवचनसार (updated)"


# ---------------------------------------------------------------------------
# sync_gatha
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_gatha_creates_in_shastra_edge(driver):
    s_pg_id = str(uuid.uuid4())
    g_pg_id = str(uuid.uuid4())
    await sync_shastra(driver, natural_key="ps", pg_id=s_pg_id, title_hi="प्रवचनसार", database=TEST_DB)
    await sync_gatha(
        driver,
        natural_key="ps:039",
        pg_id=g_pg_id,
        shastra_natural_key="ps",
        gatha_number="039",
        heading_hi="मंगलाचरण",
        database=TEST_DB,
    )
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (g:Gatha {natural_key: $gnk})-[:IN_SHASTRA]->(s:Shastra {natural_key: $snk}) RETURN count(*) AS cnt",
            gnk="ps:039", snk="ps",
        )
        record = await result.single()
    assert record["cnt"] == 1


@skip_no_neo4j
async def test_sync_gatha_idempotent(driver):
    s_pg_id = str(uuid.uuid4())
    g_pg_id = str(uuid.uuid4())
    await sync_shastra(driver, natural_key="ps2", pg_id=s_pg_id, title_hi="प्रवचनसार", database=TEST_DB)
    await sync_gatha(driver, natural_key="ps2:001", pg_id=g_pg_id, shastra_natural_key="ps2", gatha_number="001", database=TEST_DB)
    await sync_gatha(driver, natural_key="ps2:001", pg_id=g_pg_id, shastra_natural_key="ps2", gatha_number="001", heading_hi="updated", database=TEST_DB)

    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (g:Gatha {natural_key: $nk}) RETURN count(g) AS cnt, g.heading_hi AS heading",
            nk="ps2:001",
        )
        record = await result.single()
    assert record["cnt"] == 1
    assert record["heading"] == "updated"


# ---------------------------------------------------------------------------
# queries: resolve_token
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_resolve_token_direct_keyword(driver):
    pg_id = str(uuid.uuid4())
    await sync_keyword(driver, natural_key="ज्ञान", pg_id=pg_id, display_text="ज्ञान", database=TEST_DB)
    result = await resolve_token(driver, token="ज्ञान", database=TEST_DB)
    assert result is not None
    assert result["keyword_nk"] == "ज्ञान"
    assert result["keyword_pg_id"] == pg_id


@skip_no_neo4j
async def test_resolve_token_via_alias(driver):
    pg_id = str(uuid.uuid4())
    alias_pg_id = str(uuid.uuid4())
    aliases = [{"alias_text": "ज्ञान-alias", "pg_id": alias_pg_id, "source": "admin"}]
    await sync_keyword(driver, natural_key="ज्ञान-base", pg_id=pg_id, display_text="ज्ञान", aliases=aliases, database=TEST_DB)
    result = await resolve_token(driver, token="ज्ञान-alias", database=TEST_DB)
    assert result is not None
    assert result["keyword_nk"] == "ज्ञान-base"


@skip_no_neo4j
async def test_resolve_token_unknown(driver):
    result = await resolve_token(driver, token="अज्ञात-xyz-notexist", database=TEST_DB)
    assert result is None


# ---------------------------------------------------------------------------
# queries: traverse_topics
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_traverse_topics_returns_results(driver):
    kw_pg_id = str(uuid.uuid4())
    tp_pg_id = str(uuid.uuid4())
    await sync_keyword(driver, natural_key="kw-traverse", pg_id=kw_pg_id, display_text="test", database=TEST_DB)
    await sync_topic(
        driver,
        natural_key="tp-traverse",
        pg_id=tp_pg_id,
        display_text_hi="traverse topic",
        source="jainkosh",
        parent_keyword_natural_key="kw-traverse",
        database=TEST_DB,
    )
    results = await traverse_topics(driver, seed_keyword_nks=["kw-traverse"], top_k=5, database=TEST_DB)
    assert any(r["topic_nk"] == "tp-traverse" for r in results)


# ---------------------------------------------------------------------------
# queries: shortest_path
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_shortest_path_connected(driver):
    kw_pg_id = str(uuid.uuid4())
    tp1_pg_id = str(uuid.uuid4())
    tp2_pg_id = str(uuid.uuid4())
    await sync_keyword(driver, natural_key="kw-path", pg_id=kw_pg_id, display_text="kw", database=TEST_DB)
    await sync_topic(driver, natural_key="tp-path-1", pg_id=tp1_pg_id, display_text_hi="tp1", source="jainkosh", parent_keyword_natural_key="kw-path", database=TEST_DB)
    await sync_topic(driver, natural_key="tp-path-2", pg_id=tp2_pg_id, display_text_hi="tp2", source="jainkosh", parent_keyword_natural_key="kw-path", database=TEST_DB)
    # Add IS_A edge: tp-path-2 IS_A tp-path-1
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            "MATCH (a:Topic {natural_key: $a}), (b:Topic {natural_key: $b}) MERGE (a)-[:IS_A]->(b)",
            a="tp-path-2", b="tp-path-1",
        )
    path = await shortest_path(driver, from_nk="tp-path-1", to_nk="tp-path-2", database=TEST_DB)
    assert path is not None


@skip_no_neo4j
async def test_shortest_path_disconnected(driver):
    tp1_pg_id = str(uuid.uuid4())
    tp2_pg_id = str(uuid.uuid4())
    await sync_topic(driver, natural_key="tp-dis-1", pg_id=tp1_pg_id, display_text_hi="d1", source="jainkosh", database=TEST_DB)
    await sync_topic(driver, natural_key="tp-dis-2", pg_id=tp2_pg_id, display_text_hi="d2", source="jainkosh", database=TEST_DB)
    path = await shortest_path(driver, from_nk="tp-dis-1", to_nk="tp-dis-2", database=TEST_DB)
    assert path is None
