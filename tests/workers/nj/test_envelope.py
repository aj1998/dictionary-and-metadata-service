from __future__ import annotations

from workers.ingestion.nj.config import load_config_for_shastra
from workers.ingestion.nj.envelope import build_envelope
from workers.ingestion.nj.models import (
    AnyavarthaItem,
    GathaExtract,
    GathaWordMeaningEntry,
    KalashExtract,
    KalashHindiEntry,
    KalashSanskritEntry,
    KalashWMEntry,
    PrimaryTeeka,
    SecondaryTeeka,
    ShastraParseResult,
)


def _make_result(gathas=None, secondary_kalashes=None):
    return ShastraParseResult(
        shastra_natural_key="समयसार",
        gathas=gathas or [],
        secondary_kalashes=secondary_kalashes or [],
        total_html_files_processed=1,
        parser_version="1.0.0",
        parsed_at="2026-01-01T00:00:00Z",
    )


def _make_gatha(**kwargs) -> GathaExtract:
    defaults = dict(
        shastra_natural_key="समयसार",
        gatha_number="001",
        page_html_id="001",
        html_filename="001.html",
        adhikaar_hi="मंगलाचरण",
        adhikaar_number=1,
        heading_hi="सिद्धों को नमस्कार",
    )
    defaults.update(kwargs)
    return GathaExtract(**defaults)


def _cfg():
    return load_config_for_shastra("samaysaar")


# ---------------------------------------------------------------------------
# Basic topology
# ---------------------------------------------------------------------------

def test_build_envelope_has_expected_topology():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="009",
        page_html_id="009-010",
        html_filename="009-010.html",
        adhikaar_hi="जीव अधिकार",
        adhikaar_number=2,
        heading_hi="test",
        is_combined_page=True,
        related_gatha_numbers=["010"],
        prakrit_text="णमो अरिहंताणं",
        anyavartha=AnyavarthaItem(
            full_anyavaarth="नमो अरिहंतों को",
            tagged_terms=[GathaWordMeaningEntry(source_word="णमो", meaning="नमो", position=1)],
        ),
    )
    result = _make_result(gathas=[g])
    env = build_envelope(result, cfg)

    assert "shastra_parse_result" in env
    assert "would_write" in env
    ww = env["would_write"]
    assert ww["mongo"]["gatha_prakrit"][0]["natural_key"] == "समयसार:9:prakrit"
    assert ww["mongo"]["teeka_gatha_mapping"][0]["natural_key"] == "समयसार:आत्मख्याती:9"
    assert ww["mongo"]["teeka_gatha_mapping"][0]["is_related"] == ["010"]
    assert ww["postgres"]["gathas"][0]["adhikaar_number"] == 2


# ---------------------------------------------------------------------------
# table field on postgres rows (JK parity)
# ---------------------------------------------------------------------------

def test_postgres_rows_have_table_field():
    cfg = _cfg()
    g = _make_gatha(prakrit_text="test")
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]["postgres"]

    assert ww["authors"][0]["table"] == "authors"
    assert ww["shastras"][0]["table"] == "shastras"
    assert ww["teekas"][0]["table"] == "teekas"
    assert ww["publications"][0]["table"] == "publications"
    assert ww["gathas"][0]["table"] == "gathas"


def test_postgres_kalasha_row_has_table_field():
    cfg = _cfg()
    k = KalashExtract(
        shastra_natural_key="समयसार",
        kalash_number="011",
        html_filename="011.html",
        heading_hi=None,
        preceding_primary_gatha_number="010",
    )
    result = _make_result(secondary_kalashes=[k])
    kalash_row = build_envelope(result, cfg)["would_write"]["postgres"]["kalashas"][0]
    assert kalash_row["table"] == "kalashas"


def test_postgres_teeka_chapters_have_table_field():
    cfg = _cfg()
    g = _make_gatha(adhikaar_number=1, adhikaar_hi="मंगलाचरण")
    chapters = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["postgres"]["teeka_chapters"]
    assert chapters[0]["table"] == "teeka_chapters"


# ---------------------------------------------------------------------------
# collection field on mongo docs (JK parity)
# ---------------------------------------------------------------------------

def test_mongo_docs_have_collection_field():
    cfg = _cfg()
    g = _make_gatha(
        prakrit_text="test",
        sanskrit_text="test",
        hindi_chhands=[],
        anyavartha=AnyavarthaItem(full_anyavaarth="test", tagged_terms=[]),
    )
    result = _make_result(gathas=[g])
    mongo = build_envelope(result, cfg)["would_write"]["mongo"]

    assert mongo["gatha_prakrit"][0]["collection"] == "gatha_prakrit"
    assert mongo["gatha_sanskrit"][0]["collection"] == "gatha_sanskrit"
    assert mongo["teeka_gatha_mapping"][0]["collection"] == "teeka_gatha_mapping"


