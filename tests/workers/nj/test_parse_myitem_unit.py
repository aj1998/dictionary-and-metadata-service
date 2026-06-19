from __future__ import annotations

from workers.ingestion.nj.parse_myitem import (
    _split_leading_adhikaar,
    parse_myitem,
)


def test_parse_myitem_extracts_primary_and_secondary(nj_cfg):
    js = """
mySel=$('select#select-native-0')
$optgrp=$('<optgroup label="﻿जीव अधिकार"')
$optgrp.append("<option value='001.html'><b>001</b> - ﻿सिद्धों को नमस्कार</option>")
$optgrp.append("<option value='009-010.html'><b>009-010</b> - ﻿मिश्र पृष्ठ</option>")
mySel=$('select#select-native-1')
$optgrp=$('<optgroup label="﻿जीव अधिकार"')
$optgrp.append("<option value='011.html'><b>011</b> - ﻿जयसेन कलश</option>")
""".strip()
    (nj_cfg.input.resolved_html_dir / nj_cfg.input.my_item_js).write_text(js, encoding="utf-8")

    primary, secondary = parse_myitem(nj_cfg)
    assert set(primary.keys()) == {"001.html", "009-010.html"}
    assert primary["001.html"].gatha_number == "001"
    assert primary["001.html"].heading_hi == "सिद्धों को नमस्कार"
    assert primary["001.html"].adhikaar_hi == "जीव अधिकार"
    assert primary["001.html"].adhikaar_number == 1
    assert set(secondary.keys()) == {"011.html"}
    assert secondary["011.html"].gatha_number == "011"
    assert secondary["011.html"].adhikaar_number == 1


def test_parse_myitem_secondary_absent_when_selector_not_configured(nj_cfg):
    js = """
mySel=$('select#select-native-0')
$optgrp=$('<optgroup label="अधिकार"')
$optgrp.append("<option value='001.html'><b>001</b> - शीर्षक</option>")
mySel=$('select#select-native-1')
$optgrp=$('<optgroup label="अधिकार"')
$optgrp.append("<option value='011.html'><b>011</b> - शीर्षक</option>")
""".strip()
    (nj_cfg.input.resolved_html_dir / nj_cfg.input.my_item_js).write_text(js, encoding="utf-8")
    nj_cfg.selectors.secondary_teeka_select = None

    primary, secondary = parse_myitem(nj_cfg)
    assert set(primary.keys()) == {"001.html"}
    assert primary["001.html"].adhikaar_number == 1
    assert secondary == {}


def test_parse_myitem_assigns_incrementing_adhikaar_number(nj_cfg):
    js = """
mySel=$('select#select-native-0')
$optgrp=$('<optgroup label="प्रथम अधिकार"')
$optgrp.append("<option value='001.html'><b>001</b> - शीर्षक 1</option>")
$optgrp=$('<optgroup label="द्वितीय अधिकार"')
$optgrp.append("<option value='012.html'><b>012</b> - शीर्षक 2</option>")
""".strip()
    (nj_cfg.input.resolved_html_dir / nj_cfg.input.my_item_js).write_text(js, encoding="utf-8")
    primary, _ = parse_myitem(nj_cfg)
    assert primary["001.html"].adhikaar_number == 1
    assert primary["012.html"].adhikaar_number == 2


# --- _split_leading_adhikaar unit tests ---

def test_split_leading_adhikaar_2part():
    assert _split_leading_adhikaar("1-001") == (1, "001")


def test_split_leading_adhikaar_3part():
    assert _split_leading_adhikaar("1-019-021") == (1, "019-021")


def test_split_leading_adhikaar_no_prefix():
    assert _split_leading_adhikaar("019") == (None, "019")


def test_split_leading_adhikaar_single_digit_trailing():
    # "2-001" → adhikaar 2, gatha "001"
    assert _split_leading_adhikaar("2-001") == (2, "001")


# --- explicit adhikaar match (compound optgroup shastras e.g. तत्त्वार्थसूत्र) ---

def test_split_leading_adhikaar_explicit_equal_width_match():
    # "01-01" with the optgroup adhikaar ordinal = 1 → strip the zero-padded
    # adhyaaya prefix even though prefix/trailing are the same digit width.
    assert _split_leading_adhikaar("01-01", 1) == (1, "01")
    assert _split_leading_adhikaar("01-32", 1) == (1, "32")
    assert _split_leading_adhikaar("10-05", 10) == (10, "05")


