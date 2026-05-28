"""Tests for trailing '-N' range expansion on देखें links.

Pattern: देखें <a href="/wiki/गति#1.3">गति - 1.3</a>-6
means the relation covers topic paths 1.3, 1.4, 1.5, 1.6.
"""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_index import parse_index_relations
from workers.ingestion.jainkosh.see_also import (
    find_see_alsos_in_element,
    _extract_range_suffix_after_anchor,
    _expand_parsed_to_range,
)
from workers.ingestion.jainkosh.models import Block, IndexRelation


@pytest.fixture
def config():
    return load_config()


def make_ols(html: str):
    tree = HTMLParser(f"<body>{html}</body>")
    return tree.css("body > ol")


# ---------------------------------------------------------------------------
# Unit: _extract_range_suffix_after_anchor
# ---------------------------------------------------------------------------


class TestExtractRangeSuffix:
    def _anchor(self, html: str) -> "Node":
        tree = HTMLParser(f"<p>{html}</p>")
        return tree.css_first("a")

    def test_hyphen_suffix_detected(self):
        a = self._anchor('<a href="/wiki/गति#1.3">गति - 1.3</a>-6।')
        assert _extract_range_suffix_after_anchor(a) == 6

    def test_en_dash_suffix_detected(self):
        a = self._anchor('<a href="/wiki/गुण#3.9">गुण - 3.9</a>–11।')
        assert _extract_range_suffix_after_anchor(a) == 11

    def test_no_suffix_returns_none(self):
        a = self._anchor('<a href="/wiki/गति#1.3">गति - 1.3</a>।')
        assert _extract_range_suffix_after_anchor(a) is None

    def test_suffix_with_whitespace(self):
        a = self._anchor('<a href="/wiki/X#2.1">X - 2.1</a> - 5')
        assert _extract_range_suffix_after_anchor(a) == 5

    def test_no_fragment_no_suffix(self):
        a = self._anchor('<a href="/wiki/गति">गति</a>-6।')
        # suffix is 6 — expansion will be ignored because target_topic_path is None
        assert _extract_range_suffix_after_anchor(a) == 6


# ---------------------------------------------------------------------------
# Unit: _expand_parsed_to_range
# ---------------------------------------------------------------------------


class TestExpandParsedToRange:
    def base(self, path):
        return {
            "target_keyword": "गति",
            "target_topic_path": path,
            "target_url": f"/wiki/गति#{path}",
            "is_self": False,
            "target_exists": True,
        }

    def test_basic_range(self):
        result = _expand_parsed_to_range(self.base("1.3"), 6)
        paths = [r["target_topic_path"] for r in result]
        assert paths == ["1.3", "1.4", "1.5", "1.6"]

    def test_two_digit_end(self):
        result = _expand_parsed_to_range(self.base("3.9"), 11)
        paths = [r["target_topic_path"] for r in result]
        assert paths == ["3.9", "3.10", "3.11"]

    def test_end_equal_to_start_no_expand(self):
        result = _expand_parsed_to_range(self.base("1.3"), 3)
        assert len(result) == 1
        assert result[0]["target_topic_path"] == "1.3"

    def test_end_less_than_start_no_expand(self):
        result = _expand_parsed_to_range(self.base("1.5"), 3)
        assert len(result) == 1

    def test_no_topic_path_no_expand(self):
        parsed = {"target_keyword": "X", "target_topic_path": None,
                  "target_url": "/wiki/X", "is_self": False, "target_exists": True}
        result = _expand_parsed_to_range(parsed, 5)
        assert result == [parsed]

    def test_other_fields_preserved(self):
        result = _expand_parsed_to_range(self.base("2.1"), 3)
        for r in result:
            assert r["target_keyword"] == "गति"
            assert r["is_self"] is False
            assert r["target_exists"] is True

    def test_single_segment_path(self):
        parsed = {"target_keyword": "X", "target_topic_path": "3",
                  "target_url": "/wiki/X#3", "is_self": False, "target_exists": True}
        result = _expand_parsed_to_range(parsed, 5)
        paths = [r["target_topic_path"] for r in result]
        assert paths == ["3", "4", "5"]


# ---------------------------------------------------------------------------
# Integration: parse_index_relations
# ---------------------------------------------------------------------------