def test_mongo_kalash_docs_have_collection_field():
    cfg = _cfg()
    g = _make_gatha(
        primary_teeka=PrimaryTeeka(
            kalash_hindi=[KalashHindiEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="दोहा", text_hi="hi")],
            kalash_san=[KalashSanskritEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="दोहा", text_san="san")],
        )
    )
    result = _make_result(gathas=[g])
    mongo = build_envelope(result, cfg)["would_write"]["mongo"]
    assert mongo["kalash_hindi"][0]["collection"] == "kalash_hindi"
    assert mongo["kalash_sanskrit"][0]["collection"] == "kalash_sanskrit"


def test_mongo_secondary_kalash_docs_have_collection_field():
    cfg = _cfg()
    k = KalashExtract(
        shastra_natural_key="समयसार",
        kalash_number="011",
        html_filename="011.html",
        heading_hi=None,
        preceding_primary_gatha_number="010",
        prakrit_text="णाणम्हि",
    )
    result = _make_result(secondary_kalashes=[k])
    mongo = build_envelope(result, cfg)["would_write"]["mongo"]
    assert mongo["gatha_prakrit"][0]["collection"] == "gatha_prakrit"


# ---------------------------------------------------------------------------
# gatha_word_meanings removed from mongo output
# ---------------------------------------------------------------------------

def test_gatha_word_meanings_not_in_mongo():
    cfg = _cfg()
    g = _make_gatha(
        anyavartha=AnyavarthaItem(
            full_anyavaarth="नमो",
            tagged_terms=[GathaWordMeaningEntry(source_word="णमो", meaning="नमो", position=1)],
        ),
    )
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]
    assert "gatha_word_meanings" not in ww["mongo"]


def test_gatha_word_meanings_absent_from_secondary_kalash_mongo():
    cfg = _cfg()
    k = KalashExtract(
        shastra_natural_key="समयसार",
        kalash_number="011",
        html_filename="011.html",
        heading_hi=None,
        preceding_primary_gatha_number="010",
        anyavartha=AnyavarthaItem(
            full_anyavaarth="ज्ञान में",
            tagged_terms=[GathaWordMeaningEntry(source_word="णाणम्हि", meaning="ज्ञान में", position=1)],
        ),
    )
    result = _make_result(secondary_kalashes=[k])
    ww = build_envelope(result, cfg)["would_write"]
    assert "gatha_word_meanings" not in ww["mongo"]


# ---------------------------------------------------------------------------
# teeka_gatha_mapping — primary only, no secondary
# ---------------------------------------------------------------------------

def test_teeka_gatha_mapping_primary_only():
    cfg = _cfg()
    g = _make_gatha(
        anyavartha=AnyavarthaItem(full_anyavaarth="नमो", tagged_terms=[]),
    )
    result = _make_result(gathas=[g])
    tgm = build_envelope(result, cfg)["would_write"]["mongo"]["teeka_gatha_mapping"]
    assert len(tgm) == 1
    assert tgm[0]["teeka_natural_key"] == "समयसार:आत्मख्याती"


def test_teeka_gatha_mapping_has_tagged_terms():
    cfg = _cfg()
    g = _make_gatha(
        anyavartha=AnyavarthaItem(
            full_anyavaarth="नमो",
            tagged_terms=[GathaWordMeaningEntry(source_word="वंदित्तु", meaning="नमस्कार", position=1)],
        ),
    )
    result = _make_result(gathas=[g])
    tgm = build_envelope(result, cfg)["would_write"]["mongo"]["teeka_gatha_mapping"]
    assert tgm[0]["tagged_terms"] == [{"source_word": "वंदित्तु", "meaning": "नमस्कार"}]


# ---------------------------------------------------------------------------
# Preceding primary gatha — last gatha number from combined page
# ---------------------------------------------------------------------------

def test_secondary_kalash_gatha_nk_uses_last_gatha_number():
    cfg = _cfg()
    k = KalashExtract(
        shastra_natural_key="समयसार",
        kalash_number="011",
        html_filename="011.html",
        heading_hi=None,
        preceding_primary_gatha_number="010",
    )
    result = _make_result(secondary_kalashes=[k])
    ww = build_envelope(result, cfg)["would_write"]
    kalash_row = next(r for r in ww["postgres"]["kalashas"] if r["kalash_number"] == "11")
    assert kalash_row["gatha_natural_key"] == "समयसार:10"


