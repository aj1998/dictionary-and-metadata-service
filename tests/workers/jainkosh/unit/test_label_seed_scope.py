from pathlib import Path
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def _result():
    return parse_keyword_html(
        Path(__file__).parents[1].joinpath("fixtures", "द्रव्य.html").read_text(encoding="utf-8"),
        "https://example.org/wiki/द्रव्य",
        load_config(),
    )


def _walk(subs):
    for s in subs:
        yield s
        yield from _walk(s.children)


def test_no_label_seed_for_translation_inline_dekhen():
    res = _result()
    bad = [
        s for sec in res.page_sections for s in _walk(sec.subsections)
        if "जो सत् लक्षणवाला" in (s.heading_text or "")
        and s.is_synthetic
    ]
    assert bad == [], bad


def test_label_seed_for_redlink_row_uses_trimmed_label():
    res = _result()
    target = None
    for sec in res.page_sections:
        for s in _walk(sec.subsections):
            if s.heading_text == "इसी प्रकार ‘गुणपर्ययवद् द्रव्यं’ या ‘गुणसमुदायो द्रव्यं’ भी वे नहीं कह सकते":
                target = s
                break
    assert target is not None, "label-seed not emitted with trimmed text"
    assert target.label_topic_seed is True
