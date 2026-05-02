"""Unit tests for parse_index.py (IndexRelation parsing)."""

import pytest
from pathlib import Path
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_index import parse_index_relations
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

FIXTURE_DIR = Path("workers/ingestion/jainkosh/tests/fixtures")


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def load_fixture():
    def _load(name):
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")
    return _load


def make_ols(html: str):
    tree = HTMLParser(f"<body>{html}</body>")
    return tree.css("body > ol")


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

    def test_parses_deeply_nested_ul(self, config):
        """देखें inside a <ul> nested >2 levels deep must be captured."""
        html = """
        <ol>
          <li id="4">
            <ol>
              <li id="4.2">
                <ol>
                  <li>sub item</li>
                </ol>
              </li>
              <ul>
                <li>परमाणु में कथंचित् सावयव।–देखें <a href="/wiki/परमाणु">परमाणु</a></li>
              </ul>
            </ol>
          </li>
        </ol>
        """
        ols = make_ols(html)
        relations = parse_index_relations(ols, "द्रव्य", config)
        assert len(relations) == 1
        assert relations[0].target_keyword == "परमाणु"

    def test_parses_visesh_dekhen_trigger(self, config):
        """विशेष देखें must be recognized as a trigger."""
        html = """
        <ol>
          <ul>
            <li>पर्याय का स्वरूप विशेष देखें <a href="/wiki/पर्याय">पर्याय</a></li>
          </ul>
        </ol>
        """
        ols = make_ols(html)
        relations = parse_index_relations(ols, "द्रव्य", config)
        assert len(relations) == 1
        assert relations[0].target_keyword == "पर्याय"


def test_index_relations_full_dfs(load_fixture, config):
    """द्रव्य fixture has nested <ul> देखें relations multiple levels deep. All must be captured."""
    html = load_fixture("द्रव्य.html")
    result = parse_keyword_html(html, "https://jainkosh.org/wiki/द्रव्य", config)
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    targets = [r.label_text for r in sk.index_relations]
    assert any("परमाणु में कथंचित् सावयव" in t for t in targets)
    assert any("द्रव्य में कथंचित् नित्यानियत्व" in t for t in targets)


def test_index_relation_chain_for_nested_relation(config):
    html = """
    <ol>
      <li id="1">
        <span class="HindiText"><strong>heading</strong></span>
        <ul>
          <li>पंचास्तिकाय।–देखें <a href="/wiki/अस्तिकाय">अस्तिकाय</a></li>
        </ul>
      </li>
    </ol>
    """
    rel = parse_index_relations(make_ols(html), "द्रव्य", config)[0]
    assert rel.source_topic_path_chain == ["1"]
    assert rel.source_topic_natural_key_chain == []
    assert rel.source_topic_path == "1"


def test_index_relation_chain_for_keyword_level_ul(load_fixture, config):
    result = parse_keyword_html(load_fixture("पर्याय.html"), "https://jainkosh.org/wiki/पर्याय", config)
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    keyword_level = [r for r in sk.index_relations if r.source_topic_path_chain == []]
    assert len(keyword_level) >= 1
    assert all(r.source_topic_natural_key_chain == [] for r in keyword_level)


def test_index_relation_chain_for_deeply_nested_dekhen(config):
    html = """
    <ol>
      <li id="1">
        <ol>
          <li id="1.4">
            <ul>
              <li>इसी प्रकार देखें <a href="/wiki/गुणसमुदायो">गुणसमुदायो</a></li>
            </ul>
          </li>
        </ol>
      </li>
    </ol>
    """
    rel = parse_index_relations(make_ols(html), "द्रव्य", config)[0]
    assert rel.source_topic_path_chain == ["1", "1.4"]