# ---------------------------------------------------------------------------
# Neo4j nodes — {label, key, props} shape (JK parity)
# ---------------------------------------------------------------------------

def test_neo4j_shastra_node_shape():
    cfg = _cfg()
    result = _make_result(gathas=[_make_gatha()])
    nodes = build_envelope(result, cfg)["would_write"]["neo4j"]["nodes"]
    shastra_nodes = [n for n in nodes if n["label"] == "Shastra"]
    assert len(shastra_nodes) == 1
    n = shastra_nodes[0]
    assert n["key"] == "समयसार"
    assert "props" in n
    assert "title_hi" in n["props"]


def test_neo4j_topic_node_shape_and_dedup():
    cfg = _cfg()
    g1 = _make_gatha(gatha_number="001", heading_hi="सिद्धों को नमस्कार")
    g2 = _make_gatha(gatha_number="002", heading_hi="सिद्धों को नमस्कार")  # same heading → dedup
    g3 = _make_gatha(gatha_number="003", heading_hi="भेद विज्ञान")
    result = _make_result(gathas=[g1, g2, g3])
    nodes = build_envelope(result, cfg)["would_write"]["neo4j"]["nodes"]
    topic_nodes = [n for n in nodes if n["label"] == "Topic"]
    topic_keys = {n["key"] for n in topic_nodes}
    assert "सिद्धों को नमस्कार" in topic_keys
    assert "भेद विज्ञान" in topic_keys
    assert len(topic_nodes) == 2  # deduplicated
    # Check props shape
    t = next(n for n in topic_nodes if n["key"] == "सिद्धों को नमस्कार")
    assert t["props"]["display_text_hi"] == "सिद्धों को नमस्कार"
    assert t["props"]["source"] == "nj"


def test_neo4j_no_topic_node_for_none_heading():
    cfg = _cfg()
    g = _make_gatha(heading_hi=None)
    nodes = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["neo4j"]["nodes"]
    assert not any(n["label"] == "Topic" for n in nodes)


def test_neo4j_gatha_node_shape():
    cfg = _cfg()
    g = _make_gatha(gatha_number="001", heading_hi="सिद्धों को नमस्कार")
    nodes = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["neo4j"]["nodes"]
    gatha_nodes = [n for n in nodes if n["label"] == "Gatha"]
    assert len(gatha_nodes) == 1
    n = gatha_nodes[0]
    assert n["key"] == "समयसार:1"
    assert n["props"]["gatha_number"] == "1"
    assert n["props"]["shastra_natural_key"] == "समयसार"
    assert n["props"]["heading_hi"] == "सिद्धों को नमस्कार"


# ---------------------------------------------------------------------------
# Neo4j edges — {type, from: {label, key}, to: {label, key}, props} shape
# ---------------------------------------------------------------------------

def test_neo4j_gatha_topic_edge_shape():
    cfg = _cfg()
    g1 = _make_gatha(gatha_number="001", heading_hi="सिद्धों को नमस्कार")
    g2 = _make_gatha(gatha_number="002", heading_hi=None)
    result = _make_result(gathas=[g1, g2])
    edges = build_envelope(result, cfg)["would_write"]["neo4j"]["edges"]
    topic_edges = [e for e in edges if e["type"] == "MENTIONS_TOPIC"]
    assert len(topic_edges) == 1
    e = topic_edges[0]
    assert e["from"] == {"label": "Gatha", "key": "समयसार:1"}
    assert e["to"] == {"label": "Topic", "key": "सिद्धों को नमस्कार"}
    assert e["props"]["source"] == "nj"
    assert "weight" in e["props"]


def test_neo4j_no_edge_for_gatha_without_heading():
    cfg = _cfg()
    g = _make_gatha(heading_hi=None)
    edges = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["neo4j"]["edges"]
    assert edges == []


# ---------------------------------------------------------------------------
# Idempotency contracts — detailed shape (JK parity)
# ---------------------------------------------------------------------------

