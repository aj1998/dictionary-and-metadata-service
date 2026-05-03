"""Unit tests for see_also.py."""

import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import parse_block_stream
from workers.ingestion.jainkosh.see_also import parse_anchor, find_see_alsos_in_element
from workers.ingestion.jainkosh.models import Block, IndexRelation


CFG = load_config()


@pytest.fixture
def config():
    return load_config()


def parse_node(html: str, selector: str = "body > *"):
    tree = HTMLParser(f"<body>{html}</body>")
    return tree.css_first(selector)

def parse_p_to_blocks(html: str, config):
    tree = HTMLParser(f"<body>{html}</body>")
    p = tree.css_first("p")
    return parse_block_stream([p], config, current_keyword="आत्मा")


class TestParseAnchor:
    def test_wiki_link(self, config):
        node = parse_node('<a href="/wiki/जीव">जीव</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_keyword"] == "जीव"
        assert result["is_self"] is False
        assert result["target_exists"] is True

    def test_wiki_link_with_fragment(self, config):
        node = parse_node('<a href="/wiki/मोक्षमार्ग#2.5">text</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_keyword"] == "मोक्षमार्ग"
        assert result["target_topic_path"] == "2.5"

    def test_self_link(self, config):
        node = parse_node('<a class="mw-selflink-fragment" href="#1.2">text</a>', "a")
        result = parse_anchor(node, config, current_keyword="द्रव्य")
        assert result["is_self"] is True
        assert result["target_topic_path"] == "1.2"

    def test_redlink(self, config):
        node = parse_node('<a href="/w/index.php?title=X&action=edit&redlink=1">X</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_exists"] is False

    def test_underscore_to_space(self, config):
        node = parse_node('<a href="/wiki/वह_वह_नाम">text</a>', "a")
        result = parse_anchor(node, config, current_keyword="आत्मा")
        assert result["target_keyword"] == "वह वह नाम"


class TestFindSeeAlsos:
    def test_simple_see_also_block(self, config):
        html = '<p class="HindiText">• देखें<a href="/wiki/जीव">जीव</a></p>'
        node = parse_node(html, "p")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=False)
        assert len(results) == 1
        item = results[0]
        assert isinstance(item, Block)
        assert item.kind == "see_also"
        assert item.target_keyword == "जीव"

    def test_inline_see_also_with_fragment(self, config):
        html = '<p class="HindiText">पाठ। देखें<a href="/wiki/मोक्षमार्ग#2.5">मोक्षमार्ग - 2.5</a></p>'
        node = parse_node(html, "p")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=False)
        assert len(results) == 1
        assert results[0].target_topic_path == "2.5"

    def test_index_see_also_returns_index_relation(self, config):
        html = '<ul><li>देखें <a href="/wiki/जीव">जीव</a></li></ul>'
        node = parse_node(html, "ul")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=True)
        assert len(results) == 1
        assert isinstance(results[0], IndexRelation)

    def test_no_see_also_returns_empty(self, config):
        # Link without "देखें" pattern should not produce see_also
        html = '<p class="HindiText">यह भी पढ़ें <a href="/wiki/जीव">जीव</a></p>'
        node = parse_node(html, "p")
        results = find_see_alsos_in_element(node, config, current_keyword="आत्मा", as_index_relation=False)
        assert len(results) == 0


@pytest.mark.parametrize("html, expected_trigger_count", [
    ('<p class="HindiText">देखें <a href="/wiki/X">X</a></p>', 1),
    ('<p class="HindiText">विशेष देखें <a href="/wiki/X">X</a></p>', 1),
    (
        '<ol><li><strong id="1">A</strong>'
        '<ol><li><ul><li>परमाणु में कथंचित् सावयव निरवयवपना।।–देखें '
        '<a href="/wiki/परमाणु">परमाणु</a></li></ul></li></ol>'
        '</li></ol>',
        1,
    ),
    (
        '<p class="HindiText">A देखें <a href="/wiki/A">A</a> '
        'और विशेष देखें <a href="/wiki/B">B</a></p>',
        2,
    ),
])
def test_see_also_triggers(html, expected_trigger_count):
    tree = HTMLParser(html)
    root = tree.css_first("p, ol")
    results = find_see_alsos_in_element(root, CFG, current_keyword="X")
    assert len(results) == expected_trigger_count


