"""Integration tests for parse_reference_text()."""

import pytest

from workers.ingestion.jainkosh.config import (
    DevanagariNormalizationConfig,
    DevanagariNormSubstitution,
    ReferenceConfig,
    ReferenceNeedsManualMatchConfig,
    ReferenceMoolConfig,
    ReferenceNoisePhraseConfig,
    ReferenceSectionKeywordsConfig,
    ReferenceRawHtmlConfig,
    ReferenceSemicolonSplitConfig,
)
from workers.ingestion.jainkosh.parse_reference import (
    ShastraEntry,
    ShastraRegistry,
    _normalise,
    parse_format_string,
    parse_reference_text,
)

NORM_SUBS = [
    DevanagariNormSubstitution(**{"from": "ण्ड", "to": "ंड"}),
    DevanagariNormSubstitution(**{"from": "ण्ठ", "to": "ंठ"}),
    DevanagariNormSubstitution(**{"from": "ञ्च", "to": "ंच"}),
    DevanagariNormSubstitution(**{"from": "ञ्ज", "to": "ंज"}),
    DevanagariNormSubstitution(**{"from": "न्त", "to": "ंत"}),
    DevanagariNormSubstitution(**{"from": "न्द", "to": "ंद"}),
    DevanagariNormSubstitution(**{"from": "म्ब", "to": "ंब"}),
    DevanagariNormSubstitution(**{"from": "न्व", "to": "ंव"}),
    DevanagariNormSubstitution(**{"from": "ी", "to": "ि"}),
]

