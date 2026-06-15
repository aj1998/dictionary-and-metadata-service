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
