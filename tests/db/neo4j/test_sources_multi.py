"""Tests for the multi-source `sources` list property on Neo4j nodes (phase 03)."""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "jain_kb_common"),
)

from jain_kb_common.db.neo4j import get_driver, close_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints
from jain_kb_common.db.neo4j.stubs import sync_stub_node
from jain_kb_common.db.neo4j.upserts import (
    sync_keyword,
    sync_shastra,
    sync_topic,
    sync_gatha,
    sync_teeka,
    sync_publication,
    sync_kalash,
    sync_gatha_teeka,
    sync_gatha_teeka_bhaavarth,
    sync_kalash_bhaavarth,
    sync_table,
)

NEO4J_URL = os.environ.get("NEO4J_URL", "")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
_NEO4J_AVAILABLE = bool(NEO4J_URL and NEO4J_PASSWORD)
skip_no_neo4j = pytest.mark.skipif(not _NEO4J_AVAILABLE, reason="NEO4J_URL/NEO4J_PASSWORD not set")

TEST_DB = "neo4j"
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def driver():
    if not _NEO4J_AVAILABLE:
        pytest.skip("NEO4J_URL/NEO4J_PASSWORD not set")
    drv = get_driver(url=NEO4J_URL, user=NEO4J_USER, password=NEO4J_PASSWORD)
    await ensure_constraints(drv, database=TEST_DB)
    yield drv
    async with drv.session(database=TEST_DB) as session:
        await session.run("MATCH (n) DETACH DELETE n")
    await close_driver()


# ---------------------------------------------------------------------------
# sync_stub_node — sources set-union
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_stub_node_first_source(driver):
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X", props={}, source="jainkosh", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (n:Shastra {natural_key: $nk}) RETURN n.sources AS sources",
            nk="src-test-X",
        )
        record = await result.single()
    assert record is not None
    assert record["sources"] == ["jainkosh"]


@skip_no_neo4j
async def test_stub_node_second_source_union(driver):
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X2", props={}, source="jainkosh", database=TEST_DB)
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X2", props={}, source="nj", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (n:Shastra {natural_key: $nk}) RETURN n.sources AS sources",
            nk="src-test-X2",
        )
        record = await result.single()
    sources = sorted(record["sources"])
    assert sources == ["jainkosh", "nj"]


@skip_no_neo4j
async def test_stub_node_duplicate_source_no_growth(driver):
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X3", props={}, source="jainkosh", database=TEST_DB)
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X3", props={}, source="nj", database=TEST_DB)
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X3", props={}, source="jainkosh", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (n:Shastra {natural_key: $nk}) RETURN n.sources AS sources",
            nk="src-test-X3",
        )
        record = await result.single()
    assert len(record["sources"]) == 2


@skip_no_neo4j
async def test_stub_node_none_source_leaves_sources_untouched(driver):
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X4", props={}, source="jainkosh", database=TEST_DB)
    await sync_stub_node(driver, label="Shastra", natural_key="src-test-X4", props={}, source=None, database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (n:Shastra {natural_key: $nk}) RETURN n.sources AS sources",
            nk="src-test-X4",
        )
        record = await result.single()
    assert record["sources"] == ["jainkosh"]


# ---------------------------------------------------------------------------
# sync_keyword — sources set-union
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_keyword_sources_union(driver):
    await sync_keyword(driver, natural_key="kw-src-test", pg_id="pg1", display_text="test", source="jainkosh", database=TEST_DB)
    await sync_keyword(driver, natural_key="kw-src-test", pg_id="pg1", display_text="test", source="nj", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (k:Keyword {natural_key: $nk}) RETURN k.sources AS sources",
            nk="kw-src-test",
        )
        record = await result.single()
    assert sorted(record["sources"]) == ["jainkosh", "nj"]


@skip_no_neo4j
async def test_sync_keyword_none_source_leaves_untouched(driver):
    await sync_keyword(driver, natural_key="kw-src-none", pg_id="pg2", display_text="test", source="jainkosh", database=TEST_DB)
    await sync_keyword(driver, natural_key="kw-src-none", pg_id="pg2", display_text="test", source=None, database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (k:Keyword {natural_key: $nk}) RETURN k.sources AS sources",
            nk="kw-src-none",
        )
        record = await result.single()
    assert record["sources"] == ["jainkosh"]


# ---------------------------------------------------------------------------
# sync_shastra — sources set-union
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_shastra_sources_union(driver):
    await sync_shastra(driver, natural_key="ss-src-test", pg_id="pg3", title_hi="test", source="jainkosh", database=TEST_DB)
    await sync_shastra(driver, natural_key="ss-src-test", pg_id="pg3", title_hi="test", source="nj", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (s:Shastra {natural_key: $nk}) RETURN s.sources AS sources",
            nk="ss-src-test",
        )
        record = await result.single()
    assert sorted(record["sources"]) == ["jainkosh", "nj"]