FIXTURE_ENTRIES = [
    {"shastra_name": "धवला", "short_form": "ध", "format": "पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा"},
    {"shastra_name": "प्रवचनसार", "short_form": "प्र.सा./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "पंचास्तिकाय / तात्पर्यवृत्ति", "short_form": "पं.त.", "format": "गाथा/पृष्ठ/पंक्ति"},
    {"shastra_name": "पंचास्तिकाय", "short_form": "पं.का./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "मूलाचार", "short_form": "मूला.", "format": "गाथा"},
    {"shastra_name": "गोम्मटसार जीवकाण्ड/मूल", "alternate_names": ["गोम्मटसार जीवकांड/मूल"],
     "short_form": "गो.जी./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "सर्वार्थसिद्धि", "short_form": "स.सि.", "format": "अध्याय/सूत्र/पृष्ठ"},
    {"shastra_name": "ज्ञानसार", "format": "श्लोक"},
    {"shastra_name": "ज्ञानार्णव", "format": "अधिकार/दोहक/पृष्ठ"},
    {"shastra_name": "द्रव्यसंग्रह", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "तत्त्वार्थ सूत्र", "short_form": "त.सू.", "format": "अध्याय/सूत्र"},
    {"shastra_name": "समयसार", "format": "गाथा/पृष्ठ/पंक्ति"},
    {"shastra_name": "समयसार/आत्मख्याति", "format": "गाथा/कलश"},
    {"shastra_name": "वसुनन्दि श्रावकाचार", "alternate_names": ["वसुनंदि श्रावकाचार", "वसुनंदी श्रावकाचार"],
     "format": "सूत्र"},
    {"shastra_name": "परमात्मप्रकाश", "format": "अधिकार/श्लोक"},
    {"shastra_name": "आलापपद्धति", "format": "अधिकार/सूत्र/पृष्ठ"},
]


@pytest.fixture
def norm_config():
    return DevanagariNormalizationConfig(enabled=True, substitutions=NORM_SUBS)


def _build_registry(entries_data, norm_config):
    reg = ShastraRegistry()
    for item in entries_data:
        raw_alt = item.get("alternate_names") or item.get("alternate_name") or []
        if isinstance(raw_alt, str):
            raw_alt = [raw_alt]
        entry = ShastraEntry(
            shastra_name=item["shastra_name"],
            alternate_names=[a for a in raw_alt if a],
            short_form=item.get("short_form", ""),
            format_str=item.get("format", ""),
            format_groups=parse_format_string(item.get("format", "")),
        )
        reg.entries.append(entry)
        reg._by_primary[_normalise(entry.shastra_name, norm_config)] = entry
        for alt in entry.alternate_names:
            reg._by_alternate[_normalise(alt, norm_config)] = entry
        if entry.short_form:
            reg._by_short_form[_normalise(entry.short_form, norm_config)] = entry
    return reg


@pytest.fixture
def registry(norm_config):
    return _build_registry(FIXTURE_ENTRIES, norm_config)


@pytest.fixture
def config(norm_config):
    return ReferenceConfig(
        selector="span.GRef",
        strip_inner_anchors=True,
        parse_strategy="structured",
        shastra_config_path=None,
        devanagari_normalization=norm_config,
        mool=ReferenceMoolConfig(keywords=["मूल"], exceptions=["मूलाचार"]),
        needs_manual_match=ReferenceNeedsManualMatchConfig(on_extra_groups=True, on_missing_fields=True),
        noise_phrases=ReferenceNoisePhraseConfig(enabled=True, phrases=["मूल गाथा या टीका", "मूल या टीका"]),
        section_keywords=ReferenceSectionKeywordsConfig(enabled=True, keywords=[
            "गाथा", "श्लोक", "पंक्ति", "कलश", "अधिकार", "अध्याय",
            "सर्ग", "परिच्छेद", "प्रकरण", "खण्ड", "भाग", "पुस्तक",
        ]),
        raw_html=ReferenceRawHtmlConfig(),
        semicolon_split=ReferenceSemicolonSplitConfig(),
    )


def _single(results):
    """Helper: assert list-of-one and return the single result."""
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    return results[0]


def test_dhavala_full_match(registry, config):
    results = parse_reference_text("धवला 1/1,1,1/84/1", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "धवला"
    assert result.match_method == "shastra_name"
    assert len(result.resolved_fields) == 6
    assert result.resolved_fields[0].field == "पुस्तक"
    assert result.resolved_fields[0].value == 1


def test_teeka_detection(registry, config):
    results = parse_reference_text("प्रवचनसार / तत्त्वप्रदीपिका 1/5", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.is_teeka is True
    assert result.teeka_name == "तत्त्वप्रदीपिका"
    assert result.shastra_name == "प्रवचनसार"


def test_full_name_match_not_teeka(registry, config):
    results = parse_reference_text("पंचास्तिकाय / तात्पर्यवृत्ति/16/35/12", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.is_teeka is False
    assert result.shastra_name == "पंचास्तिकाय / तात्पर्यवृत्ति"


def test_mool_stripped(registry, config):
    results = parse_reference_text("प्रवचनसार मूल 1/5", registry, config)
    result = _single(results)
    assert result.shastra_name == "प्रवचनसार"
    assert result.needs_manual_match is False


def test_mool_exception_not_stripped(registry, config):
    results = parse_reference_text("मूलाचार 15", registry, config)
    result = _single(results)
    assert result.shastra_name == "मूलाचार"
    assert result.needs_manual_match is False


def test_unknown_shastra(registry, config):
    results = parse_reference_text("अज्ञात ग्रन्थ 1/5", registry, config)
    result = _single(results)
    assert result.needs_manual_match is True
    assert result.shastra_name is None
    assert result.resolved_fields == []


def test_anusvar_normalisation(registry, config):
    results = parse_reference_text("गोम्मटसार जीवकांड/मूल 5/10", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "गोम्मटसार जीवकाण्ड/मूल"


def test_short_form_match(registry, config):
    results = parse_reference_text("ध 1/1,1,1/84/1", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.match_method == "short_form"
    assert result.shastra_name == "धवला"


def test_empty_text(registry, config):
    results = parse_reference_text("", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name is None


def test_name_only_no_numeric(registry, config):
    # Name matches, no numeric — on_missing_fields=True but no required fields triggered
    # धवला format has required groups; with no numeric at all → needs_manual=True
    results = parse_reference_text("धवला", registry, config)
    result = _single(results)
    assert result.shastra_name == "धवला"
    assert result.needs_manual_match is True  # 14A.2: strict — missing required groups


def test_extra_groups_needs_manual_and_empty_fields(registry, config):
    # सर्वार्थसिद्धि format=अध्याय/सूत्र/पृष्ठ (3 groups); value has 4 → extra
    results = parse_reference_text("सर्वार्थसिद्धि/1/5/17/5", registry, config)
    result = _single(results)
    assert result.needs_manual_match is True
    assert result.shastra_name == "सर्वार्थसिद्धि"
    assert result.resolved_fields == []


def test_parens_stripped_before_match(registry, config):
    results = parse_reference_text("( ज्ञानसार श्लोक 29)", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "ज्ञानसार"
    assert len(result.resolved_fields) == 1
    assert result.resolved_fields[0].field == "श्लोक"
    assert result.resolved_fields[0].value == 29


def test_parens_and_keyword_stripped(registry, config):
    results = parse_reference_text("( ज्ञानार्णव अधिकार 32/5/317)", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "ज्ञानार्णव"
    assert len(result.resolved_fields) == 3


def test_section_keyword_pustak_stripped(registry, config):
    # "पुस्तक" keyword is removed, exposing "धवला" as the shastra name
    results = parse_reference_text("धवला पुस्तक 13/5,5,50/282/9", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "धवला"
    assert len(result.resolved_fields) == 6


def test_noise_phrase_removed(registry, config):
    # "मूल गाथा या टीका" removed as a whole phrase
    results = parse_reference_text("द्रव्यसंग्रह / मूल गाथा या टीका 14/46", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "द्रव्यसंग्रह"
    assert len(result.resolved_fields) == 2


def test_space_agnostic_matching(registry, config):
    # "तत्त्वार्थसूत्र" (no space) matches "तत्त्वार्थ सूत्र" in registry
    results = parse_reference_text("तत्त्वार्थसूत्र 1/5", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "तत्त्वार्थ सूत्र"
    assert len(result.resolved_fields) == 2


def test_section_keyword_in_teeka_name(registry, config):
    # "गाथा" keyword removed from "समयसार / आत्मख्याति गाथा 8"
    # After removal: "समयसार / आत्मख्याति 8"
    # "समयसार/आत्मख्याति" is a full entry in registry; format=गाथा/कलश (R=2)
    # With on_missing_fields=True (14A.2): V=1 < R=2 → needs_manual
    results = parse_reference_text("समयसार / आत्मख्याति गाथा 8", registry, config)
    result = _single(results)
    assert result.shastra_name == "समयसार/आत्मख्याति"
    assert result.needs_manual_match is True   # 14A.2: strict — missing कलश group
    assert result.resolved_fields == []


# ---------------------------------------------------------------------------
# 14A.2: strict group count — previously-valid partial citations now need_manual
# ---------------------------------------------------------------------------

def test_partial_numeric_strict_needs_manual(registry, config):
    # 14A.2: पंचास्तिकाय format=गाथा/पृष्ठ (R=2); only 1 value → needs_manual
    results = parse_reference_text("पंचास्तिकाय/10", registry, config)
    result = _single(results)
    assert result.needs_manual_match is True
    assert result.shastra_name == "पंचास्तिकाय"
    assert result.resolved_fields == []


def test_aalappaddhati_partial_strict(registry, config):
    # 14A.2: आलापपद्धति format=अधिकार/सूत्र/पृष्ठ (R=3); V=1 → needs_manual
    results = parse_reference_text("आलापपद्धति/6", registry, config)
    result = _single(results)
    assert result.needs_manual_match is True
    assert result.shastra_name == "आलापपद्धति"


def test_dhavala_partial_three_groups(registry, config):
    # 14A.2: धवला format=पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा (R=4); V=3 → needs_manual
    results = parse_reference_text("धवला 15/33/9", registry, config)
    result = _single(results)
    assert result.needs_manual_match is True
    assert result.shastra_name == "धवला"


# ---------------------------------------------------------------------------
# 14A.3: alternate_names as list
# ---------------------------------------------------------------------------

def test_alternate_names_list_match(registry, config):
    # गोम्मटसार जीवकाण्ड/मूल — the ण्ड→ंड substitution makes both forms normalise
    # to the same key, so the primary name matches first (shastra_name).
    results = parse_reference_text("गोम्मटसार जीवकांड/मूल 5/10", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "गोम्मटसार जीवकाण्ड/मूल"
    # Both primary and alternate normalise the same way; shastra_name takes priority
    assert result.match_method in ("shastra_name", "alternate_name")


# ---------------------------------------------------------------------------
# 14A.4: range/list value expansion
# ---------------------------------------------------------------------------

def test_range_expansion_single_field(registry, config):
    # "पंचाध्यायी" not in fixture; use ज्ञानसार with format=श्लोक
    # Build a custom registry with a multi-field range
    from workers.ingestion.jainkosh.parse_reference import ShastraEntry, ShastraRegistry, _normalise, parse_format_string
    custom_reg = ShastraRegistry()
    entry = ShastraEntry(
        shastra_name="ज्ञानसार",
        alternate_names=[],
        short_form="",
        format_str="श्लोक",
        format_groups=parse_format_string("श्लोक"),
    )
    custom_reg.entries.append(entry)
    custom_reg._by_primary[_normalise("ज्ञानसार", config.devanagari_normalization)] = entry

    # Range: "95-96" → 2 results
    results = parse_reference_text("ज्ञानसार 95-96", custom_reg, config)
    assert len(results) == 2
    assert all(r.needs_manual_match is False for r in results)
    values = sorted(r.resolved_fields[0].value for r in results)
    assert values == [95, 96]


def test_list_expansion(registry, config):
    # Use समयसार/आत्मख्याति format=गाथा/कलश; value="8,86" for गाथा
    custom_reg = ShastraRegistry()
    entry = ShastraEntry(
        shastra_name="आप्तमीमांसा",
        alternate_names=[],
        short_form="",
        format_str="श्लोक",
        format_groups=parse_format_string("श्लोक"),
    )
    custom_reg.entries.append(entry)
    custom_reg._by_primary[_normalise("आप्तमीमांसा", config.devanagari_normalization)] = entry

    results = parse_reference_text("आप्तमीमांसा 8,86", custom_reg, config)
    assert len(results) == 2
    values = sorted(r.resolved_fields[0].value for r in results)
    assert values == [8, 86]


def test_range_list_combined(registry, config):
    # "1-3,39" → [1,2,3,39] → 4 results
    custom_reg = ShastraRegistry()
    entry = ShastraEntry(
        shastra_name="परीक्षा",
        alternate_names=[],
        short_form="",
        format_str="सूत्र",
        format_groups=parse_format_string("सूत्र"),
    )
    custom_reg.entries.append(entry)
    custom_reg._by_primary[_normalise("परीक्षा", config.devanagari_normalization)] = entry

    results = parse_reference_text("परीक्षा 1-3,39", custom_reg, config)
    assert len(results) == 4
    values = sorted(r.resolved_fields[0].value for r in results)
    assert values == [1, 2, 3, 39]


def test_cartesian_product_expansion(registry, config):
    # Two fields each with a range → cartesian product
    custom_reg = ShastraRegistry()
    entry = ShastraEntry(
        shastra_name="विचार",
        alternate_names=[],
        short_form="",
        format_str="गाथा/पृष्ठ",
        format_groups=parse_format_string("गाथा/पृष्ठ"),
    )
    custom_reg.entries.append(entry)
    custom_reg._by_primary[_normalise("विचार", config.devanagari_normalization)] = entry

    # format=गाथा/पृष्ठ, value="1-2/5,6" → गाथा in [1,2], पृष्ठ in [5,6] → 4 results
    results = parse_reference_text("विचार 1-2/5,6", custom_reg, config)
    assert len(results) == 4


# ---------------------------------------------------------------------------
# 14A.5: leading-digit coercion
# ---------------------------------------------------------------------------

def test_leading_digit_coercion(registry, config):
    # "309परउद्धृत" → value=309 (leading digits extracted)
    custom_reg = ShastraRegistry()
    entry = ShastraEntry(
        shastra_name="परीक्षामत",
        alternate_names=[],
        short_form="",
        format_str="पृष्ठ",
        format_groups=parse_format_string("पृष्ठ"),
    )
    custom_reg.entries.append(entry)
    custom_reg._by_primary[_normalise("परीक्षामत", config.devanagari_normalization)] = entry

    results = parse_reference_text("परीक्षामत 309परउद्धृत", custom_reg, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.resolved_fields[0].value == 309


def test_non_numeric_value_needs_manual(registry, config):
    custom_reg = ShastraRegistry()
    entry = ShastraEntry(
        shastra_name="परीक्षामत",
        alternate_names=[],
        short_form="",
        format_str="पृष्ठ",
        format_groups=parse_format_string("पृष्ठ"),
    )
    custom_reg.entries.append(entry)
    custom_reg._by_primary[_normalise("परीक्षामत", config.devanagari_normalization)] = entry

    # "abc" has no leading digits → mismatch → needs_manual (with on_missing_fields=True)
    results = parse_reference_text("परीक्षामत abc", custom_reg, config)
    result = _single(results)
    assert result.needs_manual_match is True


# ---------------------------------------------------------------------------
# 14A.6: mool-as-teeka fix
# ---------------------------------------------------------------------------

def test_mool_slash_not_teeka(registry, config):
    # "परमात्मप्रकाश/ मूल/2/27" → मूल is mool marker, not teeka
    results = parse_reference_text("परमात्मप्रकाश/ मूल/2/27", registry, config)
    result = _single(results)
    assert result.is_teeka is False
    assert result.shastra_name == "परमात्मप्रकाश"


# ---------------------------------------------------------------------------
# 14A.7: short/long-i normalisation
# ---------------------------------------------------------------------------

def test_short_long_i_normalisation(registry, config):
    # वसुनन्दि श्रावकाचार (registry) ↔ वसुनंदी श्रावकाचार (cited)
    results = parse_reference_text("वसुनंदी श्रावकाचार 27", registry, config)
    result = _single(results)
    assert result.needs_manual_match is False
    assert result.shastra_name == "वसुनन्दि श्रावकाचार"


# ---------------------------------------------------------------------------
# 14A.8: trailing non-numeric stripping
# ---------------------------------------------------------------------------

def test_trailing_non_numeric_stripped(registry, config):
    # "धवला 3/1,2,1/2/ पंक्ति नं." → keyword "पंक्ति" removed → trailing "नं." stripped
    # → numeric_clean="3/1,2,1/2" (3 groups). Format has 4 required groups.
    # With strict on_missing_fields=True (14A.2): V=3 < R=4 → needs_manual.
    # Key check: shastra IS matched; it's the numeric groups that cause rejection.
    results = parse_reference_text("धवला 3/1,2,1/2/ पंक्ति नं.", registry, config)
    result = _single(results)
    assert result.shastra_name == "धवला"
    assert result.needs_manual_match is True   # strict: गाथा group missing
    assert result.resolved_fields == []


# ---------------------------------------------------------------------------
# 14A.1: puraankosh skips resolution (tested via refs.py layer)
# ---------------------------------------------------------------------------

def test_puraankosh_skips_resolution():
    """Resolution is skipped for puraankosh — tested via _resolve_reference."""
    from workers.ingestion.jainkosh.refs import _resolve_reference
    from unittest.mock import MagicMock

    cfg = MagicMock()
    cfg.reference.parse_strategy = "structured"
    cfg.shastra_registry = MagicMock()  # would be called if not skipped

    results = _resolve_reference("धवला 1/5", cfg, section_kind="puraankosh")
    assert results == [{}]
    # registry was NOT consulted
    cfg.shastra_registry.assert_not_called()
