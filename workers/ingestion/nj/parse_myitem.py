"""Parse myItem.js to build gatha index maps for primary and secondary teekas."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from jain_kb_common.shastra_identifiers import get_identifier_fields

from .config import NJConfig

logger = logging.getLogger(__name__)

_BOM = "﻿"

# Matches: $optgrp=$('<optgroup label="[BOM?]LABEL">')
_OPTGRP_RE = re.compile(
    r"""\$optgrp=\$\('<optgroup label="﻿?([^"]+)"(?:>)?'\)"""
)

# Matches: $optgrp.append("<option value='FILE'><b>GATHA_NUM</b> - [BOM?]HEADING</option>");
_OPTION_RE = re.compile(
    r"""\$optgrp\.append\("<option value='([^']+)'><b>([^<]+)</b>\s*-\s*﻿?(.*?)</option>"\)"""
)

# Matches: mySel.append("<option value='FILE'><b>GATHA_NUM</b> - [BOM?]HEADING</option>");
# Used by shastras with no <optgroup> wrapper (e.g. परमात्मप्रकाश).
_OPTION_BARE_RE = re.compile(
    r"""mySel\.append\("<option value='([^']+)'><b>([^<]+)</b>\s*-\s*﻿?(.*?)</option>"\)"""
)

# Matches: mySel=$('select#select-native-N')
_SELECT_RE = re.compile(r"""mySel=\$\('(select#select-native-\d+)'\)""")


@dataclass
class GathaIndexEntry:
    html_filename: str   # "025-026-027.html"
    gatha_number: str    # "020-021-022"
    heading_hi: str      # "अप्रतिबुद्ध - पर पदार्थ में अहंकार / ममकार"
    adhikaar_hi: str     # "जीव अधिकार"
    adhikaar_number: int | None = None   # optgroup ordinal in index (1-based)


def _strip_bom(text: str) -> str:
    return text.replace(_BOM, "").strip()


_LEADING_ADHIKAAR_RE = re.compile(r"^(\d+)-(\d+.*)$")


def _split_leading_adhikaar(
    value: str, expected_adhikaar: int | None = None
) -> tuple[int | None, str]:
    """Strip a leading N- adhikaar prefix from a gatha value.

    Two strip modes:

    1. **Explicit match** (`expected_adhikaar` given — compound optgroup shastras
       like तत्त्वार्थसूत्र): strip whenever the leading prefix numerically equals
       the optgroup-derived adhikaar ordinal, *regardless of digit width*. This
       handles zero-padded equal-width pairs the width heuristic can't, e.g.
       "01-01" (अध्याय 1, सूत्र 01) → (1, "01").

    2. **Width heuristic** (no `expected_adhikaar`): strip only when the prefix has
       *fewer* digits than the first digit-group of the trailing portion —
       distinguishing an adhikaar prefix ("1-001") from a gatha range endpoint
       pair ("009-010").

    "1-001"     → (1, "001")
    "1-019-021" → (1, "019-021")
    "2-001"     → (2, "001")
    "009-010"   → (None, "009-010")   ← range, not split
    "019"       → (None, "019")
    "01-01" (expected_adhikaar=1) → (1, "01")
    """
    m = _LEADING_ADHIKAAR_RE.match(value)
    if m:
        prefix = m.group(1)
        trailing = m.group(2)
        # Mode 1: explicit adhikaar match for compound optgroup shastras.
        if expected_adhikaar is not None and prefix.isdigit() and int(prefix) == expected_adhikaar:
            logger.debug(
                "_split_leading_adhikaar: stripped matching prefix %d from %r → %r",
                expected_adhikaar, value, trailing,
            )
            return expected_adhikaar, trailing
        # Mode 2: width heuristic.
        trailing_first = trailing.split("-")[0]
        if trailing_first.isdigit() and len(prefix) < len(trailing_first):
            adh = int(prefix)
            logger.debug("_split_leading_adhikaar: stripped prefix %d from %r → %r", adh, value, trailing)
            return adh, trailing
    return None, value


def _parse_block(lines: list[str], *, is_compound: bool = False) -> dict[str, GathaIndexEntry]:
    """Parse a single select block (lines between two mySel= markers) into a filename→entry map.

    `is_compound` enables the explicit adhikaar-prefix strip for compound optgroup
    shastras (e.g. तत्त्वार्थसूत्र), where the gatha value carries a zero-padded
    adhyaaya prefix that is redundant with the optgroup ordinal.
    """
    result: dict[str, GathaIndexEntry] = {}
    current_adhikaar = ""
    current_adhikaar_number = 0

    for line in lines:
        stripped = line.strip()

        m = _OPTGRP_RE.search(stripped)
        if m:
            current_adhikaar = _strip_bom(m.group(1))
            current_adhikaar_number += 1
            continue

        m = _OPTION_RE.search(stripped)
        if m:
            html_filename = m.group(1).strip()
            gatha_number = m.group(2).strip()
            heading_hi = _strip_bom(m.group(3))
            adh_num, gatha_canonical = _split_leading_adhikaar(
                gatha_number,
                expected_adhikaar=current_adhikaar_number if is_compound and current_adhikaar_number else None,
            )
            result[html_filename] = GathaIndexEntry(
                html_filename=html_filename,
                gatha_number=gatha_canonical,
                heading_hi=heading_hi,
                adhikaar_hi=current_adhikaar,
                adhikaar_number=current_adhikaar_number or adh_num or None,
            )
            continue

        m = _OPTION_BARE_RE.search(stripped)
        if m:
            html_filename = m.group(1).strip()
            gatha_number = m.group(2).strip()
            heading_hi = _strip_bom(m.group(3))
            adh_num, gatha_canonical = _split_leading_adhikaar(gatha_number)
            result[html_filename] = GathaIndexEntry(
                html_filename=html_filename,
                gatha_number=gatha_canonical,
                heading_hi=heading_hi,
                adhikaar_hi=current_adhikaar,
                adhikaar_number=adh_num or current_adhikaar_number or None,
            )

    return result


def parse_myitem(cfg: NJConfig) -> tuple[dict[str, GathaIndexEntry], dict[str, GathaIndexEntry]]:
    """
    Parse myItem.js and return (primary_index, secondary_index).

    primary_index: dict[html_filename, GathaIndexEntry] for select-native-0
    secondary_index: dict[html_filename, GathaIndexEntry] for select-native-1 (empty if absent)
    """
    js_path = cfg.input.resolved_html_dir / cfg.input.my_item_js
    content = js_path.read_text(encoding=cfg.input.encoding)
    lines = content.splitlines()

    # Split lines into blocks delimited by mySel=$('select#...') lines
    blocks: dict[str, list[str]] = {}
    current_select: str | None = None
    current_lines: list[str] = []

    for line in lines:
        m = _SELECT_RE.search(line.strip())
        if m:
            if current_select is not None:
                blocks[current_select] = current_lines
            current_select = m.group(1)
            current_lines = []
        else:
            if current_select is not None:
                current_lines.append(line)

    if current_select is not None:
        blocks[current_select] = current_lines

    primary_key = cfg.selectors.primary_teeka_select.lstrip("#")   # "select#select-native-0"
    secondary_key = cfg.selectors.secondary_teeka_select.lstrip("#") if cfg.selectors.secondary_teeka_select else None

    is_compound = bool(get_identifier_fields(cfg.shastra.natural_key, "gatha"))

    primary_index = _parse_block(blocks.get(primary_key, []), is_compound=is_compound)
    secondary_index = (
        _parse_block(blocks.get(secondary_key, []), is_compound=is_compound) if secondary_key else {}
    )

    logger.info(
        "myItem.js parsed: %d primary entries (compound=%s), %d secondary entries",
        len(primary_index),
        is_compound,
        len(secondary_index),
    )

    return primary_index, secondary_index
