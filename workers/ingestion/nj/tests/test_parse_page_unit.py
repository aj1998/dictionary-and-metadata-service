from __future__ import annotations

from bs4 import BeautifulSoup

from workers.ingestion.nj.parse_myitem import GathaIndexEntry
from workers.ingestion.nj.parse_page import parse_primary_page, parse_secondary_kalash_page


def _idx(fname: str, num: str, adhikaar_number: int | None = None) -> GathaIndexEntry:
    return GathaIndexEntry(
        html_filename=fname,
        gatha_number=num,
        heading_hi="शीर्षक",
        adhikaar_hi="अधिकार",
        adhikaar_number=adhikaar_number,
    )


def test_parse_primary_page_single_and_anyavartha(nj_cfg):
    html = """
<div class="title" id="gatha-001"><span><a>शीर्षक</a></span></div>
<div class="gatha">वंदित्तु सव्वसिद्धे ॥ 1 ॥</div>
<div class="gathaS">वंदित्वा सर्वसिद्धान् ॥ 1 ॥</div>
<div class="gadya">चरण 1</div>
<div class="paragraph">अन्वयार्थ : <span><font color="darkRed">[वंदित्तु]</font></span> नमस्कार</div>
<div id="teeka0">
  <div class="steeka" id="steeka0">अथ सूत्रावतार<hr class="type_7"/></div>
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
  <div>भावार्थ</div>
</div>
<div id="teeka1"><div class="steeka" id="steeka1">जयसेन<hr class="type_7"/></div></div>
""".strip()
    soup = BeautifulSoup(html, "lxml")
    gathas, delta = parse_primary_page(soup, _idx("001.html", "001", adhikaar_number=3), nj_cfg, global_kalash_start=1)
    assert len(gathas) == 1
    g = gathas[0]
    assert g.page_html_id == "001"
    assert g.adhikaar_number == 3
    assert g.prakrit_text == "वंदित्तु सव्वसिद्धे"
    assert g.sanskrit_text == "वंदित्वा सर्वसिद्धान्"
    assert g.anyavartha and g.anyavartha.full_anyavaarth == "नमस्कार"
    assert g.anyavartha.tagged_terms[0].source_word == "वंदित्तु"
    assert g.anyavartha.tagged_terms[0].meaning == "नमस्कार"
    assert g.primary_teeka is not None
    assert g.secondary_teeka is not None
    assert delta == 0


def test_parse_primary_page_preserves_newlines_in_sanskrit_and_hindi(nj_cfg):
    html = """
<div class="title" id="gatha-011"><span><a>शीर्षक</a></span></div>
<div class="gatha">प्राकृत पंक्ति 1<br/>प्राकृत पंक्ति 2</div>
<div class="gathaS">प्रथम पंक्ति<br/>द्वितीय पंक्ति ॥ 11 ॥</div>
<div class="gadya">हिंदी पंक्ति 1<br/>हिंदी पंक्ति 2</div>
<div id="teeka0"><b><font color="darkgreen">अमृतचंद्राचार्य</font></b></div>
""".strip()
    soup = BeautifulSoup(html, "lxml")
    gathas, _ = parse_primary_page(soup, _idx("011.html", "011"), nj_cfg, global_kalash_start=1)
    g = gathas[0]
    assert g.prakrit_text == "प्राकृत पंक्ति 1\nप्राकृत पंक्ति 2"
    assert g.sanskrit_text == "प्रथम पंक्ति\nद्वितीय पंक्ति"
    assert g.hindi_chhands[0].text_hi == "हिंदी पंक्ति 1\nहिंदी पंक्ति 2"


def test_parse_primary_page_multi_gatha_expansion(nj_cfg):
    html = """
<div class="title" id="gatha-009-010"><span><a>शीर्षक</a></span></div>
<div class="gatha">पहला भाग ॥9॥ दूसरा भाग</div>
<div class="gathaS">प्रथम भाग ॥९॥ द्वितीय भाग</div>
<div class="gadya">हिंदी एक ॥९॥ हिंदी दो ॥१०॥</div>
<div id="teeka0"><b><font color="darkgreen">अमृतचंद्राचार्य</font></b></div>
""".strip()
    soup = BeautifulSoup(html, "lxml")
    gathas, _ = parse_primary_page(soup, _idx("009-010.html", "009-010"), nj_cfg, global_kalash_start=1)
    assert [g.gatha_number for g in gathas] == ["009", "010"]
    assert all(g.is_combined_page for g in gathas)
    assert gathas[0].related_gatha_numbers == ["010"]
    assert gathas[1].related_gatha_numbers == ["009"]
    assert gathas[0].prakrit_text == "पहला भाग ॥9॥"
    assert gathas[1].prakrit_text == "दूसरा भाग"
    assert gathas[0].sanskrit_text == "प्रथम भाग ॥९॥"
    assert gathas[1].sanskrit_text == "द्वितीय भाग"
    assert gathas[0].hindi_chhands[0].text_hi == "हिंदी एक ॥९॥"
    assert gathas[1].hindi_chhands[0].text_hi == "हिंदी दो ॥१०॥"


def test_parse_secondary_kalash_page(nj_cfg):
    html = """
<div class="title" id="gatha-012"><span><a>जयसेन शीर्षक</a></span></div>
<div class="gatha">प्राकृत</div>
<div class="paragraph">अन्वयार्थ : <span><font color="darkRed">[धुव]</font></span> ध्रुव</div>
<div id="teeka0"><div class="steeka" id="steeka0">संस्कृतांश</div><div>हिंदी</div></div>
""".strip()
    soup = BeautifulSoup(html, "lxml")
    kal = parse_secondary_kalash_page(soup, "012.html", "010", nj_cfg)
    assert kal.kalash_number == "012"
    assert kal.heading_hi == "जयसेन शीर्षक"
    assert kal.preceding_primary_gatha_number == "010"
    assert kal.anyavartha and kal.anyavartha.tagged_terms[0].meaning == "ध्रुव"


def test_anyavartha_full_text_removes_tagged_source_words(nj_cfg):
    html = """
<div class="title" id="gatha-013"><span><a>शीर्षक</a></span></div>
<div class="gatha">प्राकृत</div>
<div class="paragraph">
  अन्वयार्थ :
  <span><font color="darkRed">[वंदित्तु]</font></span> नमस्कार,
  <span><font color="darkRed">[सव्व]</font></span> सबको प्रणाम
</div>
<div id="teeka0"><b><font color="darkgreen">अमृतचंद्राचार्य</font></b></div>
""".strip()
    soup = BeautifulSoup(html, "lxml")
    gathas, _ = parse_primary_page(soup, _idx("013.html", "013"), nj_cfg, global_kalash_start=1)
    g = gathas[0]
    assert g.anyavartha is not None
    assert g.anyavartha.full_anyavaarth == "नमस्कार, सबको प्रणाम"
    assert [t.source_word for t in g.anyavartha.tagged_terms] == ["वंदित्तु", "सव्व"]
