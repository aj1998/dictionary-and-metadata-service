"""Table block extraction."""

from __future__ import annotations

import re

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block


_RAW_HTML_TEXT_RUN_RE = re.compile(r"(>)([^<]*)(<)")
_WS_RE = re.compile(r"[\t\n\r\f\v ]+")


def _clean_raw_html(html: str, config: JainkoshConfig) -> str:
    if not html:
        return html
    if not config.table.raw_html.collapse_whitespace:
        return html

    def _collapse_run(match: re.Match[str]) -> str:
        left, run, right = match.group(1), match.group(2), match.group(3)
        if not run:
            return left + run + right
        collapsed = _WS_RE.sub(" ", run).strip()
        if not collapsed:
            return left + right
        return left + collapsed + right

    return _RAW_HTML_TEXT_RUN_RE.sub(_collapse_run, html)


def extract_table_block(table: Node, config: JainkoshConfig) -> Block:
    """Convert a <table> node into a Block(kind='table', raw_html=...)."""
    raw_html = table.html or ""
    if config.table.raw_html.collapse_whitespace:
        raw_html = _clean_raw_html(raw_html, config)
    block = Block(kind="table", raw_html=raw_html)
    if config.table.extraction_strategy == "raw_html_plus_rows":
        block.table_rows = _extract_rows(table)
    return block


def _extract_rows(table: Node) -> list[list[str]]:
    return []
