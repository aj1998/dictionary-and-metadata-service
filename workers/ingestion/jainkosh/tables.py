"""Table block extraction."""

from __future__ import annotations

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block


def extract_table_block(table: Node, config: JainkoshConfig) -> Block:
    """Convert a <table> node into a Block(kind='table', raw_html=...)."""
    block = Block(kind="table", raw_html=table.html or "")
    if config.table.extraction_strategy == "raw_html_plus_rows":
        block.table_rows = _extract_rows(table)
    return block


def _extract_rows(table: Node) -> list[list[str]]:
    return []
