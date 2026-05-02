"""Unit tests for parse_definitions.py."""

import pytest
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope, walk_subsection_tree
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.topic_keys import slug

FIXTURE_DIR = "workers/ingestion/jainkosh/tests/fixtures"


@pytest.fixture
def config():
    return load_config()


def load_html(name: str) -> str:
    path = f"{FIXTURE_DIR}/{name}.html"
    with open(path, encoding="utf-8") as f:
        return f.read()


def get_section(result, kind: str):
    for sec in result.page_sections:
        if sec.section_kind == kind:
            return sec
    return None


def parse_keyword(name: str):
    config = load_config()
    html = load_html(name)
    return parse_keyword_html(html, f"https://jainkosh.org/wiki/{name}", config)


class TestSiddhantkoshDefinitions:
    def test_atma_has_four_definitions(self, config):
        html = load_html("आत्मा")
        result = parse_keyword_html(html, "https://jainkosh.org/wiki/आत्मा", config)
        sec = get_section(result, "siddhantkosh")
        assert sec is not None
        assert len(sec.definitions) == 4

    def test_dravya_has_one_definition(self, config):
        html = load_html("द्रव्य")
        result = parse_keyword_html(html, "https://jainkosh.org/wiki/द्रव्य", config)
        sec = get_section(result, "siddhantkosh")
        assert sec is not None
        assert len(sec.definitions) == 1

    def test_paryay_siddhantkosh_has_one_definition(self, config):
        html = load_html("पर्याय")
        result = parse_keyword_html(html, "https://jainkosh.org/wiki/पर्याय", config)
        sec = get_section(result, "siddhantkosh")
        assert sec is not None
        assert len(sec.definitions) == 1


class TestPuraankoshDefinitions:
    def test_atma_puraankosh_has_two_definitions(self, config):
        html = load_html("आत्मा")
        result = parse_keyword_html(html, "https://jainkosh.org/wiki/आत्मा", config)
        sec = get_section(result, "puraankosh")
        assert sec is not None
        assert len(sec.definitions) == 2

    def test_dravya_puraankosh_has_one_definition(self, config):
        html = load_html("द्रव्य")
        result = parse_keyword_html(html, "https://jainkosh.org/wiki/द्रव्य", config)
        sec = get_section(result, "puraankosh")
        assert sec is not None
        assert len(sec.definitions) == 1

    def test_paryay_puraankosh_has_two_definitions(self, config):
        html = load_html("पर्याय")
        result = parse_keyword_html(html, "https://jainkosh.org/wiki/पर्याय", config)
        sec = get_section(result, "puraankosh")
        assert sec is not None
        assert len(sec.definitions) == 2


def test_label_before_dekhen_creates_synthetic_topic():
    result = parse_keyword("आत्मा")
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    all_subs = list(walk_subsection_tree(sk.subsections))
    label_topics = [s for s in all_subs if getattr(s, "label_topic_seed", False)]
    matched = [s for s in label_topics if s.heading_text == "बहिरात्मा, अंतरात्मा व परमात्मा"]
    assert len(matched) == 1
    t = matched[0]
    assert t.is_synthetic is True
    assert t.is_leaf is True
    assert t.topic_path is None
    assert t.label_topic_seed is True


def test_label_topic_natural_key_no_comma_split():
    label = "बहिरात्मा, अंतरात्मा व परमात्मा"
    expected_slug = "बहिरात्मा-अंतरात्मा-व-परमात्मा"
    assert slug(label, load_config()) == expected_slug


def test_envelope_idempotency_contract_present():
    result = parse_keyword("आत्मा")
    env = build_envelope(result)
    pg_topics = env.would_write["postgres"]["topics"]
    assert all("idempotency_contract" in t for t in pg_topics)
    sample = pg_topics[0]["idempotency_contract"]
    assert sample["conflict_key"] == ["natural_key"]
    assert sample["on_conflict"] == "do_update"
    assert "fields_replace" in sample
    assert "fields_append" in sample
