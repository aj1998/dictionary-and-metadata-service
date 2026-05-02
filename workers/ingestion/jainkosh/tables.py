"""Table block extraction."""

from __future__ import annotations

from selectolax.parser import Node

from .models import Block


def extract_table_block(table: Node) -> Block:
    """Convert a <table> node into a Block(kind='table', raw_html=...)."""
    return Block(kind="table", raw_html=table.html or "")
