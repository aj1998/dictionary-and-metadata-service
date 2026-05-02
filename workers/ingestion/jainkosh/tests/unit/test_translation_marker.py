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
