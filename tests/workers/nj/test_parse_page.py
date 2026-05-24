"""Integration-style tests for NJ page parsing using local nikkyjain HTML files."""

from __future__ import annotations

import os

import pytest
from bs4 import BeautifulSoup

from workers.ingestion.nj.classify_pages import classify_page, preceding_primary_gatha
from workers.ingestion.nj.config import load_config_for_shastra
from workers.ingestion.nj.parse_myitem import parse_myitem
from workers.ingestion.nj.parse_page import parse_primary_page, parse_secondary_kalash_page

NJ_PATH = os.environ.get("NIKKYJAIN_LOCAL_PATH", "")
SKIP = not NJ_PATH


@pytest.fixture(scope="module")
def cfg():
    return load_config_for_shastra("samaysaar")


@pytest.fixture(scope="module")
def indexes(cfg):
    return parse_myitem(cfg)


@pytest.mark.skipif(SKIP, reason="NIKKYJAIN_LOCAL_PATH not set")
def test_myitem_counts(indexes):
    primary, secondary = indexes
    assert len(primary) >= 200
    assert len(secondary) >= 200


@pytest.mark.skipif(SKIP, reason="NIKKYJAIN_LOCAL_PATH not set")
def test_classify(indexes):
    primary, secondary = indexes
    assert classify_page("001.html", primary, secondary) == "primary_gatha"
    assert classify_page("012.html", primary, secondary) == "secondary_kalash"


@pytest.mark.skipif(SKIP, reason="NIKKYJAIN_LOCAL_PATH not set")
def test_parse_001(cfg, indexes):
    primary, _ = indexes
    html = (cfg.input.resolved_html_dir / "001.html").read_text(encoding=cfg.input.encoding)
    soup = BeautifulSoup(html, "lxml")

    gathas, delta = parse_primary_page(soup, primary["001.html"], cfg, global_kalash_start=1)

    assert len(gathas) == 1
    g = gathas[0]
    assert g.gatha_number == "001"
    assert g.heading_hi == "सिद्धों को नमस्कार"
    assert g.prakrit_text and g.prakrit_text.startswith("वंदित्तु")
    assert g.primary_teeka is not None
    assert len(g.primary_teeka.kalash_san) == 3
    assert g.primary_teeka.gatha_teeka_san is not None
    assert g.primary_teeka.gatha_teeka_bhaavarth_md
    assert g.anyavartha is not None
    assert len(g.anyavartha.tagged_terms) >= 8
    assert all("[" not in t.source_word for t in g.anyavartha.tagged_terms)
    assert delta == 3


@pytest.mark.skipif(SKIP, reason="NIKKYJAIN_LOCAL_PATH not set")
def test_parse_multi_gatha(cfg, indexes):
    primary, _ = indexes
    html = (cfg.input.resolved_html_dir / "009-010.html").read_text(encoding=cfg.input.encoding)
    soup = BeautifulSoup(html, "lxml")

    gathas, _ = parse_primary_page(soup, primary["009-010.html"], cfg, global_kalash_start=1)

    assert len(gathas) == 2
    nums = {g.gatha_number for g in gathas}
    assert "009" in nums and "010" in nums
    for g in gathas:
        assert g.is_combined_page


@pytest.mark.skipif(SKIP, reason="NIKKYJAIN_LOCAL_PATH not set")
def test_parse_secondary_kalash(cfg, indexes):
    primary, _ = indexes
    html = (cfg.input.resolved_html_dir / "012.html").read_text(encoding=cfg.input.encoding)
    soup = BeautifulSoup(html, "lxml")

    files = sorted(f.name for f in cfg.input.resolved_html_dir.iterdir() if f.is_file() and f.name.endswith(".html"))
    preceding = preceding_primary_gatha("012.html", files, primary)
    kal = parse_secondary_kalash_page(soup, "012.html", preceding, cfg)

    assert kal.kalash_number == "012"
    assert kal.preceding_primary_gatha_number is not None
