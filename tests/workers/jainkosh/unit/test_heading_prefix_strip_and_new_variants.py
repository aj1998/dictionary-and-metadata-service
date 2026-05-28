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


    # ------------------------------------------------------------------
    # After-dekhen: देखें <link> text_after → child label-seed topic
    # ------------------------------------------------------------------

    def test_1_1_4_has_no_direct_hindi_text_blocks(self, swabhav_result):
        """Section 1.1.4 should have no direct hindi_text blocks — each
        'देखें <link> text_after' element becomes a child seed, not a block."""
        section = swabhav_result.page_sections[0]
        sub114 = self._find_by_path(section.subsections, "1.1.4")
        assert sub114 is not None
        hindi_blocks = [b for b in sub114.blocks if b.kind == "hindi_text"]
        assert hindi_blocks == [], (
            f"Expected no hindi_text blocks in 1.1.4, got: {[b.text_devanagari for b in hindi_blocks]}"
        )

    def test_1_1_4_has_two_after_dekhen_children(self, swabhav_result):
        """Section 1.1.4 must have exactly two after-dekhen child seeds."""
        section = swabhav_result.page_sections[0]
        sub114 = self._find_by_path(section.subsections, "1.1.4")
        assert sub114 is not None
        seeds = [c for c in sub114.children if c.label_topic_seed]
        assert len(seeds) == 2, f"Expected 2 after-dekhen seeds, got {len(seeds)}"

    def test_1_1_4_child_headings_are_after_text(self, swabhav_result):
        """Child seed headings must be the text that followed each देखें link."""
        section = swabhav_result.page_sections[0]
        sub114 = self._find_by_path(section.subsections, "1.1.4")
        assert sub114 is not None
        headings = {c.heading_text for c in sub114.children if c.label_topic_seed}
        assert any("एकार्थवाची" in h for h in headings), (
            f"Expected 'एकार्थवाची' in a child heading; got {headings}"
        )

    def test_1_1_4_child_seeds_have_see_also_blocks(self, swabhav_result):
        """Each after-dekhen child seed must carry a see_also block."""
        section = swabhav_result.page_sections[0]
        sub114 = self._find_by_path(section.subsections, "1.1.4")
        assert sub114 is not None
        seeds = [c for c in sub114.children if c.label_topic_seed]
        for seed in seeds:
            sa = [b for b in seed.blocks if b.kind == "see_also"]
            assert sa, f"Seed '{seed.heading_text[:40]}' has no see_also block"

    def test_1_1_4_first_child_see_also_target(self, swabhav_result):
        """The first seed in 1.1.4 should point to तत्त्व topic 1.1."""
        section = swabhav_result.page_sections[0]
        sub114 = self._find_by_path(section.subsections, "1.1.4")
        assert sub114 is not None
        targets = {
            (b.target_keyword, b.target_topic_path)
            for c in sub114.children if c.label_topic_seed
            for b in c.blocks if b.kind == "see_also"
        }
        assert ("तत्त्व", "1.1") in targets, f"Expected (तत्त्व, 1.1) in targets; got {targets}"

    def test_1_4_has_after_dekhen_child(self, swabhav_result):
        """Section 1.4 must have a child seed for the पारिणामिक after-dekhen element."""
        section = swabhav_result.page_sections[0]
        sub14 = self._find_by_path(section.subsections, "1.4")
        assert sub14 is not None
        seeds = [c for c in sub14.children if c.label_topic_seed]
        assert len(seeds) >= 1, "Expected at least one after-dekhen seed in section 1.4"
        targets = {b.target_keyword for c in seeds for b in c.blocks if b.kind == "see_also"}
        assert "पारिणामिक" in targets, f"Expected पारिणामिक in targets; got {targets}"

    def test_1_4_retains_other_blocks(self, swabhav_result):
        """Section 1.4 must still have its other blocks (sanskrit_text, hindi_text)."""
        section = swabhav_result.page_sections[0]
        sub14 = self._find_by_path(section.subsections, "1.4")
        assert sub14 is not None
        kinds = {b.kind for b in sub14.blocks}
        assert "sanskrit_text" in kinds, "Expected sanskrit_text in 1.4 blocks"

    def test_2_4_has_after_dekhen_child_self_link(self, swabhav_result):
        """Section 2.4 must have a child seed for the self-link after-dekhen element."""
        section = swabhav_result.page_sections[0]
        sub24 = self._find_by_path(section.subsections, "2.4")
        assert sub24 is not None
        seeds = [c for c in sub24.children if c.label_topic_seed]
        assert len(seeds) >= 1, "Expected at least one after-dekhen seed in section 2.4"
        self_links = [b for c in seeds for b in c.blocks if b.kind == "see_also" and b.is_self]
        assert self_links, "Expected a self-link see_also in the 2.4 after-dekhen seed"


