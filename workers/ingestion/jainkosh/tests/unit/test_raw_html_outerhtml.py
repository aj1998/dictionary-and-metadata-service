import pytest
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.refs import _clean_raw_html, extract_refs_from_node
from workers.ingestion.jainkosh.tables import extract_table_block


@pytest.fixture
def config():
    return load_config()


def test_table_raw_html_is_full_outerhtml(config):
    html = (
        '<table class="t1">'
        '<tbody><tr><th>A</th><th>B</th></tr>'
        '<tr><td>1</td><td>2</td></tr></tbody>'
        '</table>'
    )
    node = HTMLParser(html).css_first("table")
    block = extract_table_block(node, config)
    assert block.raw_html.startswith("<table")
    assert "</table>" in block.raw_html
    assert "<tr>" in block.raw_html
    assert "<td>1</td>" in block.raw_html
    assert "<td>2</td>" in block.raw_html


def test_raw_html_collapses_runs_of_whitespace(config):
    src = '<span class="GRef">  सर्वार्थसिद्धि/5/2/266/10   </span>'
    out = _clean_raw_html(src, config)
    assert out == '<span class="GRef">सर्वार्थसिद्धि/5/2/266/10</span>'


def test_raw_html_double_space_inside_text_collapsed(config):
    src = '<span class="GRef">( सर्वार्थसिद्धि/5/38/30  पर उद्धृत गाथा)</span>'
    out = _clean_raw_html(src, config)
    assert out == '<span class="GRef">( सर्वार्थसिद्धि/5/38/30 पर उद्धृत गाथा)</span>'


def test_raw_html_attribute_values_preserved(config):
    src = '<a href="/wiki/X" title="X">link</a>'
    out = _clean_raw_html(src, config)
    assert out == '<a href="/wiki/X" title="X">link</a>'


def test_reference_raw_html_is_cleaned_in_extract(config):
    html = '<p><span class="GRef">  abc   </span></p>'
    node = HTMLParser(html).css_first("p")
    refs = extract_refs_from_node(node, config)
    assert refs[0].raw_html == '<span class="GRef">abc</span>'
