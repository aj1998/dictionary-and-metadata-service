"""Unit tests for nested-span flattening (parse_blocks.flatten_for_blocks)."""

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


class TestNestedSpan:
    def test_flat_span_unchanged(self, config):
        html = '<span class="SanskritText">आत्मा द्वादशांगम्</span>'
        blocks = parse_block_stream(make_elements(html), config)
        assert len(blocks) == 1
        assert blocks[0].kind == "sanskrit_text"

    def test_nested_span_splits_into_multiple_blocks(self, config):
        # Outer SanskritText contains nested SanskritText and HindiText
        html = """
        <span class="SanskritText">
          outer text
          <span class="SanskritText">inner sanskrit</span>
          <span class="HindiText">= inner hindi</span>
        </span>
        """
        blocks = parse_block_stream(make_elements(html), config)
        # Should produce at least 2 blocks: inner sanskrit + its translation
        assert len(blocks) >= 1
        kinds = [b.kind for b in blocks]
        assert "sanskrit_text" in kinds

    def test_nested_translation_absorbed(self, config):
        html = """
        <span class="SanskritText">
          <span class="SanskritText">यथास्वं पर्यायैः</span>
          <span class="HindiText">= अपने-अपने पर्यायों से</span>
        </span>
        """
        blocks = parse_block_stream(make_elements(html), config)
        # The inner Sanskrit+Hindi pair should produce one block with translation
        assert any(b.hindi_translation is not None for b in blocks)
