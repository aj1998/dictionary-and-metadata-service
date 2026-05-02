"""Unit tests for see_also.py."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.see_also import parse_anchor, find_see_alsos_in_element
from workers.ingestion.jainkosh.models import Block, IndexRelation


@pytest.fixture
def config():
    return load_config()


def parse_node(html: str, selector: str = "body > *"):
    tree = HTMLParser(f"<body>{html}</body>")
    return tree.css_first(selector)


class TestParseAnchor:
    def test_wiki_link(self, config):
        node = parse_node('<a href="/wiki/जीव">जीव</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_keyword"] == "जीव"
        assert result["is_self"] is False
        assert result["target_exists"] is True

    def test_wiki_link_with_fragment(self, config):
        node = parse_node('<a href="/wiki/मोक्षमार्ग#2.5">text</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_keyword"] == "मोक्षमार्ग"
        assert result["target_topic_path"] == "2.5"

    def test_self_link(self, config):
        node = parse_node('<a class="mw-selflink-fragment" href="#1.2">text</a>', "a")
        result = parse_anchor(node, config, current_keyword="द्रव्य")
        assert result["is_self"] is True
        assert result["target_topic_path"] == "1.2"

    def test_redlink(self, config):
        node = parse_node('<a href="/w/index.php?title=X&action=edit&redlink=1">X</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_exists"] is False

    def test_underscore_to_space(self, config):
        node = parse_node('<a href="/wiki/वह_वह_नाम">text</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_keyword"] == "वह वह नाम"


class TestFindSeeAlsos:
    def test_simple_see_also_block(self, config):
        html = '<p class="HindiText">• देखें<a href="/wiki/जीव">जीव</a></p>'
        node = parse_node(html, "p")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=False)
        assert len(results) == 1
        item = results[0]
        assert isinstance(item, Block)
        assert item.kind == "see_also"
        assert item.target_keyword == "जीव"

    def test_inline_see_also_with_fragment(self, config):
        html = '<p class="HindiText">पाठ। देखें<a href="/wiki/मोक्षमार्ग#2.5">मोक्षमार्ग - 2.5</a></p>'
        node = parse_node(html, "p")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=False)
        assert len(results) == 1
        assert results[0].target_topic_path == "2.5"

    def test_index_see_also_returns_index_relation(self, config):
        html = '<ul><li>देखें <a href="/wiki/जीव">जीव</a></li></ul>'
        node = parse_node(html, "ul")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=True)
        assert len(results) == 1
        assert isinstance(results[0], IndexRelation)

    def test_no_see_also_returns_empty(self, config):
        # Link without "देखें" pattern should not produce see_also
        html = '<p class="HindiText">यह भी पढ़ें <a href="/wiki/जीव">जीव</a></p>'
        node = parse_node(html, "p")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=False)
        assert len(results) == 0
