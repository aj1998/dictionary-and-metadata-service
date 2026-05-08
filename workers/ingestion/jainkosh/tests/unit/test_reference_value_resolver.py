"""Unit tests for resolve_fields()."""

import pytest

from workers.ingestion.jainkosh.config import ReferenceNeedsManualMatchConfig
from workers.ingestion.jainkosh.parse_reference import parse_format_string, resolve_fields


@pytest.fixture
def default_config():
    return ReferenceNeedsManualMatchConfig(on_extra_groups=True, on_missing_fields=False)


@pytest.fixture
def strict_config():
    return ReferenceNeedsManualMatchConfig(on_extra_groups=True, on_missing_fields=True)


@pytest.fixture
def lenient_config():
    return ReferenceNeedsManualMatchConfig(on_extra_groups=False, on_missing_fields=False)


def _resolve(fmt, numeric_clean, config):
    groups = parse_format_string(fmt)
    return resolve_fields(numeric_clean, groups, config)


def test_full_match(default_config):
    fields, needs_manual = _resolve("पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा", "1/1,1,1/84/1", default_config)
    assert needs_manual is False
    assert len(fields) == 6
    assert [(f.field, f.value) for f in fields] == [
        ("पुस्तक", 1), ("खण्ड", 1), ("भाग", 1), ("सूत्र", 1), ("पृष्ठ", 84), ("गाथा", 1),
    ]


def test_optional_present(default_config):
    fields, needs_manual = _resolve("पुस्तक/§प्रकरण/पृष्ठ", "1/§5/10", default_config)
    assert needs_manual is False
    assert [(f.field, f.value) for f in fields] == [
        ("पुस्तक", 1), ("प्रकरण", 5), ("पृष्ठ", 10),
    ]


def test_optional_absent(default_config):
    fields, needs_manual = _resolve("पुस्तक/§प्रकरण/पृष्ठ", "1/10", default_config)
    assert needs_manual is False
    assert [(f.field, f.value) for f in fields] == [
        ("पुस्तक", 1), ("पृष्ठ", 10),
    ]


def test_extra_groups_triggers_needs_manual(default_config):
    fields, needs_manual = _resolve("अधिकार/श्लोक", "1/2/3/extra", default_config)
    assert needs_manual is True
    # raw resolved_fields before caller clears them — still have values here
    assert fields[0].value == 1
    assert fields[1].value == 2


def test_extra_groups_lenient(lenient_config):
    fields, needs_manual = _resolve("अधिकार/श्लोक", "1/2/3/extra", lenient_config)
    assert needs_manual is False


def test_missing_fields_default_not_flagged(default_config):
    # on_missing_fields=False (default): running out of value groups is OK
    fields, needs_manual = _resolve("अधिकार/श्लोक/पृष्ठ", "1", default_config)
    assert needs_manual is False
    assert fields[0].field == "अधिकार"
    assert fields[0].value == 1


def test_missing_fields_strict_triggers_needs_manual(strict_config):
    fields, needs_manual = _resolve("अधिकार/श्लोक/पृष्ठ", "1", strict_config)
    assert needs_manual is True
    assert fields[0].field == "अधिकार"
    assert fields[0].value == 1


def test_range_preserved_with_comma_separator(default_config):
    fields, needs_manual = _resolve("पुस्तक,भाग/पृष्ठ", "1,13-14/84", default_config)
    assert needs_manual is False
    assert [(f.field, f.value) for f in fields] == [
        ("पुस्तक", 1), ("भाग", "13-14"), ("पृष्ठ", 84),
    ]


def test_dash_separator_splits(default_config):
    fields, needs_manual = _resolve("मुख्याधिकार-प्रकरण/श्लोक", "3-7/5", default_config)
    assert needs_manual is False
    assert [(f.field, f.value) for f in fields] == [
        ("मुख्याधिकार", 3), ("प्रकरण", 7), ("श्लोक", 5),
    ]


def test_empty_numeric_no_required(default_config):
    fields, needs_manual = _resolve("§गाथा", "", default_config)
    assert needs_manual is False
    assert fields == []


def test_empty_numeric_with_required(default_config):
    # on_missing_fields=False means this is NOT flagged
    fields, needs_manual = _resolve("गाथा", "", default_config)
    assert needs_manual is False
    assert fields == []


def test_empty_numeric_with_required_strict(strict_config):
    fields, needs_manual = _resolve("गाथा", "", strict_config)
    assert needs_manual is True
    assert fields == []


def test_value_coercion_int():
    from workers.ingestion.jainkosh.parse_reference import _coerce_value
    assert _coerce_value("42") == 42
    assert isinstance(_coerce_value("42"), int)


def test_value_coercion_str():
    from workers.ingestion.jainkosh.parse_reference import _coerce_value
    assert _coerce_value("13-14") == "13-14"
    assert isinstance(_coerce_value("13-14"), str)
