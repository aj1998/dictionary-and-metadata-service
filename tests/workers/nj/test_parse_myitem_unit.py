from __future__ import annotations

from workers.ingestion.nj.parse_myitem import parse_myitem


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
