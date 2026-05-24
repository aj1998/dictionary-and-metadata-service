from __future__ import annotations

from workers.ingestion.nj.orchestrator import parse_shastra


def _write_html(path, body: str) -> None:
    path.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")


def test_orchestrator_batch_and_preceding_resolution(nj_cfg):
    js = """
mySel=$('select#select-native-0')
$optgrp=$('<optgroup label="अधिकार">')
$optgrp.append("<option value='001.html'><b>001</b> - शीर्षक 1</option>")
$optgrp.append("<option value='003.html'><b>003</b> - शीर्षक 3</option>")
mySel=$('select#select-native-1')
$optgrp=$('<optgroup label="अधिकार">')
$optgrp.append("<option value='002.html'><b>002</b> - शीर्षक 2</option>")
""".strip()
    root = nj_cfg.input.resolved_html_dir
    (root / "myItem.js").write_text(js, encoding="utf-8")
    _write_html(root / "0000_intro.html", "<div>skip</div>")
    _write_html(root / "001.html", """
<div class="title" id="gatha-001"><span><a>h</a></span></div>
<div class="gatha">g1</div><div id="teeka0"><b><font color="darkgreen">अमृतचंद्राचार्य</font></b></div>
""")
    _write_html(root / "002.html", """
<div class="title" id="gatha-002"><span><a>k</a></span></div>
<div class="gatha">k2</div>
<div id="teeka0"><div class="steeka" id="steeka0">san</div><div>bh</div></div>
""")
    _write_html(root / "003.html", """
<div class="title" id="gatha-003"><span><a>h3</a></span></div>
<div class="gatha">g3</div><div id="teeka0"><b><font color="darkgreen">अमृतचंद्राचार्य</font></b></div>
""")

    res = parse_shastra(nj_cfg, batch_offset=1, batch_limit=1)
    assert res.total_html_files_processed == 1
    assert len(res.gathas) == 0
    assert len(res.secondary_kalashes) == 1
    assert res.secondary_kalashes[0].kalash_number == "002"
    assert res.secondary_kalashes[0].preceding_primary_gatha_number == "001"


def test_orchestrator_collects_skip_warnings(nj_cfg):
    js = """
mySel=$('select#select-native-0')
$optgrp=$('<optgroup label="अधिकार">')
$optgrp.append("<option value='001.html'><b>001</b> - शीर्षक 1</option>")
""".strip()
    root = nj_cfg.input.resolved_html_dir
    (root / "myItem.js").write_text(js, encoding="utf-8")
    _write_html(root / "001.html", """
<div class="title" id="gatha-001"><span><a>h</a></span></div>
<div class="gatha">g1</div><div id="teeka0"><b><font color="darkgreen">अमृतचंद्राचार्य</font></b></div>
""")
    _write_html(root / "zzz.html", "<div>unknown</div>")
    res = parse_shastra(nj_cfg)
    assert any("unclassified page: zzz.html" == w for w in res.warnings)


def test_orchestrator_rejects_negative_batch(nj_cfg):
    root = nj_cfg.input.resolved_html_dir
    (root / "myItem.js").write_text("", encoding="utf-8")
    try:
        parse_shastra(nj_cfg, batch_offset=-1)
        assert False, "expected ValueError for negative offset"
    except ValueError as exc:
        assert "batch_offset" in str(exc)
    try:
        parse_shastra(nj_cfg, batch_limit=-1)
        assert False, "expected ValueError for negative limit"
    except ValueError as exc:
        assert "batch_limit" in str(exc)
