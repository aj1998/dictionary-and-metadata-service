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
        entry = ShastraEntry(
            shastra_name=item["shastra_name"],
            alternate_name=item.get("alternate_name"),
            short_form=item.get("short_form", ""),
            format_str=item.get("format", ""),
            format_groups=parse_format_string(item.get("format", "")),
        )
        registry.entries.append(entry)
        registry._by_primary[_normalise(entry.shastra_name, norm_config)] = entry
        if entry.alternate_name:
            registry._by_alternate[_normalise(entry.alternate_name, norm_config)] = entry
        if entry.short_form:
            registry._by_short_form[_normalise(entry.short_form, norm_config)] = entry
    return registry


FIXTURE_ENTRIES = [
    {"shastra_name": "धवला", "short_form": "ध", "format": "पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा"},
    {"shastra_name": "प्रवचनसार", "short_form": "प्र.सा./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "पंचास्तिकाय", "short_form": "पं.का./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "गोम्मटसार जीवकाण्ड/मूल", "alternate_name": "गोम्मटसार जीवकांड/मूल",
     "short_form": "गो.जी./मू.", "format": "गाथा/पृष्ठ"},
    {"shastra_name": "मूलाचार", "short_form": "मूला.", "format": "गाथा"},
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
        {"shastra_name": "X", "alternate_name": "Y", "format": ""},
        {"shastra_name": "Y", "format": ""},
    ]
    reg = _make_registry(entries, _make_norm_config([]))
    entry, method = reg.lookup("Y")
    # primary match for "Y" entry
    assert method == "shastra_name"
    assert entry.shastra_name == "Y"
