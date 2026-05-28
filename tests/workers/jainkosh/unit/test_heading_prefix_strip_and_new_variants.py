"""Tests for:
  - Numeric prefix stripping from V1 and V2 heading texts (Bug 1).
  - V2 fallback: span.HindiText[id] without inner <strong> (Bug 2).
  - New V5 variant: p.HindiText[id] with plain text and numeric prefix (Bug 2).
  - DFS now recurses into classless <p> containers that hold heading descendants.
  - Full स्वभाव page integration test (golden sanity).
"""

import json
from pathlib import Path

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.parse_subsections import detect_heading


@pytest.fixture(scope="module")
def config():
    return load_config()


def parse_node(html: str, selector: str, config=None):
    tree = HTMLParser(html)
    return tree.css_first(selector)


# ---------------------------------------------------------------------------
# V1 numeric prefix stripping
# ---------------------------------------------------------------------------

class TestV1NumericPrefixStrip:
    def test_v1_strips_simple_prefix(self, config):
        node = parse_node('<strong id="1.1">1. स्वभाव सामान्य का लक्षण</strong>', "strong")
        result = detect_heading(node, config)
        assert result is not None
        _, path, text = result
        assert path == "1.1"
        assert text == "स्वभाव सामान्य का लक्षण"

    def test_v1_strips_dotted_prefix(self, config):
        node = parse_node('<strong id="1.2.3">1.2.3. उपभेद</strong>', "strong")
        result = detect_heading(node, config)
        assert result is not None
        _, path, text = result
        assert path == "1.2.3"
        assert text == "उपभेद"

    def test_v1_no_prefix_unchanged(self, config):
        node = parse_node('<strong id="1">द्रव्य का निरुक्त्यर्थ</strong>', "strong")
        result = detect_heading(node, config)
        assert result is not None
        _, path, text = result
        assert text == "द्रव्य का निरुक्त्यर्थ"

    def test_v1_only_prefix_not_detected(self, config):
        """If stripping the prefix leaves empty text, reject the heading."""
        node = parse_node('<strong id="1.1">1. </strong>', "strong")
        result = detect_heading(node, config)
        assert result is None


# ---------------------------------------------------------------------------
# V2 numeric prefix stripping (with strong)
# ---------------------------------------------------------------------------

