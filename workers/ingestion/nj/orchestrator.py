"""Orchestrator for parsing a full NJ shastra from HTML files."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from jain_kb_common.shastra_identifiers import get_identifier_fields

from .classify_pages import classify_page, preceding_primary_gatha
from .config import NJConfig
from .models import GathaExtract, KalashExtract, ShastraParseResult
from .parse_myitem import GathaIndexEntry, parse_myitem
from .parse_page import parse_primary_page, parse_secondary_kalash_page

logger = logging.getLogger(__name__)


def _build_identifier_values(
    cfg: NJConfig,
    adhikaar_number: int | None,
    gatha_number_str: str,
    *,
    kind: str = "gatha",
) -> dict[str, str]:
    """Build compound identifier field→value map for a single gatha/kalash."""
    fields = get_identifier_fields(cfg.shastra.natural_key, kind) or []
    if not fields:
        return {}
    values: dict[str, str] = {}
    # Every leading field is an adhikaar-style grouping (अधिकार / अध्याय / परिच्छेद —
    # all aliases of the adhikaar ordinal per shastra.json). Populate them from the
    # adhikaar_number rather than matching a single hard-coded field name.
    for f in fields[:-1]:
        if adhikaar_number is not None:
            values[f] = str(adhikaar_number)
    values[fields[-1]] = gatha_number_str
    return values


def _enrich_adhikaar_hi(cfg: NJConfig, index: dict[str, GathaIndexEntry]) -> None:
    """Fill in adhikaar_hi from config.adhikaars when the index didn't carry one."""
    if not cfg.shastra.adhikaars:
        return
    for entry in index.values():
        if not entry.adhikaar_hi and entry.adhikaar_number is not None:
            name = next(
                (a.name_hi for a in cfg.shastra.adhikaars if a.number == entry.adhikaar_number),
                "",
            )
            if name:
                entry.adhikaar_hi = name


def parse_shastra(
    cfg: NJConfig,
    *,
    batch_offset: int = 0,
    batch_limit: int | None = None,
) -> ShastraParseResult:
    """
    Parse a shastra with optional batching over sorted, non-skipped HTML pages.

    batch_offset: number of eligible pages to skip from the start.
    batch_limit: max number of eligible pages to process (None = all remaining pages).
    """
    primary_index, secondary_index = parse_myitem(cfg)

    _enrich_adhikaar_hi(cfg, primary_index)
    _enrich_adhikaar_hi(cfg, secondary_index)

    html_dir = cfg.input.resolved_html_dir
    all_files = sorted(f.name for f in html_dir.iterdir() if f.is_file() and f.name.endswith(".html"))
    eligible_files = [f for f in all_files if f not in cfg.input.skip_files]

    if batch_offset < 0:
        raise ValueError("batch_offset must be >= 0")
    if batch_limit is not None and batch_limit < 0:
        raise ValueError("batch_limit must be >= 0 when provided")

    start = batch_offset
    end = None if batch_limit is None else batch_offset + batch_limit
    sorted_files = eligible_files[start:end]

    all_gathas: list[GathaExtract] = []
    secondary_kalashes: list[KalashExtract] = []
    warnings: list[str] = []
    global_kalash_counter = 0

    for filename in sorted_files:
        kind = classify_page(filename, primary_index, secondary_index)
        soup = BeautifulSoup((html_dir / filename).read_text(encoding=cfg.input.encoding), "lxml")

        if kind == "primary_gatha":
            gathas, delta = parse_primary_page(
                soup,
                primary_index[filename],
                cfg,
                global_kalash_start=global_kalash_counter + 1,
            )
            global_kalash_counter += delta
            gathas = [
                g.model_copy(update={
                    "identifier_values": _build_identifier_values(cfg, g.adhikaar_number, g.gatha_number),
                })
                for g in gathas
            ]
            all_gathas.extend(gathas)
        elif kind == "secondary_kalash":
            # preceding primary reference is computed in full eligible ordering,
            # not only within the current batch window.
            preceding = preceding_primary_gatha(filename, eligible_files, primary_index)
            kalashes = parse_secondary_kalash_page(
                soup,
                filename,
                preceding,
                cfg,
                secondary_entry=secondary_index.get(filename),
            )
            kalashes = [
                k.model_copy(update={
                    "identifier_values": _build_identifier_values(
                        cfg, None, k.kalash_number, kind="kalash"
                    ),
                })
                for k in kalashes
            ]
            secondary_kalashes.extend(kalashes)
        else:
            warnings.append(f"unclassified page: {filename}")

    return ShastraParseResult(
        shastra_natural_key=cfg.shastra.natural_key,
        gathas=all_gathas,
        secondary_kalashes=secondary_kalashes,
        total_html_files_processed=len(sorted_files),
        warnings=warnings,
        parser_version=cfg.version,
        parsed_at=datetime.now(timezone.utc),
    )
