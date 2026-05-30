"""Unit tests for refs.py (GRef extraction)."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import parse_block_stream
from workers.ingestion.jainkosh.refs import (
    extract_ref_text, extract_refs_from_node, is_leading_reference_node
)


class TestSemicolonSplit:
    def test_semicolon_split_basic(self, config):
        """A GRef containing '(ref1); (ref2)' produces two Reference objects."""
        html = '<p><span class="GRef">( नयचक्र बृहद्/17 ); ( द्रव्यसंग्रह/1 )</span></p>'
        node = HTMLParser(f"<body>{html}</body>").css_first("p")
        refs = extract_refs_from_node(node, config)
        assert len(refs) == 2
        assert refs[0].text == "( नयचक्र बृहद्/17 )"
        assert refs[1].text == "( द्रव्यसंग्रह/1 )"

    def test_semicolon_split_disabled(self, config):
        """With semicolon_split.enabled=False, semicolon-delimited GRef stays as one Reference."""
        html = '<p><span class="GRef">( नयचक्र बृहद्/17 ); ( द्रव्यसंग्रह/1 )</span></p>'
        node = HTMLParser(f"<body>{html}</body>").css_first("p")
        cfg = config.model_copy(deep=True)
        cfg.reference.semicolon_split.enabled = False
        refs = extract_refs_from_node(node, cfg)
        assert len(refs) == 1
        assert ";" in refs[0].text

    def test_semicolon_split_preserves_internal_semicolons(self, config):
        """A GRef like '(abc; def)' (no paren at boundary) is NOT split."""
        html = '<p><span class="GRef">( abc; def )</span></p>'
        node = HTMLParser(f"<body>{html}</body>").css_first("p")
        refs = extract_refs_from_node(node, config)
        assert len(refs) == 1
        assert refs[0].text == "( abc; def )"

    def test_semicolon_split_three_parts(self, config):
        """Three-way split '(r1); (r2); (r3)' produces three Reference objects."""
        html = '<p><span class="GRef">( r1 ); ( r2 ); ( r3 )</span></p>'
        node = HTMLParser(f"<body>{html}</body>").css_first("p")
        refs = extract_refs_from_node(node, config)
        assert len(refs) == 3
        assert refs[0].text == "( r1 )"
        assert refs[1].text == "( r2 )"
        assert refs[2].text == "( r3 )"


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

    def test_structured_parsing_populates_resolved_fields(self, config):
        node = parse_node('<p><span class="GRef">पंचास्तिकाय/9</span></p>', "p")
        refs = extract_refs_from_node(node, config)
        assert len(refs) == 1
        assert refs[0].text == "पंचास्तिकाय/9"
        assert isinstance(refs[0].needs_manual_match, bool)
        assert refs[0].shastra_name == "पंचास्तिकाय"


class TestStripRefsFromText:
    """Tests for strip_refs_from_text: trailing-semicolon cleanup and flexible whitespace."""

    def test_trailing_semicolons_between_grefs_stripped(self, config):
        """Stray semicolons left between adjacent GRef spans are removed from text_devanagari.

        HTML pattern: prose <span class="GRef">(ref1)</span>\n;  <span class="GRef">(ref2)</span>
        After stripping refs, the '; ' line should disappear.
        """
        html = (
            '<p class="HindiText">गुण और पर्यायों वाला द्रव्य है। '
            '<span class="GRef">( नियमसार/9 )</span>\n'
            ';  <span class="GRef">( प्रवचनसार/95 )</span>\n'
            '</p>'
        )
        block = parse_p_to_block(html, config)
        assert block.kind == "hindi_text"
        assert ";" not in block.text_devanagari, (
            f"Stray semicolon found in text_devanagari: {block.text_devanagari!r}"
        )
        assert "गुण और पर्यायों वाला द्रव्य है।" in block.text_devanagari

    def test_multiple_trailing_semicolons_stripped(self, config):
        """Multiple stray semicolons (one per GRef separator) are all removed."""
        html = (
            '<p class="HindiText">द्रव्य है।'
            '<span class="GRef">( ref1 )</span>\n'
            ';  <span class="GRef">( ref2 )</span>\n'
            ';  <span class="GRef">( ref3 )</span>\n'
            ';  <span class="GRef">( ref4 )</span>\n'
            '</p>'
        )
        block = parse_p_to_block(html, config)
        assert ";" not in block.text_devanagari, (
            f"Stray semicolons in text: {block.text_devanagari!r}"
        )
        assert "द्रव्य है।" in block.text_devanagari

    def test_ref_with_html_source_newline_stripped(self, config):
        """A GRef whose inner text has an HTML-source newline (not <br>) is stripped.

        This covers the हरिवंशपुराण case: the GRef HTML has a raw newline between
        the anchor text and the continuation ', 2.108, 17.135'. After rendering, the
        block text has a newline where ref.text has a space — but the ref must still
        be stripped from text_devanagari.
        """
        # Simulate the HTML pattern with indentation that creates ref.text with \n + space
        # while _render_inline normalises each line (stripping leading space after \n).
        html = (
            '<p class="HindiText">ज्ञेय होता है। '
            '<span class="GRef">'
            '<a href="/wiki/X">हरिवंशपुराण - 1.1</a>\n'
            '    , 2.108, 17.135\n'
            '</span></p>'
        )
        block = parse_p_to_block(html, config)
        assert "हरिवंशपुराण" not in block.text_devanagari, (
            f"Reference text not stripped from text_devanagari: {block.text_devanagari!r}"
        )
        assert "ज्ञेय होता है।" in block.text_devanagari

    def test_legitimate_inline_semicolon_preserved(self, config):
        """A semicolon within prose (not on its own line) is NOT removed."""
        html = (
            '<p class="HindiText">गुणों के समुदाय को द्रव्य कहते हैं; '
            'केवल इतने से भी कोई आचार्य द्रव्य का लक्षण करते हैं।</p>'
        )
        block = parse_p_to_block(html, config)
        assert ";" in block.text_devanagari, (
            "Inline prose semicolon was incorrectly removed"
        )


class TestIsBulletPoint:
    def test_is_bullet_point_set_for_li_element(self, config):
        """A block produced from an <li> node gets is_bullet_point=True."""
        html = '<li class="HindiText">कोई पाठ</li>'
        tree = HTMLParser(f"<body>{html}</body>")
        node = tree.css_first("li")
        blocks = parse_block_stream([node], config)
        assert len(blocks) == 1
        assert blocks[0].is_bullet_point is True

    def test_is_bullet_point_false_for_p_element(self, config):
        """A block produced from a <p> node gets is_bullet_point=False."""
        html = '<p class="HindiText">कोई पाठ</p>'
        tree = HTMLParser(f"<body>{html}</body>")
        node = tree.css_first("p")
        blocks = parse_block_stream([node], config)
        assert len(blocks) == 1
        assert blocks[0].is_bullet_point is False

    def test_is_bullet_point_flag_disabled(self, config):
        """With is_bullet_point_for_li=False, even <li>-origin blocks get is_bullet_point=False."""
        from workers.ingestion.jainkosh.config import BlocksConfig
        cfg = config.model_copy(update={"blocks": BlocksConfig(is_bullet_point_for_li=False)})
        html = '<li class="HindiText">कोई पाठ</li>'
        tree = HTMLParser(f"<body>{html}</body>")
        node = tree.css_first("li")
        blocks = parse_block_stream([node], cfg)
        assert len(blocks) == 1
        assert blocks[0].is_bullet_point is False


class TestInlineReferenceFlag:
    def test_extract_refs_leading_sets_inline_false(self, config):
        """Leading refs (extracted from pending_refs buffer) have inline_reference=False."""
        node = HTMLParser('<p><span class="GRef">सर्वार्थसिद्धि/1/5/17/5</span></p>').css_first("p")
        refs = extract_refs_from_node(node, config, inline=False)
        assert len(refs) == 1
        assert refs[0].inline_reference is False

    def test_extract_refs_inline_sets_inline_true(self, config):
        """Inline/trailing refs (embedded in text blocks) have inline_reference=True."""
        node = HTMLParser(
            '<p class="HindiText">some text <span class="GRef">( धवला 1/1,1,1/84/1 )</span></p>'
        ).css_first("p")
        refs = extract_refs_from_node(node, config, inline=True)
        assert len(refs) == 1
        assert refs[0].inline_reference is True

    def test_annotate_inline_position_false_always_returns_false(self, config):
        """When annotate_inline_position=False, inline_reference is always False."""
        cfg = config.model_copy(deep=True)
        cfg.reference.annotate_inline_position = False
        node = HTMLParser('<p><span class="GRef">ref text</span></p>').css_first("p")
        refs = extract_refs_from_node(node, cfg, inline=True)
        assert refs[0].inline_reference is False


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
