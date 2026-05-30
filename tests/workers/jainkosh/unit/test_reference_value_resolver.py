"""Unit tests for resolve_fields() and value expansion helpers."""

import pytest

from workers.ingestion.jainkosh.config import ReferenceNeedsManualMatchConfig
from workers.ingestion.jainkosh.parse_reference import (
    _coerce_value,
    _expand_value,
    _expand_resolved_fields,
    parse_format_string,
    resolve_fields,
)
from workers.ingestion.jainkosh.models import ResolvedField


@pytest.fixture
def default_config():
    # 14A.2: on_missing_fields now defaults to True
    return ReferenceNeedsManualMatchConfig(on_extra_groups=True, on_missing_fields=True)


@pytest.fixture
def lenient_config():
    return ReferenceNeedsManualMatchConfig(on_extra_groups=False, on_missing_fields=False)


@pytest.fixture
def strict_config():
    return ReferenceNeedsManualMatchConfig(on_extra_groups=True, on_missing_fields=True)


@pytest.fixture
def missing_ok_config():
    # on_extra_groups=True but on_missing_fields=False (old default behaviour)
    return ReferenceNeedsManualMatchConfig(on_extra_groups=True, on_missing_fields=False)


def _resolve(fmt, numeric_clean, config):
    groups = parse_format_string(fmt)
    fields, needs_manual, _consumed = resolve_fields(numeric_clean, groups, config)
    return fields, needs_manual


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


def test_missing_fields_not_flagged_with_missing_ok(missing_ok_config):
    # on_missing_fields=False: running out of value groups is OK
    fields, needs_manual = _resolve("अधिकार/श्लोक/पृष्ठ", "1", missing_ok_config)
    assert needs_manual is False
    assert fields[0].field == "अधिकार"
    assert fields[0].value == 1


def test_missing_fields_strict_triggers_needs_manual(strict_config):
    fields, needs_manual = _resolve("अधिकार/श्लोक/पृष्ठ", "1", strict_config)
    assert needs_manual is True
    assert fields[0].field == "अधिकार"
    assert fields[0].value == 1


def test_range_preserved_with_comma_separator(missing_ok_config):
    fields, needs_manual = _resolve("पुस्तक,भाग/पृष्ठ", "1,13-14/84", missing_ok_config)
    assert needs_manual is False
    assert [(f.field, f.value) for f in fields] == [
        ("पुस्तक", 1), ("भाग", "13-14"), ("पृष्ठ", 84),
    ]


def test_dash_separator_splits(missing_ok_config):
    fields, needs_manual = _resolve("मुख्याधिकार-प्रकरण/श्लोक", "3-7/5", missing_ok_config)
    assert needs_manual is False
    assert [(f.field, f.value) for f in fields] == [
        ("मुख्याधिकार", 3), ("प्रकरण", 7), ("श्लोक", 5),
    ]


def test_empty_numeric_no_required(default_config):
    fields, needs_manual = _resolve("§गाथा", "", default_config)
    assert needs_manual is False
    assert fields == []


def test_empty_numeric_with_required_strict(strict_config):
    # on_missing_fields=True: empty numeric with required group → needs_manual
    fields, needs_manual = _resolve("गाथा", "", strict_config)
    assert needs_manual is True
    assert fields == []


def test_empty_numeric_with_required_missing_ok(missing_ok_config):
    # on_missing_fields=False: empty numeric is OK
    fields, needs_manual = _resolve("गाथा", "", missing_ok_config)
    assert needs_manual is False
    assert fields == []


# ---------------------------------------------------------------------------
# 14A.5: _coerce_value extracts leading digits
# ---------------------------------------------------------------------------

def test_value_coercion_pure_int():
    assert _coerce_value("42") == 42
    assert isinstance(_coerce_value("42"), int)


def test_value_coercion_leading_digits():
    # 14A.5: extract leading digit run
    assert _coerce_value("309परउद्धृत") == 309
    assert isinstance(_coerce_value("309परउद्धृत"), int)


def test_value_coercion_leading_digits_42abc():
    assert _coerce_value("42abc") == 42


def test_value_coercion_non_numeric_returns_none():
    # No leading digits → None
    assert _coerce_value("abc") is None
    assert _coerce_value("परउद्धृत") is None


def test_value_coercion_range_returns_leading():
    # "13-14" has leading "13"; called directly returns 13
    # (In _assign_group, range/list strings are kept as-is BEFORE calling _coerce_value)
    assert _coerce_value("13-14") == 13


