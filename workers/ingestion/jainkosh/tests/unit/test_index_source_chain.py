from pathlib import Path

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

FIXTURE = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"


def _result():
    html = FIXTURE.read_text(encoding="utf-8")
    cfg = load_config()
    return parse_keyword_html(html, "https://example.org/wiki/द्रव्य", cfg)


def _by_label(rels, label):
    for rel in rels:
        if rel.label_text == label:
            return rel
    raise AssertionError(f"label not found: {label}")


def test_top_level_index_relation_resolves_to_strong_heading():
    res = _result()
    rel = _by_label(res.page_sections[0].index_relations, "द्रव्य का लक्षण ‘अर्थक्रियाकारित्व’")
    assert rel.source_topic_path_chain == ["1"]
    assert rel.source_topic_natural_key_chain == ["द्रव्य:द्रव्य-के-भेद-व-लक्षण"]


def test_nested_index_relation_resolves_full_chain():
    res = _result()
    rel = _by_label(res.page_sections[0].index_relations, "परमाणु में कथंचित् सावयव निरवयवपना")
    assert rel.source_topic_path_chain == ["4", "4.2"]
    nks = rel.source_topic_natural_key_chain
    assert nks[0] == "द्रव्य:सत्-व-द्रव्य-में-कथंचित्-भेदाभेद"
    assert nks[-1].endswith("भेदाभेद")


def test_unresolvable_label_falls_back_to_keyword():
    res = _result()
    rel = _by_label(res.page_sections[0].index_relations, "संसारी जीव का कथंचित् मूर्तत्व")
    assert rel.source_topic_path_chain == []
    assert rel.source_topic_natural_key_chain == []