@pytest.mark.parametrize("html, expected_count", [
    # देखें with no following <a> — no relation
    ('<p class="HindiText">देखें</p>', 0),
    # Two anchors after one देखें — only the first is see_also
    ('<p class="HindiText">देखें <a href="/wiki/X">X</a>, <a href="/wiki/Y">Y</a></p>', 1),
    # Trigger inside anchor text — not a relation
    ('<p class="HindiText">पाठ <a href="/wiki/X">देखें</a></p>', 0),
    # en-dash before देखें, no space — matches
    ('<p class="HindiText">पाठ।–देखें <a href="/wiki/X">X</a></p>', 1),
    # विशेष देखें and देखें in same para — two relations
    (
        '<p class="HindiText">देखें <a href="/wiki/A">A</a> '
        'और विशेष देखें <a href="/wiki/B">B</a></p>',
        2,
    ),
])
def test_see_also_edge_cases(html, expected_count):
    tree = HTMLParser(html)
    root = tree.css_first("p, ol")
    results = find_see_alsos_in_element(root, CFG, current_keyword="X")
    assert len(results) == expected_count


def test_inline_visesh_dekhen_in_hindi_block():
    html = (
        '<p class="HindiText">पर्याय का स्वरूप (विशेष देखें '
        '<a href="/wiki/अस्तिकाय">अस्तिकाय</a>)</p>'
    )
    tree = HTMLParser(html)
    root = tree.css_first("p")
    results = find_see_alsos_in_element(root, CFG, current_keyword="पर्याय")
    see_alsos = [b for b in results if isinstance(b, Block) and b.kind == "see_also"]
    assert len(see_alsos) == 1
    assert see_alsos[0].target_keyword == "अस्तिकाय"


def test_see_also_preserved_when_text_fully_stripped():
    """When block text is entirely a (देखें ...) pattern, the see_also block
    must still be emitted even though there is no prose block."""
    html = '<li class="HindiText">(विशेष देखें <a href="/wiki/आकाश#2">आकाश - 2</a>)</li>'
    tree = HTMLParser(f"<body>{html}</body>")
    node = tree.css_first("li")
    blocks = parse_block_stream([node], CFG, current_keyword="द्रव्य")
    see_also_blocks = [b for b in blocks if b.kind == "see_also"]
    hindi_blocks = [b for b in blocks if b.kind == "hindi_text"]
    assert len(see_also_blocks) == 1, f"Expected 1 see_also block, got: {blocks}"
    assert see_also_blocks[0].target_keyword == "आकाश"
    assert see_also_blocks[0].target_topic_path == "2"
    assert len(hindi_blocks) == 0, "No hindi_text block should be emitted"


def test_see_also_not_preserved_when_flag_disabled():
    """With preserve_see_alsos_on_empty_text=False, the see_also is silently dropped."""
    import copy
    from workers.ingestion.jainkosh.config import BlocksConfig
    config = load_config()
    config = config.model_copy(update={"blocks": BlocksConfig(preserve_see_alsos_on_empty_text=False)})
    html = '<li class="HindiText">(विशेष देखें <a href="/wiki/आकाश#2">आकाश - 2</a>)</li>'
    tree = HTMLParser(f"<body>{html}</body>")
    node = tree.css_first("li")
    blocks = parse_block_stream([node], config, current_keyword="द्रव्य")
    assert blocks == [], f"Expected empty blocks, got: {blocks}"


def test_redlink_row_fully_dropped_from_block_stream():
    """Row-style redlink entry (• label - देखें target) is fully suppressed in parent block stream.

    The see_also block is instead placed in the corresponding child label-seed subsection
    (see test_label_seed_relation_assignment.py for coverage of that path).
    """
    html = ('<p class="HindiText">•\tबहिरात्मा, अंतरात्मा व परमात्मा - देखें '
            '<a href="/w/index.php?title=%E0%A4%B5%E0%A4%B9_%E0%A4%B5%E0%A4%B9_%E0%A4%A8%E0%A4%BE%E0%A4%AE&amp;action=edit&amp;redlink=1" '
            'class="new" title="वह वह नाम (page does not exist)">वह वह नाम</a></p>')
    blocks = parse_p_to_blocks(html, CFG)

    # Row-style element: NEITHER hindi_text NOR see_also should appear in parent block stream
    assert blocks == [], f"Expected empty blocks for row-style redlink entry, got: {blocks}"