class TestIndexRelationRangeExpansion:
    def test_range_in_index_ul(self, config):
        html = """
        <ol>
          <ul>
            <li>जीव पुद्गल का स्वभाव-देखें <a href="/wiki/गति#1.3">गति - 1.3</a>-6।</li>
          </ul>
        </ol>
        """
        ols = make_ols(html)
        rels = parse_index_relations(ols, "स्वभाव", config)
        assert len(rels) == 4
        paths = [r.target_topic_path for r in rels]
        assert paths == ["1.3", "1.4", "1.5", "1.6"]
        for r in rels:
            assert r.target_keyword == "गति"

    def test_range_two_digit_end(self, config):
        html = """
        <ol>
          <ul>
            <li>वस्तु में अनंतों धर्म-देखें <a href="/wiki/गुण#3.9">गुण - 3.9</a>-11।</li>
          </ul>
        </ol>
        """
        ols = make_ols(html)
        rels = parse_index_relations(ols, "स्वभाव", config)
        assert len(rels) == 3
        paths = [r.target_topic_path for r in rels]
        assert paths == ["3.9", "3.10", "3.11"]

    def test_no_range_suffix_single_relation(self, config):
        html = """
        <ol>
          <ul>
            <li>देखें <a href="/wiki/गति#1.3">गति - 1.3</a>।</li>
          </ul>
        </ol>
        """
        ols = make_ols(html)
        rels = parse_index_relations(ols, "स्वभाव", config)
        assert len(rels) == 1
        assert rels[0].target_topic_path == "1.3"

    def test_range_preserves_label_and_source_chain(self, config):
        html = """
        <ol>
          <li id="1">
            <span class="HindiText"><strong>heading</strong></span>
            <ul>
              <li>जीव का स्वभाव-देखें <a href="/wiki/गति#1.3">गति - 1.3</a>-5।</li>
            </ul>
          </li>
        </ol>
        """
        ols = make_ols(html)
        rels = parse_index_relations(ols, "स्वभाव", config)
        assert len(rels) == 3
        for r in rels:
            assert "जीव का स्वभाव" in r.label_text
            assert r.source_topic_path_chain == ["1"]

    def test_range_with_no_fragment_no_expand(self, config):
        # No target_topic_path means expansion is skipped despite suffix
        html = """
        <ol>
          <ul>
            <li>देखें <a href="/wiki/गति">गति</a>-6।</li>
          </ul>
        </ol>
        """
        ols = make_ols(html)
        rels = parse_index_relations(ols, "स्वभाव", config)
        assert len(rels) == 1
        assert rels[0].target_topic_path is None


# ---------------------------------------------------------------------------
# Integration: find_see_alsos_in_element (inline देखें blocks)
# ---------------------------------------------------------------------------


class TestInlineSeeAlsoRangeExpansion:
    def _el(self, inner_html: str):
        tree = HTMLParser(f"<p class='HindiText'>{inner_html}</p>")
        return tree.css_first("p")

    def test_inline_range_produces_multiple_blocks(self, config):
        el = self._el(
            'प्रतिपादन-देखें <a href="/wiki/मोक्ष#2.1">मोक्ष - 2.1</a>-4।'
        )
        blocks = find_see_alsos_in_element(el, config, current_keyword="कर्म")
        assert len(blocks) == 4
        paths = [b.target_topic_path for b in blocks]
        assert paths == ["2.1", "2.2", "2.3", "2.4"]
        for b in blocks:
            assert isinstance(b, Block)
            assert b.kind == "see_also"
            assert b.target_keyword == "मोक्ष"

    def test_inline_no_range_single_block(self, config):
        el = self._el('देखें <a href="/wiki/मोक्ष#2.1">मोक्ष - 2.1</a>।')
        blocks = find_see_alsos_in_element(el, config, current_keyword="कर्म")
        assert len(blocks) == 1
        assert blocks[0].target_topic_path == "2.1"

    def test_inline_range_as_index_relation(self, config):
        el = self._el(
            'देखें <a href="/wiki/गुण#1.2">गुण - 1.2</a>-4।'
        )
        results = find_see_alsos_in_element(
            el, config, current_keyword="कर्म",
            source_topic_path="3", as_index_relation=True
        )
        assert len(results) == 3
        for r in results:
            assert isinstance(r, IndexRelation)
            assert r.source_topic_path == "3"
        paths = [r.target_topic_path for r in results]
        assert paths == ["1.2", "1.3", "1.4"]
