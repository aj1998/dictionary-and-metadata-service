from __future__ import annotations

from workers.ingestion.nj.classify_pages import classify_page, preceding_primary_gatha
from workers.ingestion.nj.parse_myitem import GathaIndexEntry


def _entry(fname: str, num: str) -> GathaIndexEntry:
    return GathaIndexEntry(
        html_filename=fname,
        gatha_number=num,
        heading_hi="h",
        adhikaar_hi="a",
    )


def test_classify_page_variants():
    primary = {"001.html": _entry("001.html", "001")}
    secondary = {"011.html": _entry("011.html", "011")}
    assert classify_page("001.html", primary, secondary) == "primary_gatha"
    assert classify_page("011.html", primary, secondary) == "secondary_kalash"
    assert classify_page("999.html", primary, secondary) == "skip"


def test_preceding_primary_gatha():
    primary = {
        "001.html": _entry("001.html", "001"),
        "009-010.html": _entry("009-010.html", "009-010"),
    }
    files = ["0000.html", "001.html", "011.html", "009-010.html", "012.html"]
    assert preceding_primary_gatha("011.html", files, primary) == "001"
    assert preceding_primary_gatha("012.html", files, primary) == "010"
    assert preceding_primary_gatha("0000.html", files, primary) is None
    assert preceding_primary_gatha("absent.html", files, primary) is None