class TestV2NumericPrefixStripWithStrong:
    def test_v2_strips_prefix_in_strong(self, config):
        html = '<span class="HindiText" id="2.1"><strong>2. उपभेद</strong></span>'
        node = parse_node(html, "span.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        _, path, text = result
        assert path == "2.1"
        assert text == "उपभेद"

    def test_v2_no_prefix_in_strong_unchanged(self, config):
        html = '<span class="HindiText" id="2"><strong>भेद व लक्षण</strong></span>'
        node = parse_node(html, "span.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        _, _, text = result
        assert text == "भेद व लक्षण"


# ---------------------------------------------------------------------------
# V2 fallback: span.HindiText[id] without inner <strong>
# ---------------------------------------------------------------------------

class TestV2NoStrongFallback:
    def test_v2_no_strong_with_numeric_prefix_detected(self, config):
        html = '<span class="HindiText" id="1.1.2">2. स्वभाव का लक्षण अंतरंग भाव</span>'
        node = parse_node(html, "span.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        variant, path, text = result
        assert variant == "V2"
        assert path == "1.1.2"
        assert text == "स्वभाव का लक्षण अंतरंग भाव"

    def test_v2_no_strong_without_numeric_prefix_not_detected(self, config):
        """Plain text with no numeric prefix must not be promoted to a heading."""
        html = '<span class="HindiText" id="2">text only</span>'
        node = parse_node(html, "span")
        result = detect_heading(node, config)
        assert result is None

    def test_v2_no_strong_with_child_elements_not_detected(self, config):
        """If the no-strong span has child elements, we don't promote it."""
        html = '<span class="HindiText" id="2">2. heading <span class="GRef">ref</span></span>'
        node = parse_node(html, "span.HindiText")
        result = detect_heading(node, config)
        assert result is None


# ---------------------------------------------------------------------------
# V5 variant: p.HindiText[id] without child elements, with numeric prefix
# ---------------------------------------------------------------------------

class TestV5Variant:
    def test_v5_detected(self, config):
        html = '<p class="HindiText" id="1.1.1">1. स्वभाव का निरुक्ति अर्थ</p>'
        node = parse_node(html, "p.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        variant, path, text = result
        assert variant == "V5"
        assert path == "1.1.1"
        assert text == "स्वभाव का निरुक्ति अर्थ"

    def test_v5_strips_numeric_prefix(self, config):
        html = '<p class="HindiText" id="2.3">3. उपभेद शीर्षक</p>'
        node = parse_node(html, "p.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        _, path, text = result
        assert path == "2.3"
        assert text == "उपभेद शीर्षक"

    def test_v5_no_numeric_prefix_not_detected(self, config):
        """p.HindiText[id] without numeric prefix must not be a heading."""
        html = '<p class="HindiText" id="1.1.1">plain text heading</p>'
        node = parse_node(html, "p.HindiText")
        result = detect_heading(node, config)
        assert result is None

    def test_v5_with_child_elements_not_detected(self, config):
        """p.HindiText[id] that has child elements is not a V5 heading."""
        html = '<p class="HindiText" id="1.1.1"><b>1. heading</b></p>'
        node = parse_node(html, "p.HindiText")
        result = detect_heading(node, config)
        # V4 would match this (b is only child), not V5
        assert result is not None
        variant, _, _ = result
        assert variant == "V4"

    def test_puraankosh_definition_not_detected_as_v5(self, config):
        """PuranKosh definition <p id="1" class="HindiText">(1) text</p> must NOT be V5."""
        html = '<p id="1" class="HindiText">(1) some definition text</p>'
        node = parse_node(html, "p")
        result = detect_heading(node, config)
        assert result is None


# ---------------------------------------------------------------------------
# DFS: classless <p> containing a heading span must be recursed into
# ---------------------------------------------------------------------------

class TestDFSClasslessPContainer:
    def test_heading_inside_classless_p_is_found(self, config):
        html = """<html><body><div class="mw-parser-output">
<h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
<strong id="1">शीर्षक एक</strong>
<p>
  <span class="HindiText" id="1.1">1. उपशीर्षक</span>
</p>
<p class="HindiText">= कोई अनुवाद।</p>
</div></body></html>"""
        result = parse_keyword_html(html, "https://www.jainkosh.org/wiki/test", config)
        section = result.page_sections[0]
        sub1 = next((s for s in section.subsections if s.topic_path == "1"), None)
        assert sub1 is not None
        child11 = next((c for c in sub1.children if c.topic_path == "1.1"), None)
        assert child11 is not None, "1.1 should be detected despite being inside classless <p>"
        assert child11.heading_text == "उपशीर्षक"

    def test_v2_bare_inside_classless_p_no_heading_text_in_blocks(self, config):
        """V2-bare heading inside classless <p> must NOT produce a content block with
        the heading text (regression for _make_v2_content_block erroneously emitting
        the heading text as a hindi_text block for spans without inner <strong>)."""
        html = """<html><body><div class="mw-parser-output">
<h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
<strong id="1">शीर्षक एक</strong>
<p>
  <span class="HindiText" id="1.1">1. उपशीर्षक</span>
</p>
<p class="SanskritText">सूत्रम्।</p>
<p class="HindiText">= अनुवाद।</p>
</div></body></html>"""
        result = parse_keyword_html(html, "https://www.jainkosh.org/wiki/test", config)
        section = result.page_sections[0]

        def _find(subs, path):
            for s in subs:
                if s.topic_path == path:
                    return s
                found = _find(s.children, path)
                if found:
                    return found
            return None

        child11 = _find(section.subsections, "1.1")
        assert child11 is not None
        block_texts = [b.text_devanagari or "" for b in child11.blocks]
        assert not any("उपशीर्षक" in bt for bt in block_texts), (
            f"Heading text leaked into blocks of 1.1: {block_texts}"
        )
        assert not any("1. उपशीर्षक" in bt for bt in block_texts), (
            f"Heading text with numeric prefix leaked into blocks of 1.1: {block_texts}"
        )


# ---------------------------------------------------------------------------
# Integration: स्वभाव page structure
# ---------------------------------------------------------------------------

class TestSwabhavIntegration:
    @pytest.fixture(scope="class")
    def swabhav_result(self, config):
        fixture = (
            Path(__file__).parents[4]
            / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures" / "स्वभाव.html"
        )
        html = fixture.read_text(encoding="utf-8")
        return parse_keyword_html(
            html,
            "https://www.jainkosh.org/wiki/%E0%A4%B8%E0%A5%8D%E0%A4%B5%E0%A4%AD%E0%A4%BE%E0%A4%B5",
            config,
        )

    def _find_by_path(self, subsections, path):
        for s in subsections:
            if s.topic_path == path:
                return s
            found = self._find_by_path(s.children, path)
            if found:
                return found
        return None

    def test_section_1_1_has_no_numeric_prefix(self, swabhav_result):
        section = swabhav_result.page_sections[0]
        sub11 = self._find_by_path(section.subsections, "1.1")
        assert sub11 is not None
        assert sub11.heading_text == "स्वभाव सामान्य का लक्षण"

    def test_section_1_1_has_four_children(self, swabhav_result):
        section = swabhav_result.page_sections[0]
        sub11 = self._find_by_path(section.subsections, "1.1")
        assert sub11 is not None
        child_paths = {c.topic_path for c in sub11.children}
        assert child_paths == {"1.1.1", "1.1.2", "1.1.3", "1.1.4"}

    def test_section_1_1_1_is_v5_heading(self, swabhav_result):
        section = swabhav_result.page_sections[0]
        sub111 = self._find_by_path(section.subsections, "1.1.1")
        assert sub111 is not None
        assert sub111.heading_text == "स्वभाव का निरुक्ति अर्थ"

    def test_section_1_1_2_is_v2_no_strong_heading(self, swabhav_result):
        section = swabhav_result.page_sections[0]
        sub112 = self._find_by_path(section.subsections, "1.1.2")
        assert sub112 is not None
        assert sub112.heading_text == "स्वभाव का लक्षण अंतरंग भाव"

    def test_no_numeric_prefix_in_any_v1_child_headings(self, swabhav_result):
        section = swabhav_result.page_sections[0]
        import re
        prefix_re = re.compile(r'^\d+\.')
        def check_no_prefix(subs):
            for s in subs:
                assert not prefix_re.match(s.heading_text), \
                    f"heading_text {s.heading_text!r} starts with numeric prefix"
                check_no_prefix(s.children)
        check_no_prefix(section.subsections)

    def test_1_1_1_not_in_blocks_of_1_1(self, swabhav_result):
        """The text '1. स्वभाव का निरुक्ति अर्थ' must not appear as a block in 1.1."""
        section = swabhav_result.page_sections[0]
        sub11 = self._find_by_path(section.subsections, "1.1")
        assert sub11 is not None
        block_texts = [b.text_devanagari or "" for b in sub11.blocks]
        for bt in block_texts:
            assert "स्वभाव का निरुक्ति अर्थ" not in bt, \
                f"Heading text leaked into blocks: {bt!r}"

    @pytest.mark.parametrize("path,heading_text", [
        ("1.1.2", "स्वभाव का लक्षण अंतरंग भाव"),
        ("1.1.3", "स्वभाव का लक्षण गुण पर्यायों में अन्वय परिणाम"),
        ("1.1.4", "स्वभाव व शक्ति के एकार्थवाची नाम"),
    ])
    def test_v2_bare_heading_text_not_in_own_blocks(self, swabhav_result, path, heading_text):
        """V2-bare heading text must not appear as a content block inside its own subsection
        (regression: _make_v2_content_block was emitting the heading text as hindi_text)."""
        section = swabhav_result.page_sections[0]
        sub = self._find_by_path(section.subsections, path)
        assert sub is not None, f"Subsection {path} not found"
        block_texts = [b.text_devanagari or "" for b in sub.blocks]
        for bt in block_texts:
            assert heading_text not in bt, (
                f"Heading text for {path} leaked into own blocks: {bt!r}"
            )


# ---------------------------------------------------------------------------
# Golden snapshot for स्वभाव
# ---------------------------------------------------------------------------

class TestSwabhavGolden:
    def test_golden_matches(self, config):
        fixture = (
            Path(__file__).parents[4]
            / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures" / "स्वभाव.html"
        )
        golden_path = (
            Path(__file__).parents[4]
            / "workers" / "ingestion" / "jainkosh" / "tests" / "golden" / "स्वभाव.json"
        )
        html = fixture.read_text(encoding="utf-8")
        from datetime import datetime, timezone
        frozen = datetime(2026, 5, 4, 0, 0, 0)
        result = parse_keyword_html(html,
            "https://www.jainkosh.org/wiki/%E0%A4%B8%E0%A5%8D%E0%A4%B5%E0%A4%AD%E0%A4%BE%E0%A4%B5",
            config, frozen_time=frozen)

        from workers.ingestion.jainkosh.envelope import build_envelope
        envelope = build_envelope(result, config)
        actual = json.loads(envelope.model_dump_json())

        with golden_path.open(encoding="utf-8") as f:
            expected = json.load(f)

        assert actual == expected, "स्वभाव golden mismatch — regenerate with cli parse --frozen-time"
