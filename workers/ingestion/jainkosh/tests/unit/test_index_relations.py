"""Unit tests for parse_index.py (IndexRelation parsing)."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_index import parse_index_relations


@pytest.fixture
def config():
    return load_config()


def make_ols(html: str):
    tree = HTMLParser(f"<body>{html}</body>")
    return tree.css("ol")


class TestIndexRelations:
    def test_parses_section_level_see_also_ul(self, config):
        # Keyword-level <ul> is a direct child of outer <ol>
        html = """
        <ol>
          <ul>
            <li>देखें <a href="/wiki/द्रव्य">द्रव्य</a></li>
          </ul>
        </ol>
        """
        ols = make_ols(html)
        relations = parse_index_relations(ols, "आत्मा", config)
        assert len(relations) == 1
        assert relations[0].target_keyword == "द्रव्य"
        assert relations[0].source_topic_path is None

    def test_parses_li_level_see_also(self, config):
        html = """
        <ol>
          <li id="1">
            <span class="HindiText"><strong>heading</strong></span>
            <ul>
              <li>देखें <a href="/wiki/गुण">गुण</a></li>
            </ul>
          </li>
        </ol>
        """
        ols = make_ols(html)
        relations = parse_index_relations(ols, "द्रव्य", config)
        assert len(relations) == 1
        assert relations[0].target_keyword == "गुण"
        assert relations[0].source_topic_path == "1"

    def test_parses_redlink(self, config):
        html = """
        <ol>
          <ul>
            <li>देखें <a href="/w/index.php?title=X&action=edit&redlink=1">X</a></li>
          </ul>
        </ol>
        """
        ols = make_ols(html)
        relations = parse_index_relations(ols, "आत्मा", config)
        assert len(relations) == 1
        assert relations[0].target_exists is False

    def test_parses_fragment_link(self, config):
        html = """
        <ol>
          <li id="1">
            <span class="HindiText"><strong>heading</strong></span>
            <ul>
              <li>देखें <a href="/wiki/मोक्षमार्ग#2.5">text</a></li>
            </ul>
          </li>
        </ol>
        """
        ols = make_ols(html)
        relations = parse_index_relations(ols, "द्रव्य", config)
        assert len(relations) == 1
        assert relations[0].target_keyword == "मोक्षमार्ग"
        assert relations[0].target_topic_path == "2.5"
