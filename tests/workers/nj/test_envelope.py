from __future__ import annotations

from workers.ingestion.jainkosh.models import Multilingual, ParsedTable
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
    ShortFontAnchor,
    ShortFontEntry,
    ShastraParseResult,
)
from workers.ingestion.nj.envelope import _GATHA, _KALASH, _TEEKA, _BHAAVARTH, _ADHYAAY


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
    assert ww["mongo"]["gatha_prakrit"][0]["natural_key"] == "समयसार:गाथा:9:prakrit"
    assert ww["mongo"]["teeka_gatha_mapping"][0]["natural_key"] == "समयसार:आत्मख्याति:9"
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
    assert tgm[0]["teeka_natural_key"] == "समयसार:आत्मख्याति"


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
    assert tgm[0]["tagged_terms"] == [{
        "source_word": "वंदित्तु",
        "meaning": "नमस्कार",
        "position": 1,
        "start_offset": None,
        "end_offset": None,
    }]


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
    assert kalash_row["gatha_natural_key"] == "समयसार:गाथा:10"
    # Natural key should use Hindi label
    assert kalash_row["natural_key"] == "समयसार:तात्पर्यवृत्ति:कलश:11"


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
    assert n["key"] == "समयसार:गाथा:1"
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
    assert e["from"] == {"label": "Gatha", "key": "समयसार:गाथा:1"}
    assert e["to"] == {"label": "Topic", "key": "सिद्धों को नमस्कार"}
    assert e["props"]["source"] == "nj"
    assert "weight" in e["props"]


def test_neo4j_no_mentions_topic_edge_for_gatha_without_heading():
    cfg = _cfg()
    g = _make_gatha(heading_hi=None)
    edges = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["neo4j"]["edges"]
    assert not any(e["type"] == "MENTIONS_TOPIC" for e in edges)


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
        "neo4j:Shastra", "neo4j:Teeka", "neo4j:Publication",
        "neo4j:Topic", "neo4j:Gatha", "neo4j:GathaTeeka", "neo4j:GathaTeekaBhaavarth",
        "neo4j:Kalash", "neo4j:KalashBhaavarth",
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
    assert ch1["natural_key"] == "समयसार:आत्मख्याति:अध्याय:1"
    assert ch1["teeka_natural_key"] == "समयसार:आत्मख्याति"
    assert ch1["start_gatha_natural_key"] == "समयसार:गाथा:1"
    assert ch1["end_gatha_natural_key"] == "समयसार:गाथा:1"
    ch2 = next(c for c in chapters if c["chapter_number"] == 2)
    assert ch2["start_gatha_natural_key"] == "समयसार:गाथा:2"
    assert ch2["end_gatha_natural_key"] == "समयसार:गाथा:3"


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
    # Natural key must use Hindi कलश label
    assert wms[0]["kalash_natural_key"] == "समयसार:आत्मख्याति:कलश:4"
    assert wms[0]["natural_key"] == "समयसार:आत्मख्याति:कलश:4:word_meanings"


# ---------------------------------------------------------------------------
# Hindi labels in natural keys (matching JK style)
# ---------------------------------------------------------------------------

def test_kalash_natural_key_uses_hindi_label():
    """Primary kalash NKs must use कलश (not kalash)."""
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(
            kalash_san=[KalashSanskritEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="अनुष्टुभ्", text_san="नम:")],
            kalash_hindi=[KalashHindiEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="दोहा", text_hi="hi")],
        ),
    )
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]
    pg_kalash = ww["postgres"]["kalashas"][0]
    assert ":कलश:" in pg_kalash["natural_key"], f"Expected Hindi कलश, got: {pg_kalash['natural_key']}"
    mongo_san = ww["mongo"]["kalash_sanskrit"][0]
    assert ":कलश:" in mongo_san["natural_key"]
    assert ":कलश:" in mongo_san["kalash_natural_key"]


def test_gatha_teeka_sanskrit_nk_uses_hindi_label():
    """gatha_teeka_sanskrit NKs must use टीका (not teeka)."""
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(gatha_teeka_san="अथ सूत्रावतार"),
    )
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]
    san_doc = ww["mongo"]["gatha_teeka_sanskrit"][0]
    assert ":टीका:" in san_doc["natural_key"], f"Expected Hindi टीका, got: {san_doc['natural_key']}"


