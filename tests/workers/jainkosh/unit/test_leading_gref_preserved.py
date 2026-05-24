from pathlib import Path

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

FIXTURE = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"


def _result():
    return parse_keyword_html(
        FIXTURE.read_text(encoding="utf-8"),
        "https://example.org/wiki/द्रव्य",
        load_config(),
    )


def _walk_subs(subs):
    for subsection in subs:
        yield subsection
        yield from _walk_subs(subsection.children)


def _find_sub(result, heading):
    for section in result.page_sections:
        for subsection in _walk_subs(section.subsections):
            if subsection.heading_text == heading:
                return subsection
    raise AssertionError(heading)


def test_panchastikaya_leading_ref_attached_to_prakrit_gatha():
    sub = _find_sub(_result(), "द्रव्य का निरुक्त्यर्थ")
    gatha = next(block for block in sub.blocks if block.kind == "prakrit_gatha")
    ref_texts = [ref.text for ref in gatha.references]
    assert any("पंचास्तिकाय/9" in text for text in ref_texts), ref_texts


def test_sarvarthasiddhi_leading_ref_attached_to_sanskrit_text():
    sub = _find_sub(_result(), "द्रव्य का निरुक्त्यर्थ")
    sanskrit_blocks = [block for block in sub.blocks if block.kind == "sanskrit_text"]
    first = next(
        block for block in sanskrit_blocks if "गुणैर्गुणान्वा" in (block.text_devanagari or "")
    )
    ref_texts = [ref.text for ref in first.references]
    assert any("सर्वार्थसिद्धि/1/5/17/5" in text for text in ref_texts), ref_texts
