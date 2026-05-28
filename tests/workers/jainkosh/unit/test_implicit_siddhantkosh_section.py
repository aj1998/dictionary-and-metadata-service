"""Unit tests for pages with no <h2> sections.

When a page has content directly in div.mw-parser-output with no h2 headers,
the parser should treat the whole content as a single implicit siddhantkosh section.
"""

import pytest

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

URL = "https://www.jainkosh.org/wiki/%E0%A4%B8%E0%A5%8D%E0%A4%B5%E0%A4%AD%E0%A4%BE%E0%A4%B5"

MINIMAL_PAGE_NO_H2 = """<!DOCTYPE html>
<html><body>
<div class="mw-parser-output">
<p class="HindiText">वस्तु के स्वयंसिद्ध अंश का नाम स्वभाव है।</p>
<strong id="1">स्वभाव के भेद</strong>
<p class="HindiText">= भेद का विवरण।</p>
</div>
</body></html>"""

EMPTY_PARSER_OUTPUT = """<!DOCTYPE html>
<html><body>
<div class="mw-parser-output"></div>
</body></html>"""

WITH_H2_UNAFFECTED = """<!DOCTYPE html>
<html><body>
<div class="mw-parser-output">
<h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
<p class="HindiText">= कोई परिभाषा।</p>
</div>
</body></html>"""


@pytest.fixture
def config():
    return load_config()


class TestImplicitSiddhantkoshSection:
    def test_no_h2_produces_one_section(self, config):
        result = parse_keyword_html(MINIMAL_PAGE_NO_H2, URL, config)
        assert len(result.page_sections) == 1

    def test_implicit_section_is_siddhantkosh(self, config):
        result = parse_keyword_html(MINIMAL_PAGE_NO_H2, URL, config)
        section = result.page_sections[0]
        assert section.section_kind == "siddhantkosh"

    def test_implicit_section_h2_text(self, config):
        result = parse_keyword_html(MINIMAL_PAGE_NO_H2, URL, config)
        section = result.page_sections[0]
        assert section.h2_text == "सिद्धांतकोष से"

    def test_implicit_section_index_is_zero(self, config):
        result = parse_keyword_html(MINIMAL_PAGE_NO_H2, URL, config)
        assert result.page_sections[0].section_index == 0

    def test_implicit_section_parses_subsections(self, config):
        result = parse_keyword_html(MINIMAL_PAGE_NO_H2, URL, config)
        section = result.page_sections[0]
        assert len(section.subsections) >= 1
        assert section.subsections[0].topic_path == "1"
        assert section.subsections[0].heading_text == "स्वभाव के भेद"

    def test_truly_empty_parser_output_produces_no_sections(self, config):
        result = parse_keyword_html(EMPTY_PARSER_OUTPUT, URL, config)
        assert result.page_sections == []

    def test_page_with_h2_unaffected(self, config):
        result = parse_keyword_html(WITH_H2_UNAFFECTED, URL, config)
        assert len(result.page_sections) == 1
        assert result.page_sections[0].section_kind == "siddhantkosh"
        assert result.page_sections[0].h2_text == "सिद्धांतकोष से"