def test_idempotency_contracts_are_detailed():
    cfg = _cfg()
    result = _make_result(gathas=[_make_gatha()])
    contracts = build_envelope(result, cfg)["would_write"]["idempotency_contracts"]

    required_keys = {
        "postgres:authors", "postgres:shastras", "postgres:teekas", "postgres:publications",
        "postgres:gathas", "postgres:kalashas", "postgres:teeka_chapters",
        "mongo:gatha_prakrit", "mongo:gatha_sanskrit", "mongo:gatha_hindi_chhand",
        "mongo:teeka_gatha_mapping", "mongo:gatha_teeka_sanskrit", "mongo:gatha_teeka_bhaavarth_hindi",
        "mongo:kalash_sanskrit", "mongo:kalash_hindi", "mongo:kalash_word_meanings",
        "neo4j:Shastra", "neo4j:Topic", "neo4j:Gatha",
    }
    assert required_keys.issubset(set(contracts.keys()))

    # Each contract has the same shape as JK contracts
    for key, contract in contracts.items():
        assert "conflict_key" in contract, f"{key} missing conflict_key"
        assert "on_conflict" in contract, f"{key} missing on_conflict"
        assert "fields_replace" in contract, f"{key} missing fields_replace"
        assert "fields_append" in contract, f"{key} missing fields_append"
        assert "stores" in contract, f"{key} missing stores"

    # neo4j contracts use "merge"; postgres/mongo use "do_update"
    assert contracts["neo4j:Gatha"]["on_conflict"] == "merge"
    assert contracts["neo4j:Gatha"]["conflict_key"] == ["key"]
    assert contracts["postgres:gathas"]["on_conflict"] == "do_update"
    assert contracts["postgres:gathas"]["conflict_key"] == ["natural_key"]


# ---------------------------------------------------------------------------
# teeka_chapters (primary teeka only)
# ---------------------------------------------------------------------------

def test_teeka_chapters_grouped_by_adhikaar():
    cfg = _cfg()
    g1 = _make_gatha(gatha_number="001", adhikaar_number=1, adhikaar_hi="मंगलाचरण")
    g2 = _make_gatha(gatha_number="002", adhikaar_number=2, adhikaar_hi="पीठिका")
    g3 = _make_gatha(gatha_number="003", adhikaar_number=2, adhikaar_hi="पीठिका")
    result = _make_result(gathas=[g1, g2, g3])
    chapters = build_envelope(result, cfg)["would_write"]["postgres"]["teeka_chapters"]
    assert len(chapters) == 2
    ch1 = next(c for c in chapters if c["chapter_number"] == 1)
    assert ch1["natural_key"] == "समयसार:आत्मख्याती:chapter:1"
    assert ch1["teeka_natural_key"] == "समयसार:आत्मख्याती"
    assert ch1["start_gatha_natural_key"] == "समयसार:1"
    assert ch1["end_gatha_natural_key"] == "समयसार:1"
    ch2 = next(c for c in chapters if c["chapter_number"] == 2)
    assert ch2["start_gatha_natural_key"] == "समयसार:2"
    assert ch2["end_gatha_natural_key"] == "समयसार:3"


def test_teeka_chapters_skips_none_adhikaar():
    cfg = _cfg()
    g = _make_gatha(gatha_number="001", adhikaar_number=None, adhikaar_hi=None)
    chapters = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["postgres"]["teeka_chapters"]
    assert chapters == []


def test_teeka_chapters_name_in_lang_text():
    cfg = _cfg()
    g = _make_gatha(gatha_number="001", adhikaar_number=1, adhikaar_hi="मंगलाचरण")
    chapters = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["postgres"]["teeka_chapters"]
    assert chapters[0]["name"] == [{"lang": "hin", "script": "Deva", "text": "मंगलाचरण"}]


# ---------------------------------------------------------------------------
# kalash WM local-to-global index mapping (regression)
# ---------------------------------------------------------------------------

def test_build_envelope_maps_local_kalash_wm_to_global_index():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="011",
        page_html_id="011",
        html_filename="011.html",
        primary_teeka=PrimaryTeeka(
            kalash_hindi=[
                KalashHindiEntry(
                    local_kalash_index=1,
                    global_kalash_index=4,
                    chhand_type="दोहा",
                    text_hi="हिंदी",
                )
            ],
            kalash_word_meanings={
                1: [KalashWMEntry(source_word="स्वानुभूत्या चकासते", meaning="निज अनुभव से प्रकाशित")]
            },
        ),
    )
    result = _make_result(gathas=[g])
    env = build_envelope(result, cfg)
    wms = env["would_write"]["mongo"]["kalash_word_meanings"]
    assert len(wms) == 1
    assert wms[0]["kalash_number"] == "4"
    assert wms[0]["entries"][0]["meaning"] == "निज अनुभव से प्रकाशित"
