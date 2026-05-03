"""Unit tests for heading variant detection (V1–V4)."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_subsections import detect_heading


@pytest.fixture
def config():
    return load_config()


def parse_first(html: str, selector: str):
    tree = HTMLParser(html)
    return tree.css_first(selector)


class TestV1:
    """<strong id="N">heading</strong>"""

    def test_detects_v1(self, config):
        node = parse_first('<strong id="1.1">निरुक्ति अर्थ</strong>', "strong")
        result = detect_heading(node, config)
        assert result is not None
        variant, path, text = result
        assert variant == "V1"
        assert path == "1.1"
        assert text == "निरुक्ति अर्थ"

    def test_v1_no_id_not_detected(self, config):
        node = parse_first("<strong>some text</strong>", "strong")
        assert detect_heading(node, config) is None

    def test_v1_empty_text_not_detected(self, config):
        node = parse_first('<strong id="1.1"></strong>', "strong")
        assert detect_heading(node, config) is None


class TestV2:
    """<span class="HindiText" id="N"><strong>heading</strong></span>"""

    def test_detects_v2(self, config):
        html = '<span class="HindiText" id="2">भेद व लक्षण<strong>भेद व लक्षण</strong></span>'
        node = parse_first(html, "span.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        variant, path, text = result
        assert variant == "V2"
        assert path == "2"
        assert "भेद" in text

    def test_v2_no_id_not_detected(self, config):
        html = '<span class="HindiText"><strong>text</strong></span>'
        node = parse_first(html, "span.HindiText")
        assert detect_heading(node, config) is None

    def test_v2_no_strong_not_detected(self, config):
        html = '<span class="HindiText" id="2">text only</span>'
        node = parse_first(html, "span")
        assert detect_heading(node, config) is None


class TestV3:
    """<li id="N"><span class="HindiText"><strong>heading</strong></span>"""

    def test_detects_v3(self, config):
        html = '<li id="1"><span class="HindiText"><strong>भेद व लक्षण</strong></span></li>'
        node = parse_first(html, "li")
        result = detect_heading(node, config)
        assert result is not None
        variant, path, text = result
        assert variant == "V3"
        assert path == "1"
        assert "भेद" in text

    def test_v3_no_id_not_detected(self, config):
        html = '<li><span class="HindiText"><strong>text</strong></span></li>'
        node = parse_first(html, "li")
        assert detect_heading(node, config) is None

    def test_v3_footer_id_excluded(self, config):
        html = '<li id="footer-1"><span class="HindiText"><strong>text</strong></span></li>'
        node = parse_first(html, "li")
        assert detect_heading(node, config) is None

    def test_v3_nested_path(self, config):
        html = '<li id="1.1.2"><span class="HindiText"><strong>sub heading</strong></span></li>'
        node = parse_first(html, "li")
        result = detect_heading(node, config)
        assert result is not None
        _, path, _ = result
        assert path == "1.1.2"


class TestV4:
    """<p class="HindiText"><b>N. heading</b></p>"""

    def test_detects_v4(self, config):
        html = '<p class="HindiText"><b>2. आत्मा के बहिरात्मादि 3 भेद</b></p>'
        node = parse_first(html, "p.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        variant, path, text = result
        assert variant == "V4"
        assert path == "2"
        assert "आत्मा" in text

    def test_v4_dotted_path(self, config):
        html = '<p class="HindiText"><b>1.2. उपभेद</b></p>'
        node = parse_first(html, "p.HindiText")
        result = detect_heading(node, config)
        assert result is not None
        _, path, _ = result
        assert path == "1.2"

    def test_v4_multiple_b_children_not_detected(self, config):
        # More than one element child → not V4
        html = '<p class="HindiText"><b>2. heading</b><b>extra</b></p>'
        node = parse_first(html, "p.HindiText")
        assert detect_heading(node, config) is None

    def test_v4_wrong_class_not_detected(self, config):
        html = '<p class="SanskritText"><b>2. heading</b></p>'
        node = parse_first(html, "p")
        assert detect_heading(node, config) is None

    def test_v4_no_numeric_prefix_not_detected(self, config):
        # "text" without "N. " prefix doesn't match V4 regex
        html = '<p class="HindiText"><b>heading without number</b></p>'
        node = parse_first(html, "p.HindiText")
        assert detect_heading(node, config) is None


class TestV5NotAHeading:
    """V5 is the puraankosh definition pattern — must NOT be detected as a heading."""

    def test_p_with_id_not_heading(self, config):
        html = '<p id="1" class="HindiText">(1) some definition text</p>'
        node = parse_first(html, "p")
        assert detect_heading(node, config) is None


def test_v2_heading_inline_content_is_captured():
    """Topic 4.1.1 is a V2 heading whose body content lives inside the heading span.
    After the fix it must have non-empty blocks."""
    from pathlib import Path
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    fixture = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"
    html = fixture.read_text(encoding="utf-8")
    cfg = load_config()
    res = parse_keyword_html(html, "https://example.org/wiki/द्रव्य", cfg)

    section = res.page_sections[0]

    def find_by_path(subs, path):
        for s in subs:
            if s.topic_path == path:
                return s
            found = find_by_path(s.children, path)
            if found:
                return found
        return None

    sub_411 = find_by_path(section.subsections, "4.1.1")
    assert sub_411 is not None, "topic 4.1.1 not found"
    assert len(sub_411.blocks) > 0, "4.1.1 must have blocks"
    assert sub_411.blocks[0].kind == "hindi_text"
    assert "ब्रह्माद्वैत" in (sub_411.blocks[0].text_devanagari or "")