def test_gatha_teeka_bhaavarth_nk_uses_hindi_label():
    """gatha_teeka_bhaavarth_hindi NKs must use भावार्थ (not bhaavarth)."""
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(gatha_teeka_bhaavarth_md="भावार्थ text"),
    )
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]
    bh_doc = ww["mongo"]["gatha_teeka_bhaavarth_hindi"][0]
    assert ":भावार्थ:" in bh_doc["natural_key"], f"Expected Hindi भावार्थ, got: {bh_doc['natural_key']}"


def test_secondary_kalash_nks_use_hindi_labels():
    """Secondary kalash NKs must use Hindi labels: कलश, टीका, भावार्थ."""
    cfg = _cfg()
    k = KalashExtract(
        shastra_natural_key="समयसार",
        kalash_number="011",
        html_filename="011.html",
        heading_hi=None,
        preceding_primary_gatha_number="010",
        prakrit_text="णाणम्हि",
        secondary_teeka=SecondaryTeeka(
            gatha_teeka_san="Sanskrit text",
            gatha_teeka_bhaavarth_md="Hindi bhaavarth",
        ),
    )
    result = _make_result(secondary_kalashes=[k])
    ww = build_envelope(result, cfg)["would_write"]
    # Postgres kalash NK
    pg_kalash = next(r for r in ww["postgres"]["kalashas"])
    assert ":कलश:" in pg_kalash["natural_key"]
    # Mongo teeka_san NK
    san_doc = ww["mongo"]["gatha_teeka_sanskrit"][0]
    assert ":कलश:" in san_doc["natural_key"]
    assert ":टीका:" in san_doc["natural_key"]
    # Mongo bhaavarth NK
    bh_doc = ww["mongo"]["gatha_teeka_bhaavarth_hindi"][0]
    assert ":कलश:" in bh_doc["natural_key"]
    assert ":भावार्थ:" in bh_doc["natural_key"]


def test_teeka_chapter_nk_uses_hindi_adhyaay():
    """Teeka chapter NKs must use अध्याय (not chapter)."""
    cfg = _cfg()
    g = _make_gatha(gatha_number="001", adhikaar_number=1, adhikaar_hi="मंगलाचरण")
    chapters = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]["postgres"]["teeka_chapters"]
    assert ":अध्याय:" in chapters[0]["natural_key"], f"Expected Hindi अध्याय, got: {chapters[0]['natural_key']}"


# ---------------------------------------------------------------------------
# shortfont — gatha_teeka_bhaavarth_shortfont
# ---------------------------------------------------------------------------

def _make_sf_entry(n=1) -> ShortFontEntry:
    return ShortFontEntry(
        marker_number=n,
        marker_devanagari=str(n),
        anchor_text="मोक्ष-मार्ग",
        meaning="मोक्ष का विस्तार",
        is_definition=True,
        occurrences=[ShortFontAnchor(start_offset=10, end_offset=20)],
    )


def test_shortfont_doc_emitted_when_entries_present():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="161",
        primary_teeka=PrimaryTeeka(
            gatha_teeka_bhaavarth_md="भावार्थ text",
            gatha_teeka_bhaavarth_shortfont=[_make_sf_entry()],
        ),
    )
    ww = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]
    sf_docs = ww["mongo"]["gatha_teeka_bhaavarth_shortfont"]
    assert len(sf_docs) == 1
    doc = sf_docs[0]
    assert doc["collection"] == "gatha_teeka_bhaavarth_shortfont"
    assert doc["gatha_number"] == "161"
    assert len(doc["entries"]) == 1
    entry = doc["entries"][0]
    assert entry["marker_number"] == 1
    assert entry["anchor_text"] == "मोक्ष-मार्ग"
    assert entry["meaning"] == "मोक्ष का विस्तार"
    assert entry["is_definition"] is True
    assert entry["occurrences"] == [{"start_offset": 10, "end_offset": 20}]


def test_shortfont_doc_not_emitted_when_entries_empty():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(
            gatha_teeka_bhaavarth_md="भावार्थ text",
            gatha_teeka_bhaavarth_shortfont=[],
        ),
    )
    ww = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]
    assert ww["mongo"]["gatha_teeka_bhaavarth_shortfont"] == []


