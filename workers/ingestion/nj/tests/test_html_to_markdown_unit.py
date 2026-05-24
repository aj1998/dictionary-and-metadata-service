from __future__ import annotations

from bs4 import BeautifulSoup

from workers.ingestion.nj.html_to_markdown import node_to_markdown


def test_markdown_formats_basic_tags():
    soup = BeautifulSoup(
        "<div><b>Bold</b><br/><i>Italic</i><hr/><span class='notes'>कलश-१</span></div>",
        "lxml",
    )
    out = node_to_markdown(soup.div)
    assert "**Bold**" in out
    assert "*Italic*" in out
    assert "\n---\n" in out
    assert "*(कलश-१)*" in out


def test_markdown_font_color_behavior():
    soup = BeautifulSoup(
        "<div><font color='red'>x</font><font color='blue'>y</font></div>",
        "lxml",
    )
    out = node_to_markdown(soup.div)
    assert "x" not in out
    assert '<span style="color:blue">y</span>' in out


def test_markdown_list_and_kalash_wrapper():
    soup = BeautifulSoup(
        "<div><ul><li>एक</li><li>दो</li></ul><b><div class='gadya'>गद्य</div></b></div>",
        "lxml",
    )
    out = node_to_markdown(soup.div)
    assert "- एक" in out
    assert "- दो" in out
    assert "गद्य" in out
