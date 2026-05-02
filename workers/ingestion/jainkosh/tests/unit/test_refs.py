"""Unit tests for refs.py (GRef extraction)."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import parse_block_stream
from workers.ingestion.jainkosh.refs import (
    extract_ref_text, extract_refs_from_node, is_leading_reference_node
)


@pytest.fixture
def config():
    return load_config()


def parse_node(html: str, selector: str = "body > *"):
    tree = HTMLParser(f"<body>{html}</body>")
    return tree.css_first(selector)


def parse_p_to_block(html: str, config):
    tree = HTMLParser(f"<body>{html}</body>")
    p = tree.css_first("p")
    blocks = parse_block_stream([p], config)
    assert len(blocks) == 1
    return blocks[0]


class TestExtractRefText:
    def test_simple_text(self, config):
        node = parse_node('<span class="GRef">राजवार्तिक/1/33</span>', "span.GRef")
        result = extract_ref_text(node, config)
        assert result == "राजवार्तिक/1/33"

    def test_strips_inner_anchor(self, config):
        node = parse_node(
            '<span class="GRef"><a href="/wiki/X">राजवार्तिक</a>/1/33</span>',
            "span.GRef"
        )
        result = extract_ref_text(node, config)
        # Should keep text, strip anchor tag
        assert "राजवार्तिक" in result
        assert "<a" not in result


class TestExtractRefsFromNode:
    def test_multiple_grefs(self, config):
        html = '<p><span class="GRef">ref1</span><span class="GRef">ref2</span></p>'
        node = parse_node(html, "p")
        refs = extract_refs_from_node(node, config)
        assert len(refs) == 2
        assert refs[0].text == "ref1"
        assert refs[1].text == "ref2"

    def test_inline_gref_stripped_from_text_devanagari(self, config):
        html = (
            '<p class="HindiText">उन-उन सद्भाव पर्यायों को प्राप्त होता है '
            '<span class="GRef">( राजवार्तिक/1/33/1/95/4 )</span>।</p>'
        )
        block = parse_p_to_block(html, config)
        assert block.kind == "hindi_text"
        assert "राजवार्तिक" not in block.text_devanagari
        assert block.text_devanagari.rstrip("। ").endswith("प्राप्त होता है")
        assert any(r.text == "( राजवार्तिक/1/33/1/95/4 )" for r in block.references)

    def test_inline_gref_brackets_collapsed(self, config):
        html = (
            '<p class="HindiText">द्रव्य कहते हैं। '
            '<span class="GRef">( राजवार्तिक/1/33 )</span> ।</p>'
        )
        block = parse_p_to_block(html, config)
        assert "( )" not in block.text_devanagari
        assert "  " not in block.text_devanagari

    def test_parsed_reference_stub_returns_none_in_v1_1_0(self, config):
        node = parse_node('<p><span class="GRef">पंचास्तिकाय/9</span></p>', "p")
        refs = extract_refs_from_node(node, config)
        assert len(refs) == 1
        assert refs[0].text == "पंचास्तिकाय/9"
        assert refs[0].parsed is None


class TestIsLeadingReferenceNode:
    def test_bare_gref_span(self, config):
        node = parse_node('<span class="GRef">ref</span>', "span.GRef")
        assert is_leading_reference_node(node, config) is True

    def test_p_with_only_grefs(self, config):
        html = '<p><span class="GRef">ref1</span><span class="GRef">ref2</span></p>'
        node = parse_node(html, "p")
        assert is_leading_reference_node(node, config) is True

    def test_p_with_other_content(self, config):
        html = '<p class="HindiText">some text <span class="GRef">ref</span></p>'
        node = parse_node(html, "p")
        assert is_leading_reference_node(node, config) is False

    def test_p_with_only_text_empty(self, config):
        node = parse_node("<p></p>", "p")
        assert is_leading_reference_node(node, config) is True

    def test_p_with_non_gref_span(self, config):
        html = '<p><span class="SanskritText">text</span></p>'
        node = parse_node(html, "p")
        assert is_leading_reference_node(node, config) is False
