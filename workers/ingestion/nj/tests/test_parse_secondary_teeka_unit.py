from __future__ import annotations

from bs4 import BeautifulSoup

from workers.ingestion.nj.parse_secondary_teeka import parse_secondary_teeka


def test_parse_secondary_teeka_regular_page(nj_cfg):
    html = """
<div id="teeka1">
  <div class="steeka" id="steeka1">जयसेन संस्कृत <hr class="type_7"/> बाद का भाग</div>
  <b><font color="darkgreen">जयसेनाचार्य</font></b>
  <div>हिंदी भावार्थ</div>
</div>
""".strip()
    teeka = BeautifulSoup(html, "lxml").select_one("div#teeka1")
    assert teeka is not None
    parsed = parse_secondary_teeka(teeka, nj_cfg)
    assert parsed.gatha_teeka_san == "जयसेन संस्कृत"
    assert parsed.gatha_teeka_bhaavarth_md == "हिंदी भावार्थ"


def test_parse_secondary_teeka_secondary_only_layout(nj_cfg):
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0">संस्कृतांश</div>
  <div>भावार्थ पंक्ति</div>
</div>
""".strip()
    teeka = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka is not None
    parsed = parse_secondary_teeka(teeka, nj_cfg)
    assert parsed.gatha_teeka_san == "संस्कृतांश"
    assert parsed.gatha_teeka_bhaavarth_md == "भावार्थ पंक्ति"
