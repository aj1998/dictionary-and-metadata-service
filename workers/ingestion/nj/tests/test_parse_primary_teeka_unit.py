from __future__ import annotations

from bs4 import BeautifulSoup

from workers.ingestion.nj.parse_primary_teeka import parse_primary_teeka


def test_parse_primary_teeka_extracts_kalash_and_bhaavarth(nj_cfg):
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0">
    अथ सूत्रावतार
    <font color="DarkSlateGray">(कलश-अनुष्टुभ्)</font>
    नम: समयसाराय
    <font color="DarkSlateGray">(कलश-मालिनी)</font>
    वचनम्
    <hr class="type_7"/>
  </div>
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
  <b><div class="gadya">हिंदी एक <span class="notes">(कलश-दोहा)</span></div></b>
  <b><font color="maroon">[शब्द१]</font> अर्थ १</b>
  <div>यह <font color="blue">भावार्थ</font> है</div>
  <b><div class="gadya">हिंदी दो <span class="notes">(कलश-रोला)</span></div></b>
  <b><font color="maroon">[शब्द२]</font> अर्थ २</b>
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka0 is not None

    parsed, delta = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=4)
    assert delta == 2
    assert parsed.gatha_teeka_san and "अथ सूत्रावतार" in parsed.gatha_teeka_san
    assert len(parsed.kalash_san) == 2
    assert parsed.kalash_san[0].global_kalash_index == 4
    assert parsed.kalash_san[1].global_kalash_index == 5
    assert parsed.kalash_san[0].text_san == "नम: समयसाराय"
    assert len(parsed.kalash_hindi) == 2
    assert parsed.kalash_hindi[0].chhand_type == "दोहा"
    assert parsed.kalash_hindi[1].chhand_type == "रोला"
    assert parsed.kalash_word_meanings[1][0].source_word == "शब्द१"
    assert parsed.kalash_word_meanings[2][0].meaning == "अर्थ २"
    assert parsed.gatha_teeka_bhaavarth_md and "भावार्थ" in parsed.gatha_teeka_bhaavarth_md


def test_parse_primary_teeka_handles_missing_steeka(nj_cfg):
    html = """
<div id="teeka0">
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
  <div>भावार्थ</div>
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka0 is not None
    parsed, delta = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=1)
    assert delta == 0
    assert parsed.kalash_san == []
    assert parsed.gatha_teeka_san is None
    assert parsed.gatha_teeka_bhaavarth_md == "भावार्थ"


def test_parse_primary_teeka_kalash_meaning_outside_b_tag(nj_cfg):
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0"><hr class="type_7"/></div>
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
  <b><div class="gadya">हिंदी एक <span class="notes">(कलश-दोहा)</span></div></b>
  <b><font color="maroon">[स्वानुभूत्या चकासते]</font></b> निज अनुभव से प्रकाशित
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka0 is not None

    parsed, _ = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=1)
    assert parsed.kalash_word_meanings[1][0].source_word == "स्वानुभूत्या चकासते"
    assert parsed.kalash_word_meanings[1][0].meaning == "निज अनुभव से प्रकाशित"


def test_parse_primary_teeka_separates_kalash_san_and_sutraavataar(nj_cfg):
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0">
    <b><div class="gadya">
      <font color="DarkSlateGray">(कलश-अनुष्टुभ्)</font><br/>नम: समयसाराय<br/>स्वानुभूत्या चकासते<br/>
      <font color="DarkSlateGray">(कलश-मालिनी)</font><br/>अनन्तधर्मणस्तत्त्वं पश्यंती प्रत्यगात्मन:<br/>
      <font color="DarkSlateGray">(कलश-मालिनी)</font><br/>मम परमविशुद्धि:
    </div></b>
    <br/><br/>अथ सूत्रावतार -<br/><br/>गद्यांश
    <hr class="type_7"/>
  </div>
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka0 is not None
    parsed, delta = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=1)
    assert delta == 3
    assert len(parsed.kalash_san) == 3
    assert parsed.kalash_san[0].text_san == "नम: समयसाराय\nस्वानुभूत्या चकासते"
    assert parsed.gatha_teeka_san and parsed.gatha_teeka_san.startswith("अथ सूत्रावतार -")


def test_parse_primary_teeka_bhaavarth_starts_after_kalash_wm_block(nj_cfg):
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0"><hr class="type_7"/></div>
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
  <b><div class="gadya">हिंदी एक <span class="notes">(कलश-दोहा)</span></div></b>
  <b>[<font color="maroon">परपरिणतिहेतोः मोहनाम्नःअनुभावात्</font>]</b> परपरिणति का कारण
  <span class="notes">(रागादि परिणामों)</span> की व्याप्ति द्वारा मैली<br/><br/>
  अब सूत्र प्रकट होता है -<br/><br/>
  यह पंचमगति <span class="notes">(सिद्धदशा)</span>
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka0 is not None
    parsed, _ = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=1)
    assert parsed.kalash_word_meanings[1][0].meaning.endswith("की व्याप्ति द्वारा मैली")
    assert parsed.gatha_teeka_bhaavarth_md is not None
    assert parsed.gatha_teeka_bhaavarth_md.startswith("अब सूत्र प्रकट होता है -")
