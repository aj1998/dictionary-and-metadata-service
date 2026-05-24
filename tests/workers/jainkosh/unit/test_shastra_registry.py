"""Unit tests for ShastraRegistry."""

import pytest

from workers.ingestion.jainkosh.config import DevanagariNormalizationConfig, DevanagariNormSubstitution
from workers.ingestion.jainkosh.parse_reference import ShastraEntry, ShastraRegistry, parse_format_string


def _make_norm_config(substitutions=None):
    subs = substitutions or [
        DevanagariNormSubstitution(**{"from": "ण्ड", "to": "ंड"}),
    ]
    return DevanagariNormalizationConfig(enabled=True, substitutions=subs)


def _make_registry(entries_data, norm_config=None):
    if norm_config is None:
        norm_config = _make_norm_config()
    registry = ShastraRegistry()
    from workers.ingestion.jainkosh.parse_reference import _normalise
    for item in entries_data:
        # 14A.3: accept both alternate_name (legacy str) and alternate_names (list)
        raw_alt = item.get("alternate_names") or item.get("alternate_name") or []
        if isinstance(raw_alt, str):
            raw_alt = [raw_alt]
        alternate_names = [a for a in raw_alt if a]

        entry = ShastraEntry(
            shastra_name=item["shastra_name"],
            alternate_names=alternate_names,
            short_form=item.get("short_form", ""),
            format_str=item.get("format", ""),
            format_groups=parse_format_string(item.get("format", "")),
        )
        registry.entries.append(entry)
        registry._by_primary[_normalise(entry.shastra_name, norm_config)] = entry
        for alt in entry.alternate_names:
            registry._by_alternate[_normalise(alt, norm_config)] = entry
        if entry.short_form:
            registry._by_short_form[_normalise(entry.short_form, norm_config)] = entry
    return registry


FIXTURE_ENTRIES = [
    {"shastra_name": "धवला", "short_form": "ध", "format": "पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा"},
    {"shastra_name": "प्रवचनसार", "short_form": "प्र.सा./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "पंचास्तिकाय", "short_form": "पं.का./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "गोम्मटसार जीवकाण्ड/मूल",
     "alternate_names": ["गोम्मटसार जीवकांड/मूल"],
     "short_form": "गो.जी./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "मूलाचार", "short_form": "मूला.", "format": "गाथा"},
    {"shastra_name": "वसुनन्दि श्रावकाचार",
     "alternate_names": ["वसुनंदि श्रावकाचार", "वसुनंदी श्रावकाचार"],
     "format": "सूत्र"},
]


@pytest.fixture
def registry():
    return _make_registry(FIXTURE_ENTRIES)


def test_lookup_by_shastra_name(registry):
    entry, method = registry.lookup("धवला")
    assert entry is not None
    assert entry.shastra_name == "धवला"
    assert method == "shastra_name"


def test_lookup_by_alternate_name(registry):
    # After ण्ड→ंड substitution and space removal, both forms normalise to the same key.
    norm_config = _make_norm_config()
    from workers.ingestion.jainkosh.parse_reference import _normalise
    key = _normalise("गोम्मटसार जीवकांड/मूल", norm_config)
    entry, method = registry.lookup(key)
    assert entry is not None
    assert entry.shastra_name == "गोम्मटसार जीवकाण्ड/मूल"
    assert method in ("shastra_name", "alternate_name")


def test_lookup_by_short_form(registry):
    entry, method = registry.lookup("ध")
    assert entry is not None
    assert entry.shastra_name == "धवला"
    assert method == "short_form"


def test_lookup_unknown_returns_none(registry):
    entry, method = registry.lookup("अज्ञात")
    assert entry is None
    assert method is None


def test_substitution_normalisation():
    # "काण्ड" → "कांड" via ण्ड→ंड substitution
    norm_config = _make_norm_config([
        DevanagariNormSubstitution(**{"from": "ण्ड", "to": "ंड"}),
    ])
    entries = [{"shastra_name": "गोम्मटसार जीवकाण्ड", "format": "गाथा"}]
    registry = _make_registry(entries, norm_config)
    from workers.ingestion.jainkosh.parse_reference import _normalise
    # Query with anusvar form should match chandrabindu form in registry
    entry, method = registry.lookup(_normalise("गोम्मटसार जीवकांड", norm_config))
    assert entry is not None
    assert entry.shastra_name == "गोम्मटसार जीवकाण्ड"


def test_priority_shastra_name_over_alternate(registry):
    # If a name matches both primary and alternate, shastra_name takes priority
    entries = [
        {"shastra_name": "X", "alternate_names": ["Y"], "format": ""},
        {"shastra_name": "Y", "format": ""},
    ]
    reg = _make_registry(entries, _make_norm_config([]))
    entry, method = reg.lookup("Y")
    # primary match for "Y" entry
    assert method == "shastra_name"
    assert entry.shastra_name == "Y"


def test_alternate_names_multiple(registry):
    # वसुनन्दि श्रावकाचार has alternate_names=["वसुनंदि श्रावकाचार", "वसुनंदी श्रावकाचार"]
    # With ी→ि substitution both "वसुनंदि" and "वसुनंदी" normalise to same key as
    # the primary "वसुनन्दि" (after न्द→ंद), so shastra_name or alternate_name both
    # return the same entry. Method depends on which normalises identically to primary.
    norm_config = _make_norm_config([
        DevanagariNormSubstitution(**{"from": "ण्ड", "to": "ंड"}),
        DevanagariNormSubstitution(**{"from": "न्द", "to": "ंद"}),
        DevanagariNormSubstitution(**{"from": "ी", "to": "ि"}),
    ])
    reg = _make_registry(FIXTURE_ENTRIES, norm_config)
    from workers.ingestion.jainkosh.parse_reference import _normalise

    # Query with long-i form — must match the वसुनन्दि entry
    entry, method = reg.lookup(_normalise("वसुनंदी श्रावकाचार", norm_config))
    assert entry is not None
    assert entry.shastra_name == "वसुनन्दि श्रावकाचार"
    # Match method depends on normalisation: shastra_name or alternate_name both valid
    assert method in ("shastra_name", "alternate_name")


def test_short_long_i_normalisation():
    """14A.7: short-i ↔ long-i collapsing via substitution."""
    norm_config = _make_norm_config([
        DevanagariNormSubstitution(**{"from": "न्द", "to": "ंद"}),
        DevanagariNormSubstitution(**{"from": "ी", "to": "ि"}),
    ])
    entries = [{"shastra_name": "वसुनन्दि श्रावकाचार", "format": "सूत्र"}]
    reg = _make_registry(entries, norm_config)
    from workers.ingestion.jainkosh.parse_reference import _normalise

    # वसुनंदी → after न्द→ंद and ी→ि → normalises to same key as वसुनन्दि
    entry, method = reg.lookup(_normalise("वसुनंदी श्रावकाचार", norm_config))
    assert entry is not None
    assert entry.shastra_name == "वसुनन्दि श्रावकाचार"


def test_alternate_name_legacy_string():
    """14A.3: loader must accept legacy single-string form."""
    norm_config = _make_norm_config([])
    entries = [
        {"shastra_name": "TestShastram", "alternate_name": "TestAlt", "format": ""},
    ]
    reg = _make_registry(entries, norm_config)
    entry, method = reg.lookup("TestAlt")
    assert entry is not None
    assert method == "alternate_name"
