"""Unit tests for parse_format_string()."""

import pytest

from workers.ingestion.jainkosh.parse_reference import parse_format_string


def test_single_field():
    groups = parse_format_string("श्लोक")
    assert len(groups) == 1
    assert len(groups[0].fields) == 1
    assert groups[0].fields[0].name == "श्लोक"
    assert groups[0].fields[0].optional is False
    assert groups[0].sub_separator is None


def test_four_groups_comma_separator():
    groups = parse_format_string("पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा")
    assert len(groups) == 4
    assert groups[0].fields[0].name == "पुस्तक"
    assert groups[0].sub_separator is None
    assert len(groups[1].fields) == 3
    assert groups[1].sub_separator == ","
    assert [f.name for f in groups[1].fields] == ["खण्ड", "भाग", "सूत्र"]
    assert groups[2].fields[0].name == "पृष्ठ"
    assert groups[3].fields[0].name == "गाथा"


def test_optional_group():
    groups = parse_format_string("पुस्तक/§प्रकरण/पृष्ठ")
    assert len(groups) == 3
    assert groups[1].is_optional is True
    assert groups[1].fields[0].optional is True
    assert groups[1].fields[0].name == "प्रकरण"
    assert groups[0].is_optional is False
    assert groups[2].is_optional is False


def test_dash_separator():
    groups = parse_format_string("मुख्याधिकार-प्रकरण/श्लोक")
    assert len(groups) == 2
    assert len(groups[0].fields) == 2
    assert groups[0].sub_separator == "-"
    assert groups[0].fields[0].name == "मुख्याधिकार"
    assert groups[0].fields[1].name == "प्रकरण"
    assert groups[1].fields[0].name == "श्लोक"
    assert groups[1].sub_separator is None


def test_comma_and_optional():
    groups = parse_format_string("पुस्तक,भाग/§प्रकरण/पृष्ठ/पंक्ति")
    assert len(groups) == 4
    assert groups[0].sub_separator == ","
    assert len(groups[0].fields) == 2
    assert groups[1].is_optional is True
    assert groups[2].fields[0].name == "पृष्ठ"
    assert groups[3].fields[0].name == "पंक्ति"


def test_empty_format():
    groups = parse_format_string("")
    assert groups == []


def test_is_optional_property():
    groups = parse_format_string("§गाथा")
    assert groups[0].is_optional is True
    assert groups[0].has_required_field is False


def test_has_required_field():
    groups = parse_format_string("गाथा")
    assert groups[0].has_required_field is True
    assert groups[0].is_optional is False
