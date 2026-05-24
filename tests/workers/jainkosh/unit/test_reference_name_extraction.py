"""Unit tests for split_name_and_numeric()."""

import pytest

from workers.ingestion.jainkosh.parse_reference import split_name_and_numeric


@pytest.mark.parametrize("text,expected_name,expected_numeric", [
    ("धवला 1/1,1,1/84/1", "धवला", "1/1,1,1/84/1"),
    ("धवला1/84", "धवला", "1/84"),
    ("पंचास्तिकाय / तात्पर्यवृत्ति/16/35/12", "पंचास्तिकाय / तात्पर्यवृत्ति", "16/35/12"),
    # space before § is preserved in numeric_raw; stripped later by numeric_clean
    ("कषायपाहुड़ 1/1,13-14/ §181/217/1", "कषायपाहुड़", "1/1,13-14/ §181/217/1"),
    ("धवला", "धवला", ""),
    ("प्रवचनसार मूल 1/5", "प्रवचनसार मूल", "1/5"),
])
def test_split_name_and_numeric(text, expected_name, expected_numeric):
    name, numeric = split_name_and_numeric(text)
    assert name == expected_name
    assert numeric == expected_numeric


def test_empty_string():
    name, numeric = split_name_and_numeric("")
    assert name == ""
    assert numeric == ""


def test_only_numeric():
    name, numeric = split_name_and_numeric("1/5/10")
    assert name == ""
    assert numeric == "1/5/10"
