from pathlib import Path
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def test_purankosh_definitions_have_no_paren_n_prefix():
    html = Path(__file__).parents[1].joinpath("fixtures", "आत्मा.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, "https://example.org/wiki/आत्मा", load_config())
    purankosh_secs = [s for s in res.page_sections if s.section_kind == "puraankosh"]
    assert purankosh_secs
    for sec in purankosh_secs:
        for d in sec.definitions:
            text = (d.blocks[0].text_devanagari or "")
            assert not text.lstrip().startswith("(")
            import re
            assert re.match(r"^\s*\(\d+\)\s*", text) is None, text
