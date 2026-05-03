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


def test_link_wrapped_heading_li_resolves_source_path():
    """षट् द्रव्य विभाजन index LI has <strong><a href="#3">; relations under
    its <ul> must resolve to source_topic_path_chain=["3"]."""
    res = _result()
    rels = res.page_sections[0].index_relations
    for label in [
        "संसारी जीव का कथंचित् मूर्तत्व",
        "द्रव्यों के भेदादि जानने का प्रयोजन",
        "जीव का असर्वगतपना",
        "कारण अकारण विभाग",
    ]:
        rel = _by_label(rels, label)
        assert rel.source_topic_path_chain == ["3"], f"failed for {label}"
        assert rel.source_topic_natural_key_chain == ["द्रव्य:षट्द्रव्य-विभाजन"], \
            f"failed for {label}"


def test_plain_strong_heading_derives_path_from_inner_ol():
    """4.3 and 4.4 LIs have plain-text <strong> (no anchor); path must be
    derived from their inner <ol>'s first anchor and cross-checked."""
    res = _result()
    rels = res.page_sections[0].index_relations

    rel_nitya = _by_label(rels, "द्रव्य में कथंचित् नित्यानियत्व")
    assert rel_nitya.source_topic_path_chain == ["4", "4.3"]

    rel_guna = _by_label(rels, "द्रव्य को गुण पर्याय और गुण पर्याय को द्रव्य रूप से लक्षित करना")
    assert rel_guna.source_topic_path_chain == ["4", "4.4"]

    rel_anek = _by_label(rels, "अनेक अपेक्षाओं से द्रव्य में भेदाभेद व विधि-निषेध")
    assert rel_anek.source_topic_path_chain == ["4", "4.4"]
