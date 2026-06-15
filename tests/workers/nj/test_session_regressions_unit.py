"""Regression tests for parser scenarios fixed during 2026-06-15 session.

Covers:
  1. No-kalash gatha: maroon `<b>[…]</b>` markers and bare `<b><div class=gadya>`
     verses must stay in bhaavarth, not be absorbed into phantom kalash entries
     (dravyasangrah 03.html–58.html pattern).
  2. `<font color=red>` content is preserved as `<span style="color:red">` and
     never stripped (dravyasangrah 57.html शंका pattern).
  3. `<b>` wrapping `<br><br>` paragraph breaks emits `**…**` per paragraph so
     the markdown renderer can close bold on each segment.
  4. `<span class=notes>` with internal `<br><br>` collapses whitespace so the
     `*((…))*` italic wrapper stays on one paragraph (dravyasangrah 18.html
     सिद्धोऽहं pattern).
  5. Bare `<span class=notes>(कलश)</span>` (no chhand suffix) on a Hindi
     gadya is recognised as a Hindi kalash (samaysaar 014.html pattern).
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from workers.ingestion.nj.html_to_markdown import node_to_markdown
from workers.ingestion.nj.parse_primary_teeka import parse_primary_teeka


# ---------- 1. No-kalash gatha: maroon markers and bare gadya stay in bhaavarth ----------


def test_no_kalash_maroon_markers_stay_in_bhaavarth(nj_cfg):
    """Dravyasangrah gatha 3: empty steeka0, post-steeka0 has `<b><font color=maroon>[…]</font></b>`
    prose markers plus a bare `<b><div class=gadya>verse</div></b>` (no notes-span).
    None of these should turn into phantom kalash entries.
    """
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0"></div>
  <br><br>
  <b>[<font color="maroon">तिक्काले चदुपाणा</font>]</b> तीन काल में जीव के चार प्राण होते हैं।
  <b>[<font color="maroon">ववहारा सो जीवो</font>]</b> व्यवहारनय से वह जीव है।
  <b><div class="gadya">वच्छक्खभवसारिच्छ सग्गणिरय पियराय ।<br>चुल्लय हंडिय पुण मडउणव दिटुंता जाय ॥</div></b>
  <ol><li><b>[<font color="maroon">वत्स</font>]</b> बछड़ा...</ol>
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka0 is not None

    parsed, delta = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=1)
    assert delta == 0
    assert parsed.kalash_san == []
    assert parsed.kalash_hindi == []
    assert parsed.kalash_word_meanings == {}

    bh = parsed.gatha_teeka_bhaavarth_md or ""
    # Prose marker, gadya verse, and ol-list item all flow into bhaavarth.
    assert "तिक्काले चदुपाणा" in bh
    assert "ववहारा सो जीवो" in bh
    assert "वच्छक्खभवसारिच्छ" in bh
    assert "चुल्लय हंडिय" in bh
    assert "वत्स" in bh


# ---------- 2. Red font color preserved ----------


def test_font_color_red_preserved_as_span():
    soup = BeautifulSoup(
        "<div><font color='red'>शंका – भगवान्!</font> "
        "<font color='darkGreen'>उत्तर –</font></div>",
        "lxml",
    )
    out = node_to_markdown(soup.div)
    assert '<span style="color:red">शंका – भगवान्!</span>' in out
    assert '<span style="color:darkGreen">उत्तर –</span>' in out


# ---------- 3. Bold across paragraph break splits into per-paragraph `**` pairs ----------


def test_bold_spanning_paragraph_breaks_splits_per_paragraph():
    """A `<b>` wrapping `<br><br>` would otherwise emit `**a\\n\\nb**`, which the
    markdown renderer can't bold (bold can't span paragraphs). The converter
    must emit `**a**\\n\\n**b**` so each piece bolds independently."""
    soup = BeautifulSoup(
        "<div><b>शंका – भगवान्?<br><br>उत्तर –</b></div>",
        "lxml",
    )
    out = node_to_markdown(soup.div)
    assert "**शंका – भगवान्?**" in out
    assert "**उत्तर –**" in out
    # No stray un-paired `**` with a `\n\n` between them.
    assert "**शंका – भगवान्?\n\nउत्तर –**" not in out


def test_bold_single_paragraph_still_single_pair():
    """No paragraph break → still one `**X**` wrap (unchanged behavior)."""
    soup = BeautifulSoup("<div><b>Bold</b></div>", "lxml")
    out = node_to_markdown(soup.div)
    assert "**Bold**" in out


# ---------- 4. Notes-span with internal `<br><br>` collapses whitespace ----------


def test_notes_span_collapses_internal_whitespace():
    """Source HTML occasionally embeds <br><br> inside <span class=notes>; the
    *((…))* wrapper must stay on a single paragraph so the UI italic-paren
    regex can match it."""
    soup = BeautifulSoup(
        "<div><span class='notes'>(सिद्धोऽहं ।<br><br>देहपमाणो ।।)</span></div>",
        "lxml",
    )
    out = node_to_markdown(soup.div)
    assert "*((सिद्धोऽहं । देहपमाणो ।।))*" in out
    # No `\n\n` inside the italic wrapper.
    assert "*((सिद्धोऽहं ।\n\n" not in out


def test_comment_span_collapses_internal_whitespace():
    soup = BeautifulSoup(
        "<div><span class='comment'>foo<br><br>bar</span></div>",
        "lxml",
    )
    out = node_to_markdown(soup.div)
    assert "*(foo bar)*" in out


# ---------- 5. Bare `(कलश)` notes-span recognised as Hindi kalash ----------


def test_bare_kalash_notes_recognised_as_hindi_kalash(nj_cfg):
    """Samaysaar 014.html: Hindi kalash gadyas carry `<span class=notes>(कलश)</span>`
    (no `-chhand` suffix). They must still be detected as kalash so that
    post-steeka0 `<b><div class=gadya>…(कलश)</div></b>` blocks pair with their
    Sanskrit kalashes instead of falling into bhaavarth."""
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0">
    <font color="DarkSlateGray">(कलश-मालिनी)</font>
    उभयनयविरोधध्वंसिनि ॥४॥
    <hr class="type_7"/>
  </div>
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
  <b><div class="gadya">उभयनयों में जो विरोध है <span class="notes">(कलश)</span> ॥४॥</div></b>
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    assert teeka0 is not None

    parsed, delta = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=4)
    assert delta == 1
    assert len(parsed.kalash_san) == 1
    assert len(parsed.kalash_hindi) == 1
    assert parsed.kalash_hindi[0].verse_number == "4"
    assert parsed.kalash_hindi[0].global_kalash_index == 4
    # Hindi kalash text must NOT leak into bhaavarth.
    assert parsed.gatha_teeka_bhaavarth_md in (None, "")


def test_kalash_with_chhand_suffix_still_recognised(nj_cfg):
    """Regression guard: the broader `(कलश)` matcher must still accept the
    canonical `(कलश-X)` form (samaysaar-style with chhand_type)."""
    html = """
<div id="teeka0">
  <div class="steeka" id="steeka0">
    <font color="DarkSlateGray">(कलश-दोहा)</font>
    संस्कृत वचनम् ॥१॥
    <hr class="type_7"/>
  </div>
  <b><font color="darkgreen">अमृतचंद्राचार्य</font></b>
  <b><div class="gadya">हिंदी एक <span class="notes">(कलश-दोहा)</span> ॥१॥</div></b>
</div>
""".strip()
    teeka0 = BeautifulSoup(html, "lxml").select_one("div#teeka0")
    parsed, _ = parse_primary_teeka(teeka0, nj_cfg, global_kalash_start=1)
    assert len(parsed.kalash_hindi) == 1
    assert parsed.kalash_hindi[0].chhand_type == "दोहा"
