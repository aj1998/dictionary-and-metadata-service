"""Classify HTML files as primary_gatha, secondary_kalash, or skip."""

from __future__ import annotations

import logging
from typing import Literal

from .parse_myitem import GathaIndexEntry

logger = logging.getLogger(__name__)

PageKind = Literal["primary_gatha", "secondary_kalash", "skip"]


def classify_page(
    filename: str,
    primary_index: dict[str, GathaIndexEntry],
    secondary_index: dict[str, GathaIndexEntry],
) -> PageKind:
    if filename in primary_index:
        return "primary_gatha"
    if secondary_index and filename in secondary_index:
        return "secondary_kalash"
    return "skip"


def preceding_primary_gatha(
    filename: str,
    sorted_files: list[str],
    primary_index: dict[str, GathaIndexEntry],
) -> str | None:
    """Return the gatha_number of the last primary-gatha page before `filename` in sorted order."""
    try:
        idx = sorted_files.index(filename)
    except ValueError:
        return None
    for f in reversed(sorted_files[:idx]):
        if f in primary_index:
            gatha_number = primary_index[f].gatha_number
            # For combined pages like "009-010", use the last individual gatha number
            return gatha_number.split("-")[-1]
    return None