# ---------------------------------------------------------------------------
# 14A.4: _expand_value
# ---------------------------------------------------------------------------

def test_expand_pure_int():
    assert _expand_value(42) == [42]


def test_expand_range_string():
    assert _expand_value("95-96") == [95, 96]


def test_expand_list_string():
    assert _expand_value("8,86") == [8, 86]


def test_expand_range_and_list():
    assert _expand_value("1-3,39") == [1, 2, 3, 39]


def test_expand_overflow_returns_none():
    # b - a > 50 → None
    assert _expand_value("1-100") is None


def test_expand_non_numeric_returns_none():
    assert _expand_value("abc") is None


# ---------------------------------------------------------------------------
# 14A.4: _expand_resolved_fields
# ---------------------------------------------------------------------------

def test_expand_resolved_fields_single_int():
    fields = [ResolvedField(field="गाथा", value=42)]
    result = _expand_resolved_fields(fields)
    assert result == [[ResolvedField(field="गाथा", value=42)]]


def test_expand_resolved_fields_range():
    fields = [ResolvedField(field="गाथा", value="95-96")]
    result = _expand_resolved_fields(fields)
    assert result is not None
    assert len(result) == 2
    values = sorted(r[0].value for r in result)
    assert values == [95, 96]


def test_expand_resolved_fields_cartesian_product():
    fields = [
        ResolvedField(field="गाथा", value="1-2"),
        ResolvedField(field="पृष्ठ", value="5,6"),
    ]
    result = _expand_resolved_fields(fields)
    assert result is not None
    assert len(result) == 4
    combos = sorted((r[0].value, r[1].value) for r in result)
    assert combos == [(1, 5), (1, 6), (2, 5), (2, 6)]


def test_expand_resolved_fields_overflow():
    # 10 * 10 = 100 > 50 → None
    fields = [
        ResolvedField(field="a", value="1-10"),
        ResolvedField(field="b", value="1-10"),
    ]
    assert _expand_resolved_fields(fields) is None


# ---------------------------------------------------------------------------
# Keyword trigger groups
# ---------------------------------------------------------------------------

def test_keyword_group_matches_gatha(default_config):
    """Keyword group {श्लोक/गाथा}गाथा resolves when value starts with 'गाथा'."""
    groups = parse_format_string("पुस्तक/खण्ड,भाग,धवलासूत्र/{श्लोक/गाथा}गाथा/पृष्ठ")
    fields, needs_manual, consumed = resolve_fields("3/1,2,1/गाथा4/6", groups, default_config)
    assert needs_manual is False
    assert consumed == {"गाथा"}
    assert [(f.field, f.value) for f in fields] == [
        ("पुस्तक", 3), ("खण्ड", 1), ("भाग", 2), ("धवलासूत्र", 1), ("गाथा", 4), ("पृष्ठ", 6),
    ]


def test_keyword_group_matches_shloka(default_config):
    """Keyword group {श्लोक/गाथा}गाथा resolves when value starts with 'श्लोक'."""
    groups = parse_format_string("पुस्तक/खण्ड,भाग,धवलासूत्र/{श्लोक/गाथा}गाथा/पृष्ठ")
    fields, needs_manual, consumed = resolve_fields("3/1,2,1/श्लोक5/6", groups, default_config)
    assert needs_manual is False
    assert consumed == {"श्लोक"}
    assert [(f.field, f.value) for f in fields] == [
        ("पुस्तक", 3), ("खण्ड", 1), ("भाग", 2), ("धवलासूत्र", 1), ("गाथा", 5), ("पृष्ठ", 6),
    ]


def test_keyword_group_no_match_fails(default_config):
    """Keyword group fails (needs_manual) when no trigger keyword is found."""
    groups = parse_format_string("पुस्तक/{श्लोक/गाथा}गाथा/पृष्ठ")
    fields, needs_manual, consumed = resolve_fields("3/183/11", groups, default_config)
    assert needs_manual is True
    assert consumed == set()


def test_keyword_group_consumed_keywords_empty_for_regular_format(default_config):
    """Regular (non-keyword-group) formats return empty consumed set."""
    groups = parse_format_string("पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा")
    fields, needs_manual, consumed = resolve_fields("1/1,1,1/84/1", groups, default_config)
    assert needs_manual is False
    assert consumed == set()
