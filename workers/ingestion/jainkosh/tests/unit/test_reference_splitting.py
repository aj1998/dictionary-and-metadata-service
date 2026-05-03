"""Tests for reference splitting at inline GRefs."""
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import split_element_at_inline_refs


def _cfg():
    return load_config()


def test_no_split_when_refs_only_trail():
    """If all GRefs come after the prose (no text after any GRef), no split occurs."""
    html = (
        '<p class="HindiText">यह एक वाक्य है।'
        '<span class="GRef">ग्रंथ 1.2</span>'
        '<span class="GRef">ग्रंथ 3.4</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 1, "trailing GRefs must not cause a split"


def test_split_when_text_follows_gref():
    """Prose → GRef → more prose produces two blocks."""
    html = (
        '<p class="HindiText">'
        'यह पहला वाक्य है।'
        '<span class="GRef">हरिवंशपुराण - 1.1</span>'
        'यह दूसरा वाक्य है।'
        '<span class="GRef">महापुराण 3.5</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 2

    from workers.ingestion.jainkosh.refs import extract_refs_from_node
    refs0 = extract_refs_from_node(result[0], cfg)
    refs1 = extract_refs_from_node(result[1], cfg)
    assert len(refs0) == 1
    assert "हरिवंशपुराण" in refs0[0].text
    assert len(refs1) == 1
    assert "महापुराण" in refs1[0].text


def test_split_multiple_trailing_grefs_stay_in_last_block():
    """GRef1 splits; GRef2 and GRef3 both trail the second segment."""
    html = (
        '<p class="HindiText">'
        'पहला।'
        '<span class="GRef">REF_A</span>'
        'दूसरा।'
        '<span class="GRef">REF_B</span>'
        '<span class="GRef">REF_C</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 2
    from workers.ingestion.jainkosh.refs import extract_refs_from_node
    refs1 = extract_refs_from_node(result[1], cfg)
    ref_texts = [r.text for r in refs1]
    assert "REF_B" in ref_texts
    assert "REF_C" in ref_texts


def test_split_disabled_returns_original():
    """When reference_splitting.enabled=false no split occurs."""
    html = (
        '<p class="HindiText">'
        'पहला।<span class="GRef">REF_A</span>दूसरा।<span class="GRef">REF_B</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    cfg.reference_splitting.enabled = False
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 1


def test_split_only_for_applicable_kinds():
    """kind=table or see_also blocks are not split."""
    html = '<p class="SomeUnknownClass">TEXT<span class="GRef">REF</span>MORE</p>'
    tree = HTMLParser(html)
    el = tree.css_first("p.SomeUnknownClass")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 1


def test_puranakosh_block_from_dravya_fixture_splits():
    """
    Integration: the large PuranKosh block in द्रव्य.html that currently produces
    a single hindi_text block must produce two blocks after the fix.
    """
    from pathlib import Path
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    fixture = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"
    html = fixture.read_text(encoding="utf-8")
    cfg = load_config()
    res = parse_keyword_html(html, "https://example.org/wiki/द्रव्य", cfg)

    puraankosh_sec = next(
        (s for s in res.page_sections if s.section_kind == "puraankosh"), None
    )
    assert puraankosh_sec is not None

    hariv_block = None
    mahap_block = None
    for defn in puraankosh_sec.definitions:
        for b in defn.blocks:
            if b.references:
                ref_texts = [r.text for r in b.references]
                if any("हरिवंशपुराण" in t for t in ref_texts):
                    hariv_block = b
                if any("महापुराण" in t for t in ref_texts):
                    mahap_block = b

    assert hariv_block is not None, "block with हरिवंशपुराण not found"
    assert mahap_block is not None, "block with महापुराण not found"
    assert hariv_block is not mahap_block, (
        "हरिवंशपुराण and महापुराण must be in separate blocks"
    )
    assert "महापुराण" not in (hariv_block.text_devanagari or "")
    assert "आठ अनुयोग" not in (mahap_block.text_devanagari or "")
