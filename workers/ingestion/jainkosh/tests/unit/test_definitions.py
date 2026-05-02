"""Unit tests for parse_definitions.py."""

import pytest
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

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