def test_split_leading_adhikaar_explicit_mismatch_falls_back_to_heuristic():
    # When the prefix doesn't match the expected adhikaar, the width heuristic
    # still governs — "009-010" stays an unsplit range (prevents the samaysaar
    # range regression even if an expected_adhikaar is passed).
    assert _split_leading_adhikaar("009-010", 2) == (None, "009-010")
    # But a genuine narrower prefix still splits via the heuristic.
    assert _split_leading_adhikaar("1-001", 5) == (1, "001")


# --- bare mySel.append (no optgroup) ---

def test_bare_mysel_append_no_optgroup(nj_cfg):
    js = """
mySel=$('select#select-native-0')
mySel.append("<option value='1-001.html'><b>1-001</b> - ﻿आत्मस्वरूप</option>")
mySel.append("<option value='1-019-021.html'><b>1-019-021</b> - ﻿संयुक्त गाथा</option>")
mySel.append("<option value='2-001.html'><b>2-001</b> - ﻿मोक्ष प्रारंभ</option>")
""".strip()
    (nj_cfg.input.resolved_html_dir / nj_cfg.input.my_item_js).write_text(js, encoding="utf-8")

    primary, _ = parse_myitem(nj_cfg)
    assert set(primary.keys()) == {"1-001.html", "1-019-021.html", "2-001.html"}

    e1 = primary["1-001.html"]
    assert e1.gatha_number == "001"
    assert e1.adhikaar_number == 1
    assert e1.heading_hi == "आत्मस्वरूप"

    e2 = primary["1-019-021.html"]
    assert e2.gatha_number == "019-021"
    assert e2.adhikaar_number == 1

    e3 = primary["2-001.html"]
    assert e3.gatha_number == "001"
    assert e3.adhikaar_number == 2


# --- compound optgroup shastra (तत्त्वार्थसूत्र: अध्याय-sutra `AA-SS` values) ---

def test_compound_optgroup_strips_zero_padded_adhyaaya_prefix(nj_cfg):
    """तत्त्वार्थसूत्र encodes each sutra as `01-02` (अध्याय 1, सूत्र 02) under an
    optgroup. The equal-width adhyaaya prefix must be stripped so the canonical
    gatha number is the bare sutra and `01-02` is NOT misread as a range 1→2.
    Regression for the flat-NK / mixed-राजवार्तिक bug.
    """
    nj_cfg.shastra.natural_key = "तत्त्वार्थसूत्र"  # compound in shastra.json
    js = """
mySel=$('select#select-native-0')
$optgrp=$('<optgroup label="﻿1-प्रथम-अध्याय"')
$optgrp.append("<option value='01-01.html'><b>01-01</b> - ﻿मोक्ष का उपाय</option>")
$optgrp.append("<option value='01-02.html'><b>01-02</b> - ﻿सम्यग्दर्शन का लक्षण</option>")
$optgrp=$('<optgroup label="﻿2-द्वितीय-अध्याय"')
$optgrp.append("<option value='02-13.html'><b>02-13</b> - ﻿ज्योतिष देव</option>")
""".strip()
    (nj_cfg.input.resolved_html_dir / nj_cfg.input.my_item_js).write_text(js, encoding="utf-8")

    primary, _ = parse_myitem(nj_cfg)
    assert primary["01-01.html"].gatha_number == "01"
    assert primary["01-01.html"].adhikaar_number == 1
    # The critical case: 01-02 must collapse to sutra "02", not a "01-02" range.
    assert primary["01-02.html"].gatha_number == "02"
    assert primary["01-02.html"].adhikaar_number == 1
    assert primary["02-13.html"].gatha_number == "13"
    assert primary["02-13.html"].adhikaar_number == 2


def test_non_compound_optgroup_keeps_equal_width_range(nj_cfg):
    """Guard: for a non-compound shastra (samaysaar), an equal-width hyphenated
    value like `009-010` is a genuine gatha range and must NOT be stripped even
    though it sits under an optgroup ordinal.
    """
    # nj_cfg default natural_key is samaysaar (non-compound).
    js = """
mySel=$('select#select-native-0')
$optgrp=$('<optgroup label="﻿जीव अधिकार"')
$optgrp.append("<option value='009-010.html'><b>009-010</b> - ﻿मिश्र पृष्ठ</option>")
""".strip()
    (nj_cfg.input.resolved_html_dir / nj_cfg.input.my_item_js).write_text(js, encoding="utf-8")

    primary, _ = parse_myitem(nj_cfg)
    assert primary["009-010.html"].gatha_number == "009-010"