def test_shortfont_nk_pattern():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="161",
        primary_teeka=PrimaryTeeka(
            gatha_teeka_bhaavarth_shortfont=[_make_sf_entry()],
        ),
    )
    ww = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]
    doc = ww["mongo"]["gatha_teeka_bhaavarth_shortfont"][0]
    assert doc["natural_key"].endswith(":shortfont")
    assert doc["bhaavarth_natural_key"] == doc["natural_key"][:-len(":shortfont")]
    # NK contains गाथा:टीका:भावार्थ per spec
    assert ":गाथा:टीका:भावार्थ:" in doc["natural_key"]
    assert doc["natural_key"].endswith(":161:shortfont")


def test_shortfont_multi_gatha_duplication():
    """Combined page: entries duplicated for both gatha NKs."""
    cfg = _cfg()
    g009 = _make_gatha(
        gatha_number="009",
        html_filename="009-010.html",
        is_combined_page=True,
        related_gatha_numbers=["010"],
        primary_teeka=PrimaryTeeka(
            gatha_teeka_bhaavarth_shortfont=[_make_sf_entry()],
        ),
    )
    g010 = _make_gatha(
        gatha_number="010",
        html_filename="009-010.html",
        is_combined_page=True,
        related_gatha_numbers=["009"],
        primary_teeka=PrimaryTeeka(
            gatha_teeka_bhaavarth_shortfont=[_make_sf_entry()],
        ),
    )
    ww = build_envelope(_make_result(gathas=[g009, g010]), cfg)["would_write"]
    sf_docs = ww["mongo"]["gatha_teeka_bhaavarth_shortfont"]
    nks = {d["natural_key"] for d in sf_docs}
    assert any("9:shortfont" in nk for nk in nks)
    assert any("10:shortfont" in nk for nk in nks)
    assert len(sf_docs) == 2


def test_secondary_teeka_shortfont_emitted():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        secondary_teeka=SecondaryTeeka(
            gatha_teeka_bhaavarth_shortfont=[_make_sf_entry()],
        ),
    )
    ww = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]
    sf_docs = ww["mongo"]["gatha_teeka_bhaavarth_shortfont"]
    assert len(sf_docs) == 1
    # must use secondary publication NK
    from workers.ingestion.nj.config import load_config_for_shastra
    secondary = load_config_for_shastra("samaysaar").shastra.secondary_teekas[0]
    assert sf_docs[0]["publication_natural_key"] == secondary.publication_natural_key


def test_kalash_shortfont_emitted():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(
            kalash_san=[KalashSanskritEntry(local_kalash_index=1, global_kalash_index=4, chhand_type="अनुष्टुभ्", text_san="san")],
            kalash_hindi=[KalashHindiEntry(
                local_kalash_index=1,
                global_kalash_index=4,
                chhand_type="दोहा",
                text_hi="hi",
                shortfont=[_make_sf_entry()],
            )],
        ),
    )
    ww = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]
    sf_docs = ww["mongo"]["kalash_bhaavarth_shortfont"]
    assert len(sf_docs) == 1
    doc = sf_docs[0]
    assert doc["collection"] == "kalash_bhaavarth_shortfont"
    assert doc["kalash_number"] == "4"
    assert doc["natural_key"] == "समयसार:आत्मख्याति:कलश:4:shortfont"
    assert doc["kalash_natural_key"] == "समयसार:आत्मख्याति:कलश:4"
    assert len(doc["entries"]) == 1


def test_kalash_shortfont_not_emitted_when_empty():
    cfg = _cfg()
    g = _make_gatha(
        gatha_number="001",
        primary_teeka=PrimaryTeeka(
            kalash_san=[KalashSanskritEntry(local_kalash_index=1, global_kalash_index=1, chhand_type="अनुष्टुभ्", text_san="san")],
            kalash_hindi=[KalashHindiEntry(
                local_kalash_index=1,
                global_kalash_index=1,
                chhand_type="दोहा",
                text_hi="hi",
                shortfont=[],
            )],
        ),
    )
    ww = build_envelope(_make_result(gathas=[g]), cfg)["would_write"]
    assert ww["mongo"]["kalash_bhaavarth_shortfont"] == []