# ---------------------------------------------------------------------------
# sync_topic — dual write (existing source + new sources list)
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_topic_sources_dual_write(driver):
    await sync_topic(driver, natural_key="tp-src-test", pg_id="pg4", display_text_hi="test", source="jainkosh", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (t:Topic {natural_key: $nk}) RETURN t.source AS source, t.sources AS sources",
            nk="tp-src-test",
        )
        record = await result.single()
    assert record["source"] == "jainkosh"
    assert record["sources"] == ["jainkosh"]


# ---------------------------------------------------------------------------
# sync_gatha — sources set-union
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_gatha_sources_union(driver):
    await sync_shastra(driver, natural_key="ps-gsrc", pg_id="pg5a", title_hi="test", database=TEST_DB)
    await sync_gatha(driver, natural_key="ps-gsrc:001", pg_id="pg5", shastra_natural_key="ps-gsrc", gatha_number="001", source="nj", database=TEST_DB)
    await sync_gatha(driver, natural_key="ps-gsrc:001", pg_id="pg5", shastra_natural_key="ps-gsrc", gatha_number="001", source="jainkosh", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (g:Gatha {natural_key: $nk}) RETURN g.sources AS sources",
            nk="ps-gsrc:001",
        )
        record = await result.single()
    assert sorted(record["sources"]) == ["jainkosh", "nj"]


# ---------------------------------------------------------------------------
# sync_table — dual write (existing source + new sources list)
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_table_sources_dual_write(driver):
    await sync_table(
        driver,
        natural_key="table-src-test",
        pg_id="pg6",
        source="nj",
        parent_natural_key="parent-src-test",
        parent_kind="keyword",
        seq=1,
        database=TEST_DB,
    )
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (t:Table {natural_key: $nk}) RETURN t.source AS source, t.sources AS sources",
            nk="table-src-test",
        )
        record = await result.single()
    assert record["source"] == "nj"
    assert record["sources"] == ["nj"]


# ---------------------------------------------------------------------------
# sync_teeka — sources set-union
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_teeka_sources_union(driver):
    await sync_shastra(driver, natural_key="ps-tsrc", pg_id="pg7a", title_hi="test", database=TEST_DB)
    await sync_teeka(driver, natural_key="ps-tsrc:ac", pg_id="pg7", shastra_natural_key="ps-tsrc", source="jainkosh", database=TEST_DB)
    await sync_teeka(driver, natural_key="ps-tsrc:ac", pg_id="pg7", shastra_natural_key="ps-tsrc", source="nj", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (t:Teeka {natural_key: $nk}) RETURN t.sources AS sources",
            nk="ps-tsrc:ac",
        )
        record = await result.single()
    assert sorted(record["sources"]) == ["jainkosh", "nj"]


# ---------------------------------------------------------------------------
# sync_publication — sources set-union
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_publication_sources_union(driver):
    await sync_shastra(driver, natural_key="ps-psrc", pg_id="pg8a", title_hi="test", database=TEST_DB)
    await sync_teeka(driver, natural_key="ps-psrc:ac", pg_id="pg8b", shastra_natural_key="ps-psrc", database=TEST_DB)
    await sync_publication(driver, natural_key="ps-psrc:ac:jzb", pg_id="pg8", teeka_natural_key="ps-psrc:ac", publisher_id="jzb", source="jainkosh", database=TEST_DB)
    await sync_publication(driver, natural_key="ps-psrc:ac:jzb", pg_id="pg8", teeka_natural_key="ps-psrc:ac", publisher_id="jzb", source="nj", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (p:Publication {natural_key: $nk}) RETURN p.sources AS sources",
            nk="ps-psrc:ac:jzb",
        )
        record = await result.single()
    assert sorted(record["sources"]) == ["jainkosh", "nj"]


# ---------------------------------------------------------------------------
# sync_kalash — sources set-union
# ---------------------------------------------------------------------------

@skip_no_neo4j
async def test_sync_kalash_sources_union(driver):
    await sync_shastra(driver, natural_key="ps-ksrc", pg_id="pg9a", title_hi="test", database=TEST_DB)
    await sync_teeka(driver, natural_key="ps-ksrc:ac", pg_id="pg9b", shastra_natural_key="ps-ksrc", database=TEST_DB)
    await sync_kalash(driver, natural_key="ps-ksrc:ac:001", pg_id="pg9", teeka_natural_key="ps-ksrc:ac", kalash_number="001", source="nj", database=TEST_DB)
    await sync_kalash(driver, natural_key="ps-ksrc:ac:001", pg_id="pg9", teeka_natural_key="ps-ksrc:ac", kalash_number="001", source="jainkosh", database=TEST_DB)
    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (k:Kalash {natural_key: $nk}) RETURN k.sources AS sources",
            nk="ps-ksrc:ac:001",
        )
        record = await result.single()
    assert sorted(record["sources"]) == ["jainkosh", "nj"]