class TestAfterDekhenUnit:
    """Unit tests for _is_after_dekhen_element and extract_text_after_anchor."""

    def test_detects_valid_after_dekhen_element(self, config):
        """p.HindiText starting with देखें <link> text should be detected."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_blocks import _is_after_dekhen_element
        html = """<html><body>
        <p class="HindiText">देखें <a href="/wiki/तत्त्व#1.1">तत्त्व - 1.1</a>
        तत्त्व, परमार्थ, द्रव्य, स्वभाव, परमपरम ये सब एकार्थवाची हैं।</p>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("p.HindiText")
        assert _is_after_dekhen_element(el, config) is True

    def test_rejects_element_without_after_text(self, config):
        """p.HindiText with देखें <link> but no trailing text should NOT be detected."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_blocks import _is_after_dekhen_element
        html = """<html><body>
        <p class="HindiText">देखें <a href="/wiki/तत्त्व#1.1">तत्त्व - 1.1</a></p>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("p.HindiText")
        assert _is_after_dekhen_element(el, config) is False

    def test_rejects_mid_prose_dekhen(self, config):
        """p.HindiText with prose before देखें should NOT be detected as after-dekhen."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_blocks import _is_after_dekhen_element
        html = """<html><body>
        <p class="HindiText">जो वस्तु क्रियावान् है, (देखें <a href="/wiki/जीव#3.8">जीव - 3.8</a>
        असर्वगत होने के कारण जीव क्रियावान् है)।</p>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("p.HindiText")
        assert _is_after_dekhen_element(el, config) is False

    def test_rejects_parenthesised_dekhen(self, config):
        """Parenthesised (देखें X) pattern should NOT be detected as after-dekhen."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_blocks import _is_after_dekhen_element
        html = """<html><body>
        <span class="HindiText">प्रमाण है। (देखें <a href="/wiki/सत्">सत् </a>)</span>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("span.HindiText")
        assert _is_after_dekhen_element(el, config) is False

    def test_extract_text_after_anchor(self, config):
        """extract_text_after_anchor should return text after the anchor."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.see_also import extract_text_after_anchor
        html = """<html><body>
        <p class="HindiText">देखें <a href="/wiki/तत्त्व#1.1">तत्त्व - 1.1</a>
        तत्त्व, परमार्थ, द्रव्य, स्वभाव ये सब एकार्थवाची हैं।</p>
        </body></html>"""
        tree = HTMLParser(html)
        a = tree.css_first("a")
        after = extract_text_after_anchor(a)
        assert "एकार्थवाची" in after
        assert "देखें" not in after

    def test_after_dekhen_creates_child_seed(self, config):
        """Minimal integration: after-dekhen element creates a label_topic_seed child."""
        from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
        html = """<html><body><div class="mw-parser-output">
        <h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
        <p class="HindiText"><strong id="1">शीर्षक</strong></p>
        <p class="HindiText">देखें <a href="/wiki/तत्त्व#1.1">तत्त्व - 1.1</a>
        तत्त्व, परमार्थ, द्रव्य, स्वभाव, परमपरम ये सब एकार्थवाची हैं।</p>
        </div></body></html>"""
        result = parse_keyword_html(html, "https://www.jainkosh.org/wiki/test", config)
        section = result.page_sections[0]
        sub1 = next((s for s in section.subsections if s.topic_path == "1"), None)
        assert sub1 is not None
        seeds = [c for c in sub1.children if c.label_topic_seed]
        assert len(seeds) == 1, f"Expected 1 seed, got {len(seeds)}"
        assert "एकार्थवाची" in seeds[0].heading_text
        sa = [b for b in seeds[0].blocks if b.kind == "see_also"]
        assert len(sa) == 1
        assert sa[0].target_keyword == "तत्त्व"
        assert sa[0].target_topic_path == "1.1"


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


# ---------------------------------------------------------------------------
# <br/>-separated देखें → section-level label_topic_seeds (वस्तु case)
# ---------------------------------------------------------------------------

class TestBrDekhenUnit:
    """Unit tests for _is_br_dekhen_element and extract_br_dekhen_seeds_from_elements."""

    def test_detects_br_dekhen_element(self, config):
        """span.HindiText with initial prose + <br/>+देखें lines should be detected."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_blocks import _is_br_dekhen_element
        html = """<html><body>
        <span class="HindiText">प्रारंभिक गद्य है। <br/>
        देखें <a href="/wiki/द्रव्य#1.7">द्रव्य 1.7</a>
        (सत्त, सत्त्व ये एकार्थवाची हैं)। </span>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("span.HindiText")
        assert _is_br_dekhen_element(el, config) is True

    def test_rejects_pure_after_dekhen_element(self, config):
        """p.HindiText starting with देखें should NOT be a br-dekhen element."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_blocks import _is_br_dekhen_element
        html = """<html><body>
        <p class="HindiText">देखें <a href="/wiki/तत्त्व#1.1">तत्त्व - 1.1</a>
        तत्त्व, परमार्थ ये एकार्थवाची हैं।</p>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("p.HindiText")
        assert _is_br_dekhen_element(el, config) is False

    def test_rejects_element_without_br(self, config):
        """Element without <br/> should not be detected as br-dekhen."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_blocks import _is_br_dekhen_element
        html = """<html><body>
        <p class="HindiText">गद्य है। देखें <a href="/wiki/द्रव्य">द्रव्य</a></p>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("p.HindiText")
        assert _is_br_dekhen_element(el, config) is False

    def test_extract_br_dekhen_seeds_strips_parens(self, config):
        """extract_br_dekhen_seeds_from_elements should strip outer parens from after-anchor text."""
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.parse_subsections import extract_br_dekhen_seeds_from_elements
        html = """<html><body>
        <span class="HindiText">प्रारंभिक गद्य। <br/>
        देखें <a href="/wiki/द्रव्य#1.7">द्रव्य 1.7</a>
        - (सत्त, सत्त्व ये एकार्थवाची हैं)। <br/>
        देखें <a href="/wiki/सामान्य">सामान्य</a>
        (वस्तु सामान्य है)।</span>
        </body></html>"""
        tree = HTMLParser(html)
        el = tree.css_first("span.HindiText")
        seeds = extract_br_dekhen_seeds_from_elements([el], keyword="वस्तु", config=config)
        assert len(seeds) == 2
        labels = [s[0] for s in seeds]
        assert any("एकार्थवाची" in label for label in labels)
        assert any("सामान्य" in label for label in labels)
        # Parens should be stripped
        for label in labels:
            assert not label.startswith("("), f"Outer paren not stripped: {label!r}"


class TestVastuBrDekhenIntegration:
    """Integration tests: <br/>-separated देखें in वस्तु becomes section-level label_topic_seeds."""

    @pytest.fixture(scope="class")
    def vastu_result(self, config):
        fixture = (
            Path(__file__).parents[4]
            / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures" / "वस्तु.html"
        )
        html = fixture.read_text(encoding="utf-8")
        return parse_keyword_html(
            html,
            "https://www.jainkosh.org/wiki/%E0%A4%B5%E0%A4%B8%E0%A5%8D%E0%A4%A4%E0%A5%81",
            config,
        )

    def test_section_has_four_label_topic_seeds(self, vastu_result):
        """The siddhantkosh section must have 4 label_topic_seeds for the 4 <br/>-देखें lines."""
        section = vastu_result.page_sections[0]
        seeds = section.label_topic_seeds
        assert len(seeds) == 4, f"Expected 4 seeds, got {len(seeds)}: {[s.heading_text for s in seeds]}"

    def test_seed_headings_match_expected(self, vastu_result):
        """Seed headings must be the cleaned up (paren-stripped) after-anchor texts."""
        section = vastu_result.page_sections[0]
        headings = {s.heading_text for s in section.label_topic_seeds}
        assert any("एकार्थवाची" in h for h in headings), f"Expected एकार्थवाची in a seed; got {headings}"
        assert any("गुणपर्यायात्मक" in h for h in headings), f"Expected गुणपर्यायात्मक in a seed; got {headings}"
        assert any("सामान्य विशेषात्मक" in h for h in headings), f"Expected सामान्य विशेषात्मक in a seed; got {headings}"
        assert any("श्रुतज्ञान" in h for h in headings), f"Expected श्रुतज्ञान in a seed; got {headings}"

    def test_seeds_have_see_also_blocks(self, vastu_result):
        """Each seed must carry exactly one see_also block."""
        section = vastu_result.page_sections[0]
        for seed in section.label_topic_seeds:
            sa = [b for b in seed.blocks if b.kind == "see_also"]
            assert len(sa) == 1, f"Expected 1 see_also in seed '{seed.heading_text[:40]}', got {len(sa)}"

    def test_seed_targets(self, vastu_result):
        """Seeds must point to the correct target keywords."""
        section = vastu_result.page_sections[0]
        targets = {
            (b.target_keyword, b.target_topic_path)
            for seed in section.label_topic_seeds
            for b in seed.blocks if b.kind == "see_also"
        }
        assert ("द्रव्य", "1.7") in targets, f"Expected (द्रव्य, 1.7) in targets; got {targets}"
        assert ("द्रव्य", "1.4") in targets, f"Expected (द्रव्य, 1.4) in targets; got {targets}"
        assert ("सामान्य", None) in targets, f"Expected (सामान्य, None) in targets; got {targets}"
        assert ("श्रुतज्ञान", "II") in targets, f"Expected (श्रुतज्ञान, II) in targets; got {targets}"

    def test_definition_hindi_translation_stripped(self, vastu_result):
        """hindi_translation in the definition block must have देखें lines removed."""
        section = vastu_result.page_sections[0]
        for defn in section.definitions:
            for block in defn.blocks:
                if block.hindi_translation:
                    assert "देखें" not in block.hindi_translation, (
                        f"देखें should be stripped from hindi_translation: {block.hindi_translation[:80]!r}"
                    )

    def test_definition_no_covered_see_also_blocks(self, vastu_result):
        """The 4 see_also blocks that were moved to seeds must not remain in definitions."""
        section = vastu_result.page_sections[0]
        covered_targets = {("द्रव्य", "1.7"), ("द्रव्य", "1.4"), ("सामान्य", None), ("श्रुतज्ञान", "II")}
        for defn in section.definitions:
            for block in defn.blocks:
                if block.kind == "see_also":
                    key = (block.target_keyword, block.target_topic_path)
                    assert key not in covered_targets, (
                        f"see_also block {key} should have been relocated to label_topic_seed"
                    )


# ---------------------------------------------------------------------------
# Golden snapshot for वस्तु
# ---------------------------------------------------------------------------

class TestVastuGolden:
    def test_golden_matches(self, config):
        fixture = (
            Path(__file__).parents[4]
            / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures" / "वस्तु.html"
        )
        golden_path = (
            Path(__file__).parents[4]
            / "workers" / "ingestion" / "jainkosh" / "tests" / "golden" / "वस्तु.json"
        )
        html = fixture.read_text(encoding="utf-8")
        from datetime import datetime
        frozen = datetime(2026, 5, 4, 0, 0, 0)
        result = parse_keyword_html(
            html,
            "https://www.jainkosh.org/wiki/%E0%A4%B5%E0%A4%B8%E0%A5%8D%E0%A4%A4%E0%A5%81",
            config,
            frozen_time=frozen,
        )

        from workers.ingestion.jainkosh.envelope import build_envelope
        envelope = build_envelope(result, config)
        actual = json.loads(envelope.model_dump_json())

        with golden_path.open(encoding="utf-8") as f:
            expected = json.load(f)

        assert actual == expected, "वस्तु golden mismatch — regenerate with cli parse --frozen-time"