def test_shortfont_idempotency_contracts_present():
    cfg = _cfg()
    contracts = build_envelope(_make_result(), cfg)["would_write"]["idempotency_contracts"]
    assert "mongo:gatha_teeka_bhaavarth_shortfont" in contracts
    assert "mongo:kalash_bhaavarth_shortfont" in contracts
    sf_contract = contracts["mongo:gatha_teeka_bhaavarth_shortfont"]
    assert sf_contract["conflict_key"] == ["natural_key"]
    assert sf_contract["on_conflict"] == "do_update"
    assert "entries" in sf_contract["fields_replace"]


# ---------------------------------------------------------------------------
# tables — would_write.tables (Phase 2)
# ---------------------------------------------------------------------------

def _make_parsed_table(nk: str, parent_nk: str, seq: int = 1) -> ParsedTable:
    return ParsedTable(
        natural_key=nk,
        seq=seq,
        parent_natural_key=parent_nk,
        parent_kind="gatha_teeka_bhaavarth",
        table_type="index",
        raw_html="<table><tr><th>head</th></tr><tr><td>cell</td></tr></table>",
        cells=[["head"], ["cell"]],
        header_rows=1,
        plaintext="head cell",
        caption=[Multilingual(lang="hin", script="Deva", text="सारिणी")],
    )


def test_would_write_has_tables_key():
    cfg = _cfg()
    result = _make_result(gathas=[_make_gatha()])
    ww = build_envelope(result, cfg)["would_write"]
    assert "tables" in ww


def test_tables_empty_when_no_tables_parsed():
    cfg = _cfg()
    result = _make_result(gathas=[_make_gatha()])
    ww = build_envelope(result, cfg)["would_write"]
    assert ww["tables"] == []


def test_primary_teeka_tables_emitted_in_would_write():
    cfg = _cfg()
    table_nk = "table:nj:test:parent:01"
    g = _make_gatha(
        gatha_number="007",
        primary_teeka=PrimaryTeeka(
            gatha_teeka_bhaavarth_md="भावार्थ text [तालिका देखें](table://table:nj:test:parent:01)",
            tables=[_make_parsed_table(table_nk, "test:parent")],
        ),
    )
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]
    assert len(ww["tables"]) == 1
    t = ww["tables"][0]
    assert t["natural_key"] == table_nk
    assert t["table_type"] == "index"
    assert t["parent_kind"] == "gatha_teeka_bhaavarth"


def test_secondary_teeka_tables_emitted_in_would_write():
    cfg = _cfg()
    table_nk = "table:nj:test:secondary:01"
    g = _make_gatha(
        gatha_number="007",
        secondary_teeka=SecondaryTeeka(
            gatha_teeka_bhaavarth_md="भावार्थ",
            tables=[_make_parsed_table(table_nk, "test:secondary")],
        ),
    )
    result = _make_result(gathas=[g])
    ww = build_envelope(result, cfg)["would_write"]
    assert any(t["natural_key"] == table_nk for t in ww["tables"])


def test_secondary_kalash_tables_emitted_in_would_write():
    cfg = _cfg()
    table_nk = "table:nj:test:kalash:01"
    k = KalashExtract(
        shastra_natural_key="समयसार",
        kalash_number="011",
        html_filename="011.html",
        heading_hi=None,
        preceding_primary_gatha_number="010",
        secondary_teeka=SecondaryTeeka(
            gatha_teeka_bhaavarth_md="कलश भावार्थ",
            tables=[_make_parsed_table(table_nk, "test:kalash", seq=1)],
        ),
    )
    result = _make_result(secondary_kalashes=[k])
    ww = build_envelope(result, cfg)["would_write"]
    assert any(t["natural_key"] == table_nk for t in ww["tables"])


def test_tables_idempotency_contract_present():
    cfg = _cfg()
    contracts = build_envelope(_make_result(), cfg)["would_write"]["idempotency_contracts"]
    assert "postgres:tables" in contracts
    c = contracts["postgres:tables"]
    assert c["conflict_key"] == ["natural_key"]
    assert c["on_conflict"] == "do_update"
    assert "table_type" in c["fields_replace"]
