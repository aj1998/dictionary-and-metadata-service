from datetime import datetime

from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.models import KeywordParseResult, Nav, PageSection, Subsection


def _result_with_topics():
    sub = Subsection(
        topic_path="1",
        heading_text="t1",
        heading_path=["t1"],
        natural_key="k:t1",
        parent_natural_key=None,
        is_leaf=True,
        blocks=[],
        children=[],
    )
    sec = PageSection(
        section_kind="siddhantkosh",
        section_index=0,
        h2_text="सिद्धांतकोष से",
        definitions=[],
        index_relations=[],
        subsections=[sub],
    )
    return KeywordParseResult(
        keyword="k",
        source_url="https://example/",
        page_sections=[sec],
        nav=Nav(),
        parser_version="jainkosh.rules/1.2.0",
        parsed_at=datetime(2026, 5, 2),
    )


def test_idempotency_contracts_at_envelope_root():
    env = build_envelope(_result_with_topics()).would_write
    assert "idempotency_contracts" in env
    contracts = env["idempotency_contracts"]
    assert "postgres:keywords" in contracts
    assert contracts["postgres:keywords"]["conflict_key"] == ["natural_key"]
    assert "postgres:topics" in contracts
    assert "mongo:keyword_definitions" in contracts
    assert "mongo:topic_extracts" in contracts


def test_no_per_row_idempotency_contract_in_postgres_rows():
    env = build_envelope(_result_with_topics()).would_write
    for row in env["postgres"]["keywords"]:
        assert "idempotency_contract" not in row
    for row in env["postgres"]["topics"]:
        assert "idempotency_contract" not in row


def test_no_per_row_idempotency_contract_in_mongo_rows():
    env = build_envelope(_result_with_topics()).would_write
    for row in env["mongo"]["keyword_definitions"]:
        assert "idempotency_contract" not in row
    for row in env["mongo"]["topic_extracts"]:
        assert "idempotency_contract" not in row
