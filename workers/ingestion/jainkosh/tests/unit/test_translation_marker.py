"""Unit tests for translation marker absorption in parse_blocks.py."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import parse_block_stream


@pytest.fixture
def config():
    return load_config()


def make_elements(html: str):
    tree = HTMLParser(f"<body>{html}</body>")
    return [c for c in tree.css_first("body").iter(include_text=False)]


def parse_li_to_blocks(html: str, config):
    tree = HTMLParser(f"<body>{html}</body>")
    li = tree.css_first("li")
    children = [c for c in li.iter(include_text=False) if c != li]
    return parse_block_stream(children, config)


def parse_p_to_block_with_prev_source(html: str, config):
    wrapper = f'<body><p class="SanskritText">सूत्र</p>{html}</body>'
    tree = HTMLParser(wrapper)
    elements = [c for c in tree.css_first("body").iter(include_text=False)]
    blocks = parse_block_stream(elements, config)
    assert len(blocks) == 1
    return blocks[0]


class TestTranslationMarker:
    def test_hindi_after_sanskrit_absorbed(self, config):
        html = """
        <p class="SanskritText">आत्मा द्वादशांगम्</p>
        <p class="HindiText">= द्वादशांग का नाम आत्मा है</p>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert len(blocks) == 1
        assert blocks[0].kind == "sanskrit_text"
        assert blocks[0].hindi_translation == "द्वादशांग का नाम आत्मा है"

    def test_hindi_after_prakrit_absorbed(self, config):
        html = """
        <p class="PrakritText">तिपयारो सो अप्पा</p>
        <p class="HindiText">= सो आत्मा तीन प्रकार है</p>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert len(blocks) == 1
        assert blocks[0].kind == "prakrit_text"
        assert blocks[0].hindi_translation == "सो आत्मा तीन प्रकार है"

    def test_orphan_translation_no_preceding_source(self, config):
        html = """
        <p class="HindiText">= कोई पूर्व ब्लॉक नहीं</p>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert len(blocks) == 1
        assert blocks[0].is_orphan_translation is True
        assert blocks[0].text_devanagari == "कोई पूर्व ब्लॉक नहीं"

    def test_equals_in_middle_not_consumed(self, config):
        # "=" not at start → not a translation marker
        html = """
        <p class="SanskritText">सूत्र 1</p>
        <p class="HindiText">यह = समान है</p>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert len(blocks) == 2
        assert blocks[0].hindi_translation is None
        assert blocks[1].kind == "hindi_text"

    def test_multiple_pairs(self, config):
        html = """
        <p class="SanskritText">सूत्र 1</p>
        <p class="HindiText">= अनुवाद 1</p>
        <p class="SanskritText">सूत्र 2</p>
        <p class="HindiText">= अनुवाद 2</p>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert len(blocks) == 2
        assert blocks[0].hindi_translation == "अनुवाद 1"
        assert blocks[1].hindi_translation == "अनुवाद 2"

    def test_translation_strips_leading_equals(self, config):
        html = """
        <p class="SanskritText">सूत्र</p>
        <p class="HindiText">=   अनुवाद</p>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert len(blocks) == 1
        assert blocks[0].hindi_translation == "अनुवाद"
        assert not blocks[0].hindi_translation.startswith("=")

    def test_sibling_eq_translation_marker(self, config):
        html = """
        <li>
          <span class="GRef">पंचास्तिकाय/9</span>
          <span class="PrakritGatha">दवियदि गच्छदि ।9।</span>
          =
          <span class="HindiText">उन-उन सद्भाव पर्यायों को ।</span>
        </li>
        """
        blocks = parse_li_to_blocks(html, config)
        src = next(b for b in blocks if b.kind == "prakrit_gatha")
        assert src.text_devanagari.startswith("दवियदि")
        assert src.hindi_translation is not None
        assert src.hindi_translation.startswith("उन-उन")
        assert not any(b.kind == "hindi_text" for b in blocks)

    def test_sibling_eq_with_inline_gref_in_translation(self, config):
        html = """
        <li>
          <span class="GRef">पंचास्तिकाय/9</span>
          <span class="PrakritGatha">दवियदि गच्छदि ।9।</span>
          =
          <span class="HindiText">उन-उन सद्भाव ।
            <span class="GRef">( राजवार्तिक/1/33/1/95/4 )</span>।
          </span>
        </li>
        """
        blocks = parse_li_to_blocks(html, config)
        src = next(b for b in blocks if b.kind == "prakrit_gatha")
        assert [r.text for r in src.references] == [
            "पंचास्तिकाय/9",
            "( राजवार्तिक/1/33/1/95/4 )",
        ]
        assert "राजवार्तिक" not in src.hindi_translation

    def test_eq_inside_hindi_text_still_works(self, config):
        html = '<p class="HindiText">= द्रव्य का लक्षण।</p>'
        block = parse_p_to_block_with_prev_source(html, config)
        assert block.hindi_translation is not None
