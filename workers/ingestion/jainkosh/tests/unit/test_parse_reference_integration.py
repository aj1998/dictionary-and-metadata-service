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
]

FIXTURE_ENTRIES = [
    {"shastra_name": "धवला", "short_form": "ध", "format": "पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा"},
    {"shastra_name": "प्रवचनसार", "short_form": "प्र.सा./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "पंचास्तिकाय / तात्पर्यवृत्ति", "short_form": "पं.त.", "format": "गाथा/पृष्ठ/पंक्ति"},
    {"shastra_name": "पंचास्तिकाय", "short_form": "पं.का./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "मूलाचार", "short_form": "मूला.", "format": "गाथा"},
    {"shastra_name": "गोम्मटसार जीवकाण्ड/मूल", "alternate_name": "गोम्मटसार जीवकांड/मूल",
     "short_form": "गो.जी./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "सर्वार्थसिद्धि", "short_form": "स.सि.", "format": "अध्याय/सूत्र/पृष्ठ"},
    {"shastra_name": "ज्ञानसार", "format": "श्लोक"},
    {"shastra_name": "ज्ञानार्णव", "format": "अधिकार/दोहक/पृष्ठ"},
    {"shastra_name": "द्रव्यसंग्रह", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "तत्त्वार्थ सूत्र", "short_form": "त.सू.", "format": "अध्याय/सूत्र"},
    {"shastra_name": "समयसार", "format": "गाथा/पृष्ठ/पंक्ति"},
    {"shastra_name": "समयसार/आत्मख्याति", "format": "गाथा/कलश"},
]


@pytest.fixture
def norm_config():
    return DevanagariNormalizationConfig(enabled=True, substitutions=NORM_SUBS)


@pytest.fixture
def registry(norm_config):
    reg = ShastraRegistry()
    for item in FIXTURE_ENTRIES:
        entry = ShastraEntry(
            shastra_name=item["shastra_name"],
            alternate_name=item.get("alternate_name"),
            short_form=item.get("short_form", ""),
            format_str=item.get("format", ""),
            format_groups=parse_format_string(item.get("format", "")),
        )
        reg.entries.append(entry)
        reg._by_primary[_normalise(entry.shastra_name, norm_config)] = entry
        if entry.alternate_name:
            reg._by_alternate[_normalise(entry.alternate_name, norm_config)] = entry
        if entry.short_form:
            reg._by_short_form[_normalise(entry.short_form, norm_config)] = entry
    return reg


@pytest.fixture
def config(norm_config):
    return ReferenceConfig(
        selector="span.GRef",
        strip_inner_anchors=True,
        parse_strategy="structured",
        shastra_config_path=None,
        devanagari_normalization=norm_config,
        mool=ReferenceMoolConfig(keywords=["मूल"], exceptions=["मूलाचार"]),
        needs_manual_match=ReferenceNeedsManualMatchConfig(on_extra_groups=True, on_missing_fields=False),
        noise_phrases=ReferenceNoisePhraseConfig(enabled=True, phrases=["मूल गाथा या टीका"]),
        section_keywords=ReferenceSectionKeywordsConfig(enabled=True, keywords=[
            "गाथा", "श्लोक", "पंक्ति", "कलश", "अधिकार", "अध्याय",
            "सर्ग", "परिच्छेद", "प्रकरण", "खण्ड", "भाग", "पुस्तक",
        ]),
        raw_html=ReferenceRawHtmlConfig(),
        semicolon_split=ReferenceSemicolonSplitConfig(),
    )


def test_dhavala_full_match(registry, config):
    result = parse_reference_text("धवला 1/1,1,1/84/1", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "धवला"
    assert result.match_method == "shastra_name"
    assert len(result.resolved_fields) == 6
    assert result.resolved_fields[0].field == "पुस्तक"
    assert result.resolved_fields[0].value == 1


def test_teeka_detection(registry, config):
    result = parse_reference_text("प्रवचनसार / तत्त्वप्रदीपिका 1/5", registry, config)
    assert result.needs_manual_match is False
    assert result.is_teeka is True
    assert result.teeka_name == "तत्त्वप्रदीपिका"
    assert result.shastra_name == "प्रवचनसार"


def test_full_name_match_not_teeka(registry, config):
    result = parse_reference_text("पंचास्तिकाय / तात्पर्यवृत्ति/16/35/12", registry, config)
    assert result.needs_manual_match is False
    assert result.is_teeka is False
    assert result.shastra_name == "पंचास्तिकाय / तात्पर्यवृत्ति"


def test_mool_stripped(registry, config):
    result = parse_reference_text("प्रवचनसार मूल 1/5", registry, config)
    assert result.shastra_name == "प्रवचनसार"
    assert result.needs_manual_match is False


def test_mool_exception_not_stripped(registry, config):
    result = parse_reference_text("मूलाचार 15", registry, config)
    assert result.shastra_name == "मूलाचार"
    assert result.needs_manual_match is False


def test_unknown_shastra(registry, config):
    result = parse_reference_text("अज्ञात ग्रन्थ 1/5", registry, config)
    assert result.needs_manual_match is True
    assert result.shastra_name is None
    assert result.resolved_fields == []


def test_anusvar_normalisation(registry, config):
    result = parse_reference_text("गोम्मटसार जीवकांड/मूल 5/10", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "गोम्मटसार जीवकाण्ड/मूल"


def test_short_form_match(registry, config):
    result = parse_reference_text("ध 1/1,1,1/84/1", registry, config)
    assert result.needs_manual_match is False
    assert result.match_method == "short_form"
    assert result.shastra_name == "धवला"


def test_empty_text(registry, config):
    result = parse_reference_text("", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name is None


def test_name_only_no_numeric(registry, config):
    # Name matches, no numeric — on_missing_fields=False so not flagged
    result = parse_reference_text("धवला", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "धवला"
    assert result.resolved_fields == []


# ---------------------------------------------------------------------------
# New tests for bug fixes
# ---------------------------------------------------------------------------

def test_partial_numeric_not_needs_manual(registry, config):
    # पंचास्तिकाय format=गाथा/पृष्ठ; only 1 group provided — valid with on_missing_fields=False
    result = parse_reference_text("पंचास्तिकाय/10", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "पंचास्तिकाय"
    assert len(result.resolved_fields) == 1
    assert result.resolved_fields[0].field == "गाथा"
    assert result.resolved_fields[0].value == 10


def test_extra_groups_needs_manual_and_empty_fields(registry, config):
    # सर्वार्थसिद्धि format=अध्याय/सूत्र/पृष्ठ (3 groups); value has 4 → extra
    result = parse_reference_text("सर्वार्थसिद्धि/1/5/17/5", registry, config)
    assert result.needs_manual_match is True
    assert result.shastra_name == "सर्वार्थसिद्धि"
    assert result.resolved_fields == []


def test_parens_stripped_before_match(registry, config):
    result = parse_reference_text("( ज्ञानसार श्लोक 29)", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "ज्ञानसार"
    assert result.resolved_fields == [{"field": "श्लोक", "value": 29}] or (
        len(result.resolved_fields) == 1
        and result.resolved_fields[0].field == "श्लोक"
        and result.resolved_fields[0].value == 29
    )


def test_parens_and_keyword_stripped(registry, config):
    result = parse_reference_text("( ज्ञानार्णव अधिकार 32/5/317)", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "ज्ञानार्णव"
    assert len(result.resolved_fields) == 3


def test_section_keyword_pусtак_stripped(registry, config):
    # "पुस्तक" keyword is removed, exposing "धवला" as the shastra name
    result = parse_reference_text("धवला पुस्तक 13/5,5,50/282/9", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "धवला"
    assert len(result.resolved_fields) == 6


def test_noise_phrase_removed(registry, config):
    # "मूल गाथा या टीका" removed as a whole phrase; remaining "/" leaves is_teeka handling
    result = parse_reference_text("द्रव्यसंग्रह / मूल गाथा या टीका 14/46", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "द्रव्यसंग्रह"
    assert len(result.resolved_fields) == 2


def test_space_agnostic_matching(registry, config):
    # "तत्त्वार्थसूत्र" (no space) matches "तत्त्वार्थ सूत्र" in registry
    result = parse_reference_text("तत्त्वार्थसूत्र 1/5", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "तत्त्वार्थ सूत्र"
    assert len(result.resolved_fields) == 2


def test_section_keyword_in_teeka_name(registry, config):
    # "गाथा" keyword removed from "समयसार / आत्मख्याति गाथा 8"
    # After removal: "समयसार / आत्मख्याति 8"
    # "समयसार/आत्मख्याति" is a full entry in registry → not treated as teeka
    result = parse_reference_text("समयसार / आत्मख्याति गाथा 8", registry, config)
    assert result.needs_manual_match is False
    assert result.shastra_name == "समयसार/आत्मख्याति"
    assert len(result.resolved_fields) >= 1
    assert result.resolved_fields[0].field == "गाथा"
    assert result.resolved_fields[0].value == 8
