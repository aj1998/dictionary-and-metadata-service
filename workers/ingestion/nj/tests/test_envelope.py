from __future__ import annotations

from workers.ingestion.nj.config import load_config_for_shastra
from workers.ingestion.nj.envelope import build_envelope
from workers.ingestion.nj.models import (
    AnyavarthaItem,
    GathaExtract,
    GathaWordMeaningEntry,
    KalashHindiEntry,
    KalashWMEntry,
    PrimaryTeeka,
    ShastraParseResult,
)


def test_build_envelope_has_expected_topology():
    cfg = load_config_for_shastra("samaysaar")
    g = GathaExtract(
        shastra_natural_key="samaysaar",
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
    result = ShastraParseResult(
        shastra_natural_key="samaysaar",
        gathas=[g],
        secondary_kalashes=[],
        total_html_files_processed=1,
        parser_version="1.0.0",
        parsed_at="2026-01-01T00:00:00Z",
    )

    env = build_envelope(result, cfg)
    assert "shastra_parse_result" in env
    assert "would_write" in env
    ww = env["would_write"]
    assert ww["mongo"]["gatha_prakrit"][0]["natural_key"] == "samaysaar:009:prakrit"
    assert ww["mongo"]["teeka_gatha_mapping"][0]["natural_key"] == "samaysaar:amritchandra:009"
    assert ww["mongo"]["teeka_gatha_mapping"][0]["is_related"] == ["010"]
    assert ww["postgres"]["gathas"][0]["adhikaar_number"] == 2


def test_build_envelope_maps_local_kalash_wm_to_global_index():
    cfg = load_config_for_shastra("samaysaar")
    g = GathaExtract(
        shastra_natural_key="samaysaar",
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
    result = ShastraParseResult(
        shastra_natural_key="samaysaar",
        gathas=[g],
        secondary_kalashes=[],
        total_html_files_processed=1,
        parser_version="1.0.0",
        parsed_at="2026-01-01T00:00:00Z",
    )
    env = build_envelope(result, cfg)
    wms = env["would_write"]["mongo"]["kalash_word_meanings"]
    assert len(wms) == 1
    assert wms[0]["kalash_number"] == "004"
    assert wms[0]["entries"][0]["meaning"] == "निज अनुभव से प्रकाशित"
