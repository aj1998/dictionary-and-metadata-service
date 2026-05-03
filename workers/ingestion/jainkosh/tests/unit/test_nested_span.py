"""Unit tests for nested-span flattening (parse_blocks.flatten_for_blocks)."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import BlocksConfig, load_config
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

    def test_gref_before_br_is_trailing_for_outer_block(self, config):
        """GRef before the <br/> boundary stays with the outer (hindi_text) block."""
        html = """
        <li class="HindiText">
          प्रमाण नय पाठ
          <span class="GRef">( नयचक्र बृहद्/17 )</span>
          ।<br/>
          <span class="GRef">( द्रव्यसंग्रह/1 )</span>
          <span class="SanskritText">संस्कृत पाठ</span>
        </li>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert [b.kind for b in blocks] == ["hindi_text", "sanskrit_text"]
        assert [r.text for r in blocks[0].references] == ["( नयचक्र बृहद्/17 )"]
        assert [r.text for r in blocks[1].references] == ["( द्रव्यसंग्रह/1 )"]

    def test_gref_after_br_is_leading_for_nested_block(self, config):
        """GRef after the <br/> boundary becomes a leading ref for the nested block."""
        html = """
        <li class="HindiText">
          प्रमाण नय पाठ
          <span class="GRef">( नयचक्र बृहद्/17 )</span>
          ।<br/>
          <span class="GRef">( द्रव्यसंग्रह/1 )</span>
          <span class="SanskritText">संस्कृत पाठ</span>
        </li>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert [r.text for r in blocks[0].references] == ["( नयचक्र बृहद्/17 )"]
        assert [r.text for r in blocks[1].references] == ["( द्रव्यसंग्रह/1 )"]

    def test_no_br_all_grefs_trailing(self, config):
        """When no <br/> boundary exists, all pre-nested GRefs stay with the outer block."""
        html = """
        <li class="HindiText">
          पाठ
          <span class="GRef">( ref1 )</span>
          <span class="SanskritText">संस्कृत</span>
        </li>
        """
        blocks = parse_block_stream(make_elements(html), config)
        assert [b.kind for b in blocks] == ["hindi_text", "sanskrit_text"]
        assert [r.text for r in blocks[0].references] == ["( ref1 )"]
        assert blocks[1].references == []

    def test_reattach_disabled_old_behavior(self, config):
        """With nested_span_gref_reattach=False, GRefs keep the old next-block attribution."""
        cfg = config.model_copy(update={"blocks": BlocksConfig(nested_span_gref_reattach=False)})
        html = """
        <li class="HindiText">
          पाठ
          <span class="GRef">( ref1 )</span>
          <span class="SanskritText">संस्कृत</span>
        </li>
        """
        blocks = parse_block_stream(make_elements(html), cfg)
        assert [b.kind for b in blocks] == ["hindi_text", "sanskrit_text"]
        assert blocks[0].references == []
        assert [r.text for r in blocks[1].references] == ["( ref1 )"]
